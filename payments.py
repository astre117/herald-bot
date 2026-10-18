import asyncio
import json
import logging
import os
import sqlite3
import urllib.parse
import urllib.request
from contextlib import closing
from datetime import date, timedelta

import config
import db

# The six toolkit tier prices, in naira.
TOOLKIT_AMOUNTS = {15000, 20000, 25000, 30000, 35000, 40000}
# During testing you also get alerts for a 100 naira test payment.
ALERT_AMOUNTS = TOOLKIT_AMOUNTS | {100}


def _conn():
    c = sqlite3.connect(db.DB_PATH)
    c.execute(
        "CREATE TABLE IF NOT EXISTS payments ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "flw_id INTEGER UNIQUE NOT NULL, "
        "tx_ref TEXT, "
        "email TEXT, "
        "amount INTEGER, "
        "currency TEXT, "
        "is_toolkit INTEGER DEFAULT 0, "
        "claimed_by_chat_id INTEGER, "
        "created_at TEXT DEFAULT CURRENT_TIMESTAMP)"
    )
    return c


def _fetch(days_back, email=None, max_pages=20):
    """Ask Flutterwave for successful naira payments. Their answer is the proof."""
    key = os.environ.get("FLW_SECRET_KEY", "")
    if not key:
        logging.error("FLW_SECRET_KEY is not set")
        return []

    today = date.today()
    start = (today - timedelta(days=days_back)).isoformat()
    results = []

    for page in range(1, max_pages + 1):
        params = {
            "from": start,
            "to": today.isoformat(),
            "status": "successful",
            "currency": "NGN",
            "page": page,
        }
        if email:
            params["customer_email"] = email

        req = urllib.request.Request(
            "https://api.flutterwave.com/v3/transactions?"
            + urllib.parse.urlencode(params),
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "User-Agent": "herald-bot/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read())

        rows = body.get("data") or []
        results.extend(rows)

        total_pages = ((body.get("meta") or {}).get("page_info") or {}).get("total_pages")
        if not rows or (total_pages and page >= int(total_pages)):
            break

    return [
        r for r in results
        if r.get("status") == "successful" and r.get("currency") == "NGN"
    ]


def _is_toolkit(amount, tx_ref):
    """Optional filter: set TOOLKIT_TXREF_PREFIX in Railway if toolkit
    payments share a reference prefix, so other payments are ignored."""
    if amount not in TOOLKIT_AMOUNTS:
        return 0
    prefix = os.environ.get("TOOLKIT_TXREF_PREFIX", "")
    if prefix and not (tx_ref or "").startswith(prefix):
        return 0
    return 1


def _record(row):
    """Saves one payment. Returns a dict if it is new, otherwise None."""
    try:
        flw_id = int(row["id"])
        amount = int(round(float(row.get("amount", 0))))
    except (KeyError, TypeError, ValueError):
        return None

    email = ((row.get("customer") or {}).get("email") or "").strip().lower()
    tx_ref = row.get("tx_ref") or ""
    is_toolkit = _is_toolkit(amount, tx_ref)

    with closing(_conn()) as c:
        cur = c.execute(
            "INSERT OR IGNORE INTO payments "
            "(flw_id, tx_ref, email, amount, currency, is_toolkit) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (flw_id, tx_ref, email, amount, "NGN", is_toolkit),
        )
        c.commit()
        if cur.rowcount != 1:
            return None

    return {
        "flw_id": flw_id,
        "amount": amount,
        "email": email,
        "tx_ref": tx_ref,
        "is_toolkit": is_toolkit,
    }


def toolkit_count():
    with closing(_conn()) as c:
        return c.execute(
            "SELECT COUNT(*) FROM payments WHERE is_toolkit = 1"
        ).fetchone()[0]


def sync_recent(days_back=2):
    """Returns (new payments, was_first_run). The first run only builds a
    quiet baseline so you are not flooded with old payments."""
    with closing(_conn()) as c:
        first_run = c.execute("SELECT COUNT(*) FROM payments").fetchone()[0] == 0

    rows = _fetch(3 if first_run else days_back)
    new = []
    for r in rows:
        rec = _record(r)
        if rec:
            new.append(rec)
    return new, first_run


async def sync_job(context):
    """Runs every 5 minutes (set up in main.py)."""
    try:
        new, first_run = await asyncio.to_thread(sync_recent)
    except Exception:
        logging.exception("Payment sync failed")
        return

    if first_run:
        logging.info("Payment baseline saved (%d recent payments)", len(new))
        return

    for p in new:
        if p["amount"] not in ALERT_AMOUNTS:
            continue
        if p["is_toolkit"]:
            note = f"Toolkit payment #{toolkit_count()}."
        else:
            note = "Not counted as a toolkit sale."
        text = (
            f"New payment: ₦{p['amount']:,} from {p['email'] or 'unknown email'}.\n"
            f"{note}\nRef: {p['tx_ref']}"
        )
        for admin_id in config.ADMIN_USER_IDS:
            try:
                await context.bot.send_message(chat_id=admin_id, text=text)
            except Exception:
                logging.exception("Could not notify admin %s", admin_id)

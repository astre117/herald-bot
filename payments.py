import asyncio
import json
import logging
import os
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from contextlib import closing
from datetime import date, timedelta

import config
import db

# The six toolkit tier prices, in naira.
TOOLKIT_AMOUNTS = {15000, 20000, 25000, 30000, 35000, 40000}


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


def _fetch_range(start, end, email=None, max_pages=20):
    key = os.environ.get("FLW_SECRET_KEY", "")
    if not key:
        logging.error("FLW_SECRET_KEY is not set")
        return []

    results = []
    for page in range(1, max_pages + 1):
        params = {
            "from": start.isoformat(),
            "to": end.isoformat(),
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


def _fetch(days_back, email=None):
    """Ask Flutterwave for successful naira payments. Their answer is the proof."""
    today = date.today()
    start = today - timedelta(days=days_back)
    try:
        # Tomorrow's date makes sure today's payments are included.
        return _fetch_range(start, today + timedelta(days=1), email)
    except urllib.error.HTTPError as e:
        logging.warning("Fetch with tomorrow's date failed (%s), retrying", e.code)
        return _fetch_range(start, today, email)


def _near(value, target):
    """True if value is the target price, or the price plus a small checkout
    fee paid by the customer (up to 4 percent)."""
    return target <= value <= target * 1.04


def _is_toolkit(amounts, tx_ref):
    """Returns 1 for a toolkit sale, 2 for a test payment, 0 for anything else.
    Test mode: set TEST_PAYMENT_AMOUNT in Railway (for example 300).
    Optional: set TOOLKIT_TXREF_PREFIX if toolkit payments share a reference
    prefix, so other payments are ignored."""
    test_amount = os.environ.get("TEST_PAYMENT_AMOUNT", "").strip()
    if test_amount.isdigit():
        target = int(test_amount)
        if any(_near(a, target) for a in amounts):
            return 2

    if not any(_near(a, t) for a in amounts for t in TOOLKIT_AMOUNTS):
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

    try:
        charged = int(round(float(row.get("charged_amount"))))
    except (TypeError, ValueError):
        charged = amount

    email = ((row.get("customer") or {}).get("email") or "").strip().lower()
    tx_ref = row.get("tx_ref") or ""
    is_toolkit = _is_toolkit([amount, charged], tx_ref)

    with closing(_conn()) as c:
        cur = c.execute(
            "INSERT OR IGNORE INTO payments "
            "(flw_id, tx_ref, email, amount, currency, is_toolkit) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (flw_id, tx_ref, email, amount, "NGN", is_toolkit),
        )
        c.commit()
        if cur.rowcount != 1:
            # Already recorded earlier. If it was ignored before test mode
            # was on, upgrade it so it can be alerted and claimed.
            if is_toolkit == 2:
                up = c.execute(
                    "UPDATE payments SET is_toolkit = 2 "
                    "WHERE flw_id = ? AND is_toolkit = 0",
                    (flw_id,),
                )
                c.commit()
                if up.rowcount != 1:
                    return None
            else:
                return None

    return {
        "flw_id": flw_id,
        "amount": amount,
        "email": email,
        "tx_ref": tx_ref,
        "is_toolkit": is_toolkit,
    }


def toolkit_count():
    """Real toolkit sales only. Test payments are not counted."""
    with closing(_conn()) as c:
        return c.execute(
            "SELECT COUNT(*) FROM payments WHERE is_toolkit = 1"
        ).fetchone()[0]


def recent_payments_text(limit=6):
    with closing(_conn()) as c:
        rows = c.execute(
            "SELECT amount, is_toolkit, email, tx_ref, created_at "
            "FROM payments ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    if not rows:
        return "No payments recorded yet."
    kinds = {0: "other", 1: "toolkit", 2: "TEST"}
    lines = []
    for amount, kind, email, ref, created in rows:
        lines.append(
            f"₦{amount:,} | {kinds.get(kind, '?')} | {email or 'no email'} | "
            f"{created} UTC | ref: {ref}"
        )
    return "Last recorded payments:\n" + "\n".join(lines)


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
        print(f"Payment baseline saved ({len(new)} recent payments)")
        return

    for p in new:
        if not p["is_toolkit"]:
            continue
        if p["is_toolkit"] == 2:
            note = "TEST payment. Not counted toward slots."
        else:
            note = f"Toolkit payment #{toolkit_count()}."
        text = (
            f"New payment: ₦{p['amount']:,} from {p['email'] or 'unknown email'}.\n"
            f"{note}\nRef: {p['tx_ref']}"
        )
        for admin_id in config.ADMIN_USER_IDS:
            try:
                await context.bot.send_message(chat_id=admin_id, text=text)
            except Exception:
                logging.exception("Could not notify admin %s", admin_id)


def claim_email(email, chat_id):
    """Returns 'ok', 'none' or 'taken'."""
    email = email.strip().lower()

    for attempt in range(2):
        with closing(_conn()) as c:
            rows = c.execute(
                "SELECT id, claimed_by_chat_id FROM payments "
                "WHERE email = ? AND is_toolkit IN (1, 2)",
                (email,),
            ).fetchall()

            if rows:
                if any(row[1] == chat_id for row in rows):
                    return "ok"
                free = [row for row in rows if row[1] is None]
                if free:
                    c.execute(
                        "UPDATE payments SET claimed_by_chat_id = ? WHERE id = ?",
                        (chat_id, free[0][0]),
                    )
                    c.commit()
                    return "ok"
                return "taken"

        if attempt == 0:
            # Not in our records yet: ask Flutterwave about this email.
            try:
                for tx in _fetch(60, email=email):
                    _record(tx)
            except Exception:
                logging.exception("Email lookup failed")
                return "none"

    return "none"

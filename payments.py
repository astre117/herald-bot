import base64
import hashlib
import hmac
import json
import logging
import os
import sqlite3
import urllib.parse
import urllib.request
from contextlib import closing

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


def signature_ok(headers, raw_body):
    """Accepts Flutterwave's secret-hash header (plain or HMAC style)."""
    secret = os.environ.get("FLW_SECRET_HASH", "")
    if not secret:
        return False

    plain = headers.get("verif-hash", "")
    if plain and hmac.compare_digest(plain, secret):
        return True

    sig = headers.get("flutterwave-signature", "")
    if sig:
        digest = base64.b64encode(
            hmac.new(secret.encode(), raw_body, hashlib.sha256).digest()
        ).decode()
        return hmac.compare_digest(sig, digest)

    return False


def already_recorded(flw_id):
    with closing(_conn()) as c:
        row = c.execute(
            "SELECT 1 FROM payments WHERE flw_id = ?", (int(flw_id),)
        ).fetchone()
    return row is not None


def verify_transaction(flw_id):
    """Ask Flutterwave directly. Returns the data only if it really was a
    successful naira payment, otherwise None."""
    key = os.environ.get("FLW_SECRET_KEY", "")
    if not key:
        logging.error("FLW_SECRET_KEY is not set")
        return None

    req = urllib.request.Request(
        f"https://api.flutterwave.com/v3/transactions/{int(flw_id)}/verify",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "herald-bot/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = json.loads(resp.read())

    data = body.get("data") or {}
    if (
        body.get("status") == "success"
        and data.get("status") == "successful"
        and data.get("currency") == "NGN"
    ):
        return data
    return None


def record_payment(data):
    amount = int(round(float(data.get("amount", 0))))
    email = ((data.get("customer") or {}).get("email") or "").strip().lower()
    is_toolkit = 1 if amount in TOOLKIT_AMOUNTS else 0

    with closing(_conn()) as c:
        cur = c.execute(
            "INSERT OR IGNORE INTO payments "
            "(flw_id, tx_ref, email, amount, currency, is_toolkit) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (int(data["id"]), data.get("tx_ref"), email, amount,
             data.get("currency"), is_toolkit),
        )
        c.commit()
        is_new = cur.rowcount == 1
        count = c.execute(
            "SELECT COUNT(*) FROM payments WHERE is_toolkit = 1"
        ).fetchone()[0]
    return is_new, is_toolkit, count, amount, email


def notify_admins(text):
    token = config.TELEGRAM_BOT_TOKEN
    for admin_id in config.ADMIN_USER_IDS:
        body = urllib.parse.urlencode(
            {"chat_id": admin_id, "text": text}
        ).encode()
        try:
            urllib.request.urlopen(
                urllib.request.Request(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    data=body,
                ),
                timeout=10,
            )
        except Exception:
            logging.exception("Could not notify admin %s", admin_id)


def process_webhook(payload):
    if payload.get("event") != "charge.completed":
        return

    data = payload.get("data") or {}
    flw_id = data.get("id")
    if not flw_id:
        return

    # Flutterwave can deliver the same webhook more than once.
    if already_recorded(flw_id):
        return

    # The webhook is only a claim. Flutterwave's own answer is the proof.
    verified = verify_transaction(flw_id)
    if not verified:
        logging.info("Payment %s did not verify as successful NGN", flw_id)
        return

    is_new, is_toolkit, count, amount, email = record_payment(verified)
    if not is_new:
        return

    note = (
        f"Toolkit payment #{count}."
        if is_toolkit
        else "Not a toolkit amount, so it is not counted as a toolkit sale."
    )
    notify_admins(
        f"Payment verified: ₦{amount:,} from {email or 'unknown email'}. {note}"
    )

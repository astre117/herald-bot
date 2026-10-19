"""
Follow-ups.

Telegram only lets a business bot message a customer within 24 hours of
their last message, so:
- about 20 hours after their last message, Herald sends ONE automatic nudge
- about day 3 and day 7, the admin gets a reminder with a ready-written
  message to send from her own account
Nobody is followed up if they paid, said stop, were handed to the coach,
or have written fewer than MIN_MESSAGES messages.
"""
import asyncio
import html
import logging
import os
import re
import sqlite3
import time
from contextlib import closing

from telegram.constants import ParseMode

import config
import conversations
import db
import faq
import settings

MIN_MESSAGES = 2
NUDGE_MIN_HOURS = 20
NUDGE_MAX_HOURS = 23.5  # Telegram's 24 hour window closes soon after this
DAY3_HOURS = 72
DAY7_HOURS = 168

NUDGE_INSTRUCTION = (
    "The customer has not replied for about a day. Write ONE follow-up text "
    "from Herald, 1 to 2 short sentences. Refer naturally to what they said "
    "or asked. Ask at most one easy question. No pressure, no false urgency, "
    "no repeating your earlier pitch, no slot counts, no payment link, no "
    "introduction. Output only the message text. If a follow-up would be "
    "unwelcome (they said no, asked to stop, or the conversation ended "
    "naturally), output exactly SKIP."
)

DAY3_INSTRUCTION = (
    "It is about 3 days since the customer last replied. Write a short "
    "message (1 to 3 short sentences) that Coach Create will send herself "
    "from her own account. Do not mention Herald or being an AI. Warm and "
    "low pressure, refer to what they said, offer to answer one question. "
    "No false urgency, no income promises, no slot counts. Output only the "
    "message text. If a follow-up would be unwelcome, output exactly SKIP."
)

DAY7_INSTRUCTION = (
    "It is about a week since the customer last replied. Write a short "
    "message (1 to 3 short sentences) that Coach Create will send herself "
    "from her own account. Do not mention Herald or being an AI. It is a "
    "last gentle check-in that leaves the door open, with no pressure, no "
    "false urgency, no income promises and no slot counts. Output only the "
    "message text. If a follow-up would be unwelcome, output exactly SKIP."
)


def _conn():
    c = sqlite3.connect(db.DB_PATH)
    c.execute(
        "CREATE TABLE IF NOT EXISTS prospects ("
        "chat_id INTEGER PRIMARY KEY, "
        "first_name TEXT, "
        "connection_id TEXT, "
        "status TEXT DEFAULT 'active', "
        "last_user_at INTEGER, "
        "last_bot_at INTEGER, "
        "user_msgs INTEGER DEFAULT 0, "
        "stage INTEGER DEFAULT 0)"
    )
    return c


def _speed_for(chat_id):
    """Testing only: speeds up the clock for ONE chat (FOLLOWUP_TEST_CHAT_ID)."""
    test_chat = os.environ.get("FOLLOWUP_TEST_CHAT_ID", "").strip()
    if test_chat and test_chat == str(chat_id):
        try:
            return max(1.0, float(os.environ.get("FOLLOWUP_SPEED", "60")))
        except ValueError:
            return 1.0
    return 1.0


def touch_user(chat_id, first_name, connection_id):
    """Called whenever a customer writes. Restarts their follow-up clock."""
    now = int(time.time())
    with closing(_conn()) as c:
        c.execute("INSERT OR IGNORE INTO prospects (chat_id) VALUES (?)", (chat_id,))
        c.execute(
            "UPDATE prospects SET first_name = ?, connection_id = ?, "
            "last_user_at = ?, user_msgs = user_msgs + 1, stage = 0, "
            "status = CASE WHEN status = 'handoff' THEN 'active' ELSE status END "
            "WHERE chat_id = ?",
            (first_name, connection_id, now, chat_id),
        )
        c.commit()


def touch_bot(chat_id):
    with closing(_conn()) as c:
        c.execute(
            "UPDATE prospects SET last_bot_at = ? WHERE chat_id = ?",
            (int(time.time()), chat_id),
        )
        c.commit()


def set_status(chat_id, status):
    """status: 'handoff', 'enrolled' or 'stopped'."""
    with closing(_conn()) as c:
        c.execute("INSERT OR IGNORE INTO prospects (chat_id) VALUES (?)", (chat_id,))
        if status == "handoff":
            c.execute(
                "UPDATE prospects SET status = 'handoff' "
                "WHERE chat_id = ? AND status = 'active'",
                (chat_id,),
            )
        else:
            c.execute(
                "UPDATE prospects SET status = ? WHERE chat_id = ?",
                (status, chat_id),
            )
        c.commit()


def _set_stage(chat_id, stage):
    with closing(_conn()) as c:
        c.execute("UPDATE prospects SET stage = ? WHERE chat_id = ?", (stage, chat_id))
        c.commit()


def _generate(history, name, instruction):
    """Asks Claude to write a follow-up using the whole conversation."""
    if not history:
        return ""
    system_prompt = (
        faq.SALES_PROMPT + faq.load_sales_kb() + settings.live_settings_text()
    )
    messages = list(history)
    while messages and messages[0]["role"] == "assistant":
        messages.pop(0)
    messages.append(
        {
            "role": "user",
            "content": "[System note, not from the customer: " + instruction + "]",
        }
    )
    response = faq._client.messages.create(
        model="claude-haiku-5-5",
        max_tokens=1000,
        system=system_prompt,
        messages=messages,
    )
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    text = re.sub(r"\[HANDOFF:[^\]]*\]", "", text)
    text = text.replace("[STOP]", "").replace("|||", " ").strip()
    return text


async def _send_nudge(context, chat_id, name, connection_id):
    _set_stage(chat_id, 1)  # set first, so a failure never repeats the nudge
    if not connection_id:
        return
    if conversations.count_replies_today() >= settings.daily_cap():
        return

    history = conversations.get_recent(chat_id, limit=12)
    text = await asyncio.to_thread(_generate, history, name, NUDGE_INSTRUCTION)
    if not text or text.upper().startswith("SKIP"):
        return

    await context.bot.send_chat_action(
        chat_id=chat_id, action="typing", business_connection_id=connection_id
    )
    await asyncio.sleep(2)
    sent = await context.bot.send_message(
        chat_id=chat_id, text=text, business_connection_id=connection_id
    )
    conversations.save_message(chat_id, "assistant", text, sent.message_id)
    touch_bot(chat_id)


async def _remind(context, chat_id, name, new_stage, label, instruction):
    _set_stage(chat_id, new_stage)
    history = conversations.get_recent(chat_id, limit=12)
    draft = await asyncio.to_thread(_generate, history, name, instruction)
    if draft.upper().startswith("SKIP"):
        draft = ""

    last_theirs = ""
    for m in reversed(history):
        if m["role"] == "user":
            last_theirs = m["content"]
            break
    if len(last_theirs) > 150:
        last_theirs = last_theirs[:150] + "..."

    text = (
        f"Follow-up due ({label}): <b>{html.escape(name or 'a prospect')}</b>\n"
        f"Their last message: {html.escape(last_theirs)}\n\n"
    )
    if draft:
        text += (
            "Suggested message (tap to copy):\n"
            f"<code>{html.escape(draft)}</code>\n\n"
        )
    text += (
        f'<a href="tg://user?id={chat_id}">Open chat</a>\n'
        "Send it from your own account."
    )

    for admin_id in config.ADMIN_USER_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id, text=text, parse_mode=ParseMode.HTML
            )
        except Exception:
            logging.exception("Could not send follow-up reminder to %s", admin_id)


async def followup_job(context):
    """Runs every 3 minutes (set up in main.py)."""
    if not settings.is_on() or conversations.is_paused(0):
        return

    now = int(time.time())
    with closing(_conn()) as c:
        rows = c.execute(
            "SELECT chat_id, first_name, connection_id, last_user_at, stage "
            "FROM prospects WHERE status = 'active' AND stage < 3 "
            "AND last_user_at IS NOT NULL AND last_bot_at IS NOT NULL "
            "AND last_bot_at >= last_user_at AND user_msgs >= ?",
            (MIN_MESSAGES,),
        ).fetchall()

    for chat_id, name, connection_id, last_user, stage in rows:
        if conversations.is_paused(chat_id):
            continue
        hours = (now - last_user) / 3600 * _speed_for(chat_id)
        try:
            if stage == 0:
                if hours >= NUDGE_MAX_HOURS:
                    _set_stage(chat_id, 1)  # window passed, skip the nudge
                elif hours >= NUDGE_MIN_HOURS:
                    await _send_nudge(context, chat_id, name, connection_id)
            elif stage == 1 and hours >= DAY3_HOURS:
                await _remind(context, chat_id, name, 2, "day 3", DAY3_INSTRUCTION)
            elif stage == 2 and hours >= DAY7_HOURS:
                await _remind(context, chat_id, name, 3, "day 7", DAY7_INSTRUCTION)
        except Exception:
            logging.exception("Follow-up failed for chat %s", chat_id)


def report_text():
    with closing(_conn()) as c:
        rows = c.execute(
            "SELECT chat_id, first_name, status, stage, user_msgs, last_user_at "
            "FROM prospects ORDER BY last_user_at DESC LIMIT 10"
        ).fetchall()
    if not rows:
        return "No prospects tracked yet."

    now = int(time.time())
    lines = []
    for chat_id, name, status, stage, msgs, last_user in rows:
        mins = int((now - last_user) / 60) if last_user else 0
        lines.append(
            f"{name or 'Unknown'} | id {chat_id} | {status} | step {stage}/3 | "
            f"{msgs} msgs | wrote {mins} min ago"
        )
    return (
        "Prospects (latest 10):\n" + "\n".join(lines)
        + "\n\nStep 0 = nothing sent yet, 1 = nudge done or skipped, "
        "2 = day 3 reminder sent, 3 = day 7 reminder sent."
    )

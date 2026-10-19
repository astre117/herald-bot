import sqlite3
from contextlib import closing

import config
import db
import payments


def has_verified_payment(chat_id):
    with closing(payments._conn()) as c:
        row = c.execute(
            "SELECT 1 FROM payments WHERE claimed_by_chat_id = ? LIMIT 1",
            (chat_id,),
        ).fetchone()
    return row is not None


def note_for(chat_id):
    """Tells Herald the truth about customers whose payment was verified."""
    if has_verified_payment(chat_id):
        return (
            "\n\n[System note, not from the customer: this customer's payment "
            "HAS been verified by the system, and the toolkit materials link "
            "HAS already been delivered to them. That is correct and final. "
            "Never say you are checking their payment and never retract or "
            "correct it. If they say the materials do not open, say you are "
            "bringing Coach Create in and add the handoff tag. Otherwise "
            "answer their message normally and warmly.]"
        )
    return ""


def reset_chat(chat_id):
    """Testing only: erases one chat's history so it starts fresh."""
    with closing(sqlite3.connect(db.DB_PATH)) as c:
        for sql in (
            "DELETE FROM conversations WHERE chat_id = ?",
            "DELETE FROM prospects WHERE chat_id = ?",
            "DELETE FROM paused_chats WHERE chat_id = ?",
            "UPDATE payments SET claimed_by_chat_id = NULL WHERE claimed_by_chat_id = ?",
        ):
            try:
                c.execute(sql, (chat_id,))
            except sqlite3.OperationalError:
                pass  # that table may not exist yet
        c.commit()


async def resetchat_command(update, context):
    if not update.effective_user or not config.is_admin(update.effective_user.id):
        return
    if not context.args or not context.args[0].lstrip("-").isdigit():
        await update.message.reply_text(
            "Usage: /resetchat CHAT_ID\n"
            "Get the id from /followups. This erases that chat's history so "
            "you can test it fresh. Never use it on a real customer."
        )
        return
    chat_id = int(context.args[0])
    reset_chat(chat_id)
    await update.message.reply_text(
        f"Chat {chat_id} reset. Herald treats it as a brand-new customer."
    )

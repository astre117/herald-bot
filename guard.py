import sqlite3
from contextlib import closing

import config
import db
import payments


def claimed_kinds(chat_id):
    with closing(payments._conn()) as c:
        rows = c.execute(
            "SELECT DISTINCT is_toolkit FROM payments WHERE claimed_by_chat_id = ?",
            (chat_id,),
        ).fetchall()
    return {r[0] for r in rows}


def note_for(chat_id):
    """Tells Herald the truth about customers whose payment was verified."""
    kinds = claimed_kinds(chat_id)
    note = ""

    if kinds & {1, 2}:
        note += (
            "\n\n[System note, not from the customer: this customer's toolkit "
            "payment HAS been verified by the system, and the toolkit "
            "materials link HAS already been delivered to them. That is "
            "correct and final. Never say you are checking their payment and "
            "never retract or correct it. If they say the materials do not "
            "open, say you are bringing Coach Create in and add the handoff "
            "tag. Otherwise answer their message normally and warmly.]"
        )

    if kinds & {3, 4}:
        note += (
            "\n\n[System note, not from the customer: this customer's Cohort "
            "payment HAS been detected by the system, and Coach Create has "
            "been alerted. She will confirm their spot and set up their "
            "access personally. Never say their access is already set up, "
            "and never say you are still checking the payment or retract "
            "this. Answer their questions warmly. For anything about access "
            "or onboarding, say Coach Create will handle it and add the "
            "handoff tag.]"
        )

    return note


def reset_chat(chat_id):
    """Testing only: erases one chat's history so it starts fresh."""
    with closing(sqlite3.connect(db.DB_PATH)) as c:
        for sql in (
            "DELETE FROM conversations WHERE chat_id = ?",
            "DELETE FROM prospects WHERE chat_id = ?",
            "DELETE FROM cohort_pitched WHERE chat_id = ?",
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

from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes

import db
import config


async def remind_in_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: /remindin 30 Class starts in 30 minutes!
    First arg is minutes from now, rest is the message."""
    if not config.is_admin(update.effective_user.id):
        await update.message.reply_text("This command is admin-only.")
        return

    if len(context.args) < 2 or not context.args[0].isdigit():
        await update.message.reply_text(
            "Usage: /remindin <minutes> <message>\nExample: /remindin 30 Class starts soon!"
        )
        return

    minutes = int(context.args[0])
    message = " ".join(context.args[1:])
    run_at = (datetime.utcnow() + timedelta(minutes=minutes)).isoformat()

    db.add_reminder(
        update.effective_chat.id, message, run_at, update.effective_user.id,
        thread_id=update.message.message_thread_id,
    )
    await update.message.reply_text(f"⏰ Reminder set for {minutes} minutes from now.")


async def remind_at_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: /remindat 2026-09-02 18:45 Class is starting!
    Time is interpreted as UTC — adjust for your timezone when setting it."""
    if not config.is_admin(update.effective_user.id):
        await update.message.reply_text("This command is admin-only.")
        return

    if len(context.args) < 3:
        await update.message.reply_text(
            "Usage: /remindat YYYY-MM-DD HH:MM <message> (time is UTC)\n"
            "Example: /remindat 2026-09-02 18:00 Class starting in the group!"
        )
        return

    date_str, time_str = context.args[0], context.args[1]
    message = " ".join(context.args[2:])

    try:
        run_at_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    except ValueError:
        await update.message.reply_text("Couldn't parse that date/time. Use YYYY-MM-DD HH:MM.")
        return

    db.add_reminder(
        update.effective_chat.id, message, run_at_dt.isoformat(), update.effective_user.id,
        thread_id=update.message.message_thread_id,
    )
    await update.message.reply_text(f"⏰ Reminder scheduled for {run_at_dt.isoformat()} UTC.")


async def check_due_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Runs on a repeating JobQueue timer (see main.py) — checks the DB for
    anything due and sends it. DB-backed so it survives bot restarts."""
    now_iso = datetime.utcnow().isoformat()
    due = db.get_due_reminders(now_iso)
    for reminder in due:
        try:
            await context.bot.send_message(
                chat_id=reminder["chat_id"],
                message_thread_id=reminder["thread_id"],
                text=f"⏰ Reminder: {reminder['message']}",
            )
        finally:
            db.mark_reminder_sent(reminder["id"])

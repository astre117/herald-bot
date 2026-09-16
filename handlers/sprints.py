from telegram import Update
from telegram.ext import ContextTypes

import db
import config


async def start_sprint_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: /startsprint <title>"""
    if not config.is_admin(update.effective_user.id):
        await update.message.reply_text("This command is admin-only.")
        return

    title = " ".join(context.args) if context.args else "Writing Sprint"
    chat_id = update.effective_chat.id

    existing = db.get_active_sprint(chat_id)
    if existing:
        await update.message.reply_text(
            f"There's already an active sprint here: '{existing['title']}'. "
            "End it first with /endsprint."
        )
        return

    db.start_sprint(title, chat_id)
    await update.message.reply_text(
        f"🏁 Sprint started: **{title}**\n\n"
        "Reply in this chat to check in your progress! Use /endsprint when time's up.",
        parse_mode="Markdown",
    )


async def end_sprint_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: /endsprint"""
    if not config.is_admin(update.effective_user.id):
        await update.message.reply_text("This command is admin-only.")
        return

    chat_id = update.effective_chat.id
    ended = db.end_active_sprint(chat_id)
    if not ended:
        await update.message.reply_text("No active sprint running here.")
        return

    await update.message.reply_text(
        f"🎉 Sprint '{ended['title']}' has ended! Great work everyone — "
        "drop your word counts / progress below."
    )


async def sprint_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Anyone can check: /sprint"""
    chat_id = update.effective_chat.id
    active = db.get_active_sprint(chat_id)
    if not active:
        await update.message.reply_text("No sprint running right now. Watch this space!")
        return
    await update.message.reply_text(f"🏃 Active sprint: '{active['title']}' — go go go!")

from telegram import Update
from telegram.ext import ContextTypes

import config

RULES_PATH = "rules.md"


async def announce_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: /announce <message> — posts to the announcement chat."""
    if not config.is_admin(update.effective_user.id):
        await update.message.reply_text("This command is admin-only.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /announce Your announcement text here")
        return

    if not config.ANNOUNCEMENT_CHAT_ID:
        await update.message.reply_text(
            "No ANNOUNCEMENT_CHAT_ID is set in the environment yet — add it "
            "and restart the bot."
        )
        return

    text = " ".join(context.args)
    await context.bot.send_message(
        chat_id=config.ANNOUNCEMENT_CHAT_ID,
        message_thread_id=config.ANNOUNCEMENT_TOPIC_ID,
        text=f"📢 {text}",
    )
    await update.message.reply_text("Posted to the announcement board.")


async def rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Anyone: /rules — posts the community rules. Edit rules.md any time."""
    try:
        with open(RULES_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        # Strip the leading HTML comment block if present
        if content.strip().startswith("<!--"):
            content = content.split("-->", 1)[1].strip()
    except FileNotFoundError:
        content = "Rules haven't been set up yet — ask an admin."

    await update.message.reply_text(content)


async def drop_resource_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: /dropresource <text> — posts into the Resources topic.
    Same idea as /announce, just aimed at a different topic. Note: this
    posts text only — for files/videos, forward them directly into the
    Resources topic yourself, Herald can't relay uploaded files this way."""
    if not config.is_admin(update.effective_user.id):
        await update.message.reply_text("This command is admin-only.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /dropresource Your resource description or link here")
        return

    if not config.RESOURCE_TOPIC_ID:
        await update.message.reply_text(
            "No RESOURCE_TOPIC_ID is set in the environment yet — add it and restart the bot."
        )
        return

    text = " ".join(context.args)
    await context.bot.send_message(
        chat_id=config.ANNOUNCEMENT_CHAT_ID,  # same group, different topic
        message_thread_id=config.RESOURCE_TOPIC_ID,
        text=f"📚 {text}",
    )
    await update.message.reply_text("Dropped into the Resources topic.")

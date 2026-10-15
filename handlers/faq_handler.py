from telegram import Update
from telegram.ext import ContextTypes

import faq


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Herald is fully conversational in DMs — every message gets a real
    response, not just ones phrased as questions, so she feels like a
    presence rather than a search box. In groups she stays quieter: she
    only engages when directly @mentioned or replied to, but once
    addressed there, she responds to whatever was said, question or not."""
    if not update.message or not update.message.text:
        return

    text = update.message.text
    is_private = update.effective_chat.type == "private"
    bot_username = context.bot.username
    is_mentioned = bool(bot_username) and f"@{bot_username}" in text
    is_reply_to_bot = (
        update.message.reply_to_message
        and update.message.reply_to_message.from_user
        and update.message.reply_to_message.from_user.id == context.bot.id
    )

    # Group chats: only engage if directly addressed.
    if not is_private and not (is_mentioned or is_reply_to_bot):
        return

    clean_text = text.replace(f"@{bot_username}", "").strip() if bot_username else text

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    answer, source = faq.answer_question(clean_text, update.effective_user.first_name)
    await update.message.reply_text(answer)


async def handle_business_message(update, context):
    """Handle incoming messages from Telegram Business customers."""
    message = update.business_message

    if not message or not message.text:
        return

    connection_id = message.business_connection_id
    if not connection_id:
        return

    # Avoid responding to messages sent by the business account itself.
    if message.chat.type == "private" and message.from_user:
        if message.chat.id != message.from_user.id:
            return

    text = message.text.strip()
    if not text:
        return

    first_name = (
        message.from_user.first_name
        if message.from_user
        else "there"
    )

    try:
        await context.bot.send_chat_action(
            chat_id=message.chat_id,
            action="typing",
            business_connection_id=connection_id,
        )

        answer, source = faq.answer_question(text, first_name)

        await context.bot.send_message(
            chat_id=message.chat_id,
            text=answer,
            business_connection_id=connection_id,
        )

    except Exception:
    import logging
    logging.exception("Failed to handle a Telegram Business message")
        )


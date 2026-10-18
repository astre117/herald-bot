import asyncio
import html
import logging
import os
import re
from datetime import date

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

import config
import faq
import conversations
import payments
import settings

# Remembers which alerts were already sent today, so you don't get spammed.
_alerted = {}

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


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


# ---------------------------------------------------------------------------
# Control chat: alerts, Take over / Resume buttons, global off switch
# ---------------------------------------------------------------------------

async def _notify_admins(bot, text, reply_markup=None, parse_mode=None):
    for admin_id in config.ADMIN_USER_IDS:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
            )
        except Exception:
            logging.exception("Could not notify admin %s", admin_id)


async def _alert_once_a_day(bot, kind, text):
    today = date.today().isoformat()
    if _alerted.get(kind) == today:
        return
    _alerted[kind] = today
    await _notify_admins(bot, text)


async def _send_handoff(bot, chat_id, first_name, reason):
    recent = conversations.get_recent(chat_id, limit=6)
    lines = []
    for m in recent:
        who = "Customer" if m["role"] == "user" else "Herald"
        content = m["content"].replace("|||", " / ")
        if len(content) > 200:
            content = content[:200] + "..."
        lines.append(f"{who}: {html.escape(content)}")

    text = (
        f"Herald needs you: <b>{html.escape(first_name)}</b>\n"
        f"Reason: {html.escape(reason)}\n\n"
        + "\n".join(lines)
        + f'\n\n<a href="tg://user?id={chat_id}">Open chat</a>'
    )
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("Take over", callback_data=f"take:{chat_id}"),
        InlineKeyboardButton("Resume Herald", callback_data=f"resume:{chat_id}"),
    ]])
    await _notify_admins(bot, text, reply_markup=markup, parse_mode=ParseMode.HTML)


async def handle_control_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.data:
        return
    if not config.is_admin(query.from_user.id):
        await query.answer("Admins only.", show_alert=True)
        return

    action, _, raw_id = query.data.partition(":")
    try:
        chat_id = int(raw_id)
    except ValueError:
        await query.answer()
        return

    if action == "take":
        conversations.pause_chat(chat_id)
        await query.answer("Herald is silenced in this chat.")
    elif action == "resume":
        conversations.resume_chat(chat_id)
        await query.answer("Herald is back on in this chat.")
    else:
        await query.answer()


async def herald_off_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not config.is_admin(update.effective_user.id):
        return
    conversations.pause_chat(0)  # 0 = every chat
    await update.message.reply_text(
        "Herald is OFF in every chat. Send /heraldon to turn her back on."
    )


async def herald_on_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not config.is_admin(update.effective_user.id):
        return
    conversations.resume_chat(0)
    await update.message.reply_text("Herald is ON again.")


# ---------------------------------------------------------------------------
# Business (customer) messages
# ---------------------------------------------------------------------------

def _split_chunks(answer):
    """Split a reply on ||| into at most 3 non-empty chunks."""
    chunks = [c.strip() for c in answer.split("|||") if c.strip()]
    return chunks[:3] or [answer.strip()]


def _typing_delay(chunk):
    """1 to 3 seconds, longer for longer chunks."""
    return min(3.0, 1.0 + len(chunk) / 60)


async def _send_texts(context, chat_id, connection_id, chunks):
    """Sends each chunk as its own message with a typing pause."""
    last_id = None
    for chunk in chunks:
        await context.bot.send_chat_action(
            chat_id=chat_id,
            action="typing",
            business_connection_id=connection_id,
        )
        await asyncio.sleep(_typing_delay(chunk))
        sent = await context.bot.send_message(
            chat_id=chat_id,
            text=chunk,
            business_connection_id=connection_id,
        )
        last_id = sent.message_id
    return last_id


async def _deliver_materials(context, chat_id, connection_id, first_name, email):
    link = os.environ.get("MATERIALS_LINK", "")

    if not link:
        chunks = ["Thanks, I can see your payment.", "Let me bring Coach Create in to send your materials."]
        last_id = await _send_texts(context, chat_id, connection_id, chunks)
        conversations.save_message(chat_id, "assistant", "|||".join(chunks), last_id)
        await _send_handoff(
            context.bot, chat_id, first_name,
            f"Verified payment for {email} but MATERIALS_LINK is not set",
        )
        return

    chunks = [
        "Your payment is confirmed. Thank you!",
        f"Here are your materials: {link}",
        "Please keep them to yourself and don't share the link. Message me if anything doesn't open.",
    ]
    last_id = await _send_texts(context, chat_id, connection_id, chunks)

    # The link itself is never stored in the conversation history.
    conversations.save_message(
        chat_id,
        "assistant",
        "Your payment is confirmed. Thank you!|||[Herald sent the toolkit materials link]|||"
        "Please keep them to yourself and don't share the link.",
        last_id,
    )
    await _notify_admins(
        context.bot,
        f"Materials sent to {first_name} (payment email: {email}).",
    )


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
        chat_id = message.chat_id

        # Load earlier messages first, then save this one.
        history = conversations.get_recent(chat_id, limit=12)
        is_new = conversations.save_message(
            chat_id, "user", text, message.message_id
        )
        if not is_new:
            # Telegram sent this exact message twice. Ignore it.
            return

        # Global off switch (settings.txt, or /heraldoff)
        if not settings.is_on() or conversations.is_paused(0):
            logging.info("Herald is switched off; not replying")
            return

        # Per-chat pause (Take over button)
        if conversations.is_paused(chat_id):
            logging.info("Chat %s is paused; not replying", chat_id)
            return

        # Daily reply cap (settings.txt)
        if conversations.count_replies_today() >= settings.daily_cap():
            logging.warning("Daily reply cap reached; not replying")
            await _alert_once_a_day(
                context.bot,
                "cap",
                "Herald has hit today's reply cap and has gone quiet in all "
                "chats. Raise daily_reply_cap in settings.txt if you want "
                "her to continue.",
            )
            return

        # Payment claim: the buyer sent an email address.
        system_note = ""
        email_match = _EMAIL_RE.search(text)
        if email_match:
            email = email_match.group(0)
            result = await asyncio.to_thread(payments.claim_email, email, chat_id)

            if result == "ok":
                await _deliver_materials(
                    context, chat_id, connection_id, first_name, email
                )
                return

            if result == "taken":
                chunks = [
                    "I can see a payment for that email.",
                    "I need Coach Create to check one thing before I send your materials.",
                ]
                last_id = await _send_texts(context, chat_id, connection_id, chunks)
                conversations.save_message(
                    chat_id, "assistant", "|||".join(chunks), last_id
                )
                await _send_handoff(
                    context.bot, chat_id, first_name,
                    f"Payment email {email} was already claimed by another Telegram account",
                )
                return

            system_note = (
                "\n\n[System note, not from the customer: the email above was "
                "checked and no verified toolkit payment matches it. Do not say "
                "any payment is confirmed. Tell them you cannot see it yet, ask "
                "them to double-check the email used at checkout, mention it can "
                "take a few minutes after paying, and add a handoff tag.]"
            )

        await context.bot.send_chat_action(
            chat_id=chat_id,
            action="typing",
            business_connection_id=connection_id,
        )

        answer, source = faq.answer_question(text + system_note, first_name, history)
        chunks = _split_chunks(answer)

        last_sent_id = await _send_texts(context, chat_id, connection_id, chunks)

        # Saved with ||| between chunks so Claude keeps seeing the format.
        conversations.save_message(
            chat_id, "assistant", "|||".join(chunks), last_sent_id
        )

        # Tell the admins if Herald asked for a human.
        if source.startswith("handoff:"):
            await _send_handoff(
                context.bot, chat_id, first_name, source[len("handoff:"):]
            )

    except Exception as e:
        logging.exception("Failed to handle a Telegram Business message")
        if "credit balance" in str(e).lower():
            await _alert_once_a_day(
                context.bot,
                "credits",
                "Herald's Anthropic credits have run out, so she can't "
                "reply. Please top up your credits.",
            )

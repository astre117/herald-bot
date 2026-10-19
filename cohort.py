import asyncio

import conversations
import followups
import payments


async def handle_claim(context, chat_id, connection_id, first_name, email):
    """Called when a buyer sends an email that matched no toolkit payment.
    Returns True if it was a Cohort payment and has been handled."""
    from handlers import faq_handler as h  # imported here to avoid a loop

    result = await asyncio.to_thread(
        payments.claim_email_kinds, email, chat_id, (3, 4)
    )
    if result == "none":
        return False

    if result == "taken":
        chunks = [
            "I can see a payment for that email.",
            "I need Coach Create to check one thing before we go further.",
        ]
        reason = (
            f"Cohort payment email {email} was already claimed by another "
            "Telegram account"
        )
    else:
        chunks = [
            "I can see your Cohort payment. Thank you!",
            "Coach Create will confirm your spot and set up your access personally.",
        ]
        reason = (
            f"Cohort payment detected for {email}. Please confirm their spot "
            "and onboard them (Dravonis ID and group)"
        )

    last_id = await h._send_texts(context, chat_id, connection_id, chunks)
    conversations.save_message(chat_id, "assistant", "|||".join(chunks), last_id)
    await h._send_handoff(context.bot, chat_id, first_name, reason)

    if result == "ok":
        followups.set_status(chat_id, "enrolled")
    return True

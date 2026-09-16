from telegram import Update
from telegram.ext import ContextTypes, filters

import config
import faq


class WinsTopicFilter(filters.MessageFilter):
    """Matches only text messages posted inside the configured Wins &
    Testimonials topic. Built as its own filter (rather than checking
    inside the handler and silently returning) so that non-matching
    messages fall through cleanly to other handlers, like the general FAQ
    handler — instead of this handler swallowing every message in the
    group and blocking everything else."""

    def filter(self, message):
        if config.WINS_TOPIC_ID is None or not config.ANNOUNCEMENT_CHAT_ID:
            return False
        if str(message.chat_id) != str(config.ANNOUNCEMENT_CHAT_ID):
            return False
        return message.message_thread_id == config.WINS_TOPIC_ID


wins_topic_filter = WinsTopicFilter()


async def react_to_win(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fires on any text message in the Wins & Testimonials topic. Herald
    reacts with a short, specific celebration rather than a canned line."""
    if not update.message or not update.message.text:
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reaction = faq.celebrate_win(update.message.text, update.effective_user.first_name)
    await update.message.reply_text(reaction)

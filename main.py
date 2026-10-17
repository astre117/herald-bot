from telegram import BotCommand, BotCommandScopeDefault, BotCommandScopeChat
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)
import config
import db
import conversations
from keep_alive import keep_alive

import conversations
import conversations
import handlers.onboarding as onboarding
from handlers.onboarding import (
    welcome_new_member,
    assign_id_command,
    pending_students_command,
    add_ids_command,
    add_ids_file_command,
    id_pool_status_command,
    confirm_paid_command,
    my_status_command,
)
from handlers.announcements import announce_command, rules_command, drop_resource_command
from handlers.sprints import (
    start_sprint_command,
    end_sprint_command,
    sprint_status_command,
)
from handlers.reminders import (
    remind_in_command,
    remind_at_command,
    check_due_reminders,
)
from handlers.issues import (
    report_issue_command,
    issues_command,
    resolve_issue_command,
)
from handlers.wins import react_to_win, wins_topic_filter
from handlers.faq_handler import (
    handle_message,
    handle_business_message,
    handle_control_buttons,
    herald_off_command,
    herald_on_command,
)

STUDENT_COMMANDS = [
    BotCommand("start", "Say hello to Herald and get started"),
    BotCommand("mystatus", "Check your Dravonis ID and status"),
    BotCommand("rules", "See the community rules"),
    BotCommand("sprint", "Check if a sprint is active"),
    BotCommand("reportissue", "Report a Dravonis bug or problem"),
]

ADMIN_COMMANDS = STUDENT_COMMANDS + [
    BotCommand("announce", "Post to the announcement board"),
    BotCommand("dropresource", "Post something into the Resources topic"),
    BotCommand("addids", "Bulk-add Dravonis IDs to the pool"),
    BotCommand("idpool", "Check how many IDs are left"),
    BotCommand("confirmpaid", "Confirm payment and assign next ID"),
    BotCommand("assignid", "Manually assign a specific ID"),
    BotCommand("pending", "List students awaiting an ID"),
    BotCommand("startsprint", "Start a sprint"),
    BotCommand("endsprint", "End the active sprint"),
    BotCommand("remindin", "Set a reminder in X minutes"),
    BotCommand("remindat", "Set a reminder for a specific time"),
    BotCommand("issues", "List open reported issues"),
    BotCommand("resolveissue", "Mark an issue as resolved"),
]


async def setup_commands(app):
    """Runs once on startup. Sets a slim command menu for everyone by
    default, and a full menu (including admin commands) just for admins'
    private chats with the bot — so students never see admin-only clutter."""
    await app.bot.set_my_commands(STUDENT_COMMANDS, scope=BotCommandScopeDefault())

    for admin_id in config.ADMIN_USER_IDS:
        try:
            await app.bot.set_my_commands(
                ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=admin_id)
            )
        except Exception:
            # Admin hasn't started a private chat with the bot yet — their
            # scoped menu will be set the first time setup_commands reruns
            # after they do (e.g. next bot restart).
            print(f"Could not set admin command scope for {admin_id} (they may not have DM'd the bot yet)")


async def start_command(update, context):
    student = db.get_student(update.effective_user.id)

    if student and student["status"] == "pending_id":
        await onboarding.herald_intro_dm(context.bot, update.effective_user.id)
        return

    await update.message.reply_text(
        "Hey, I'm Herald! 👋 I keep this cohort running smoothly — "
        "onboarding, announcements, sprints, reminders, and answering "
        "whatever's on your mind. Consider me Dravonis's partner: Dravonis "
        "handles the writing craft, I handle everything around it. Ask me "
        "anything cohort-related, or just say hi."
    )


def main():
    db.init_db()
    conversations.init_conversations()

    seeded, skipped = db.seed_pool_from_file("seed_ids.txt")
    if seeded:
        print(f"Seeded {len(seeded)} Dravonis ID(s) into the pool from seed_ids.txt")
    keep_alive()

    app = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .post_init(setup_commands)
        .build()
    )

    # Onboarding
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    app.add_handler(CommandHandler("assignid", assign_id_command))
    app.add_handler(CommandHandler("pending", pending_students_command))
    app.add_handler(CommandHandler("addids", add_ids_command))
    app.add_handler(MessageHandler(filters.Document.ALL, add_ids_file_command))
    app.add_handler(CommandHandler("idpool", id_pool_status_command))
    app.add_handler(CommandHandler("confirmpaid", confirm_paid_command))
    app.add_handler(CommandHandler("mystatus", my_status_command))

    # Announcements
    app.add_handler(CommandHandler("announce", announce_command))
    app.add_handler(CommandHandler("dropresource", drop_resource_command))
    app.add_handler(CommandHandler("rules", rules_command))

    # Sprints
    app.add_handler(CommandHandler("startsprint", start_sprint_command))
    app.add_handler(CommandHandler("endsprint", end_sprint_command))
    app.add_handler(CommandHandler("sprint", sprint_status_command))

    # Reminders
    app.add_handler(CommandHandler("remindin", remind_in_command))
    app.add_handler(CommandHandler("remindat", remind_at_command))

    # Issue reporting
    app.add_handler(CommandHandler("reportissue", report_issue_command))
    app.add_handler(CommandHandler("issues", issues_command))
    app.add_handler(CommandHandler("resolveissue", resolve_issue_command))

    # Misc
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("heraldoff", herald_off_command))
    app.add_handler(CommandHandler("heraldon", herald_on_command))
    app.add_handler(CallbackQueryHandler(handle_control_buttons, pattern=r"^(take|resume):"))

    # Wins & Testimonials — must come BEFORE the FAQ catch-all so wins
    # posts get Herald's celebration instead of a generic FAQ attempt
    app.add_handler(MessageHandler(filters.TEXT & wins_topic_filter, react_to_win))

    # FAQ — catch-all text handler, must be added last
    app.add_handler(
    MessageHandler(
        filters.UpdateType.BUSINESS_MESSAGE,
        handle_business_message,
    )
)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Background job: check for due reminders every 30 seconds
    app.job_queue.run_repeating(check_due_reminders, interval=30, first=10)

    print("Bot is running...")
    app.run_polling(
    allowed_updates=[
        "message",
        "business_connection",
        "business_message",
        "callback_query",
    ]
)


if __name__ == "__main__":
    main()

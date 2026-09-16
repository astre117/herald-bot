from telegram import Update
from telegram.ext import ContextTypes

import db
import config


async def report_issue_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Any student: /reportissue <description>"""
    if not context.args:
        await update.message.reply_text(
            "Usage: /reportissue <what's wrong>\n"
            "Example: /reportissue Dravonis won't load my outline"
        )
        return

    description = " ".join(context.args)
    user = update.effective_user

    issue_id = db.log_issue(user.id, user.username, user.full_name, description)

    await update.message.reply_text(
        "Got it — I've logged this and flagged it for an admin. They'll follow up with you directly. 🙏"
    )

    if config.ADMIN_NOTIFY_CHAT_ID:
        await context.bot.send_message(
            chat_id=config.ADMIN_NOTIFY_CHAT_ID,
            text=(
                f"🚩 Issue #{issue_id} reported by {user.full_name} "
                f"(@{user.username or 'no_username'}):\n\n{description}"
            ),
        )


async def issues_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: /issues — lists open issues."""
    if not config.is_admin(update.effective_user.id):
        await update.message.reply_text("This command is admin-only.")
        return

    open_issues = db.list_open_issues()
    if not open_issues:
        await update.message.reply_text("No open issues right now. 🎉")
        return

    lines = [
        f"#{i['id']} — {i['full_name']} (@{i['username'] or i['telegram_id']}): {i['description']}"
        for i in open_issues
    ]
    await update.message.reply_text("Open issues:\n" + "\n".join(lines))


async def resolve_issue_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: /resolveissue <id>"""
    if not config.is_admin(update.effective_user.id):
        await update.message.reply_text("This command is admin-only.")
        return

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /resolveissue <issue_id>")
        return

    db.resolve_issue(int(context.args[0]))
    await update.message.reply_text(f"Marked issue #{context.args[0]} as resolved.")

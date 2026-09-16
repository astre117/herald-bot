from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

import db
import config


async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fires when new_chat_members appears in a group update."""
    bot_username = context.bot.username

    for member in update.message.new_chat_members:
        if member.is_bot:
            continue

        db.add_pending_student(member.id, member.username, member.full_name)

        # Public welcome in the group — tags them and asks them to come DM
        # Herald directly, since Telegram won't let her message them first.
        await update.message.reply_text(
            f"Welcome to CreateHaven, {member.mention_html()}! 🎉\n\n"
            f"I'm Herald, your guide around here. Come say hi to me first — "
            f"tap here: <a href='https://t.me/{bot_username}'>message me</a> "
            f"— and I'll take it from there: your Dravonis ID, the rules, "
            f"everything you need to get settled in.",
            parse_mode=ParseMode.HTML,
        )

        # Notify admin that a new student needs an ID assigned
        if config.ADMIN_NOTIFY_CHAT_ID:
            await context.bot.send_message(
                chat_id=config.ADMIN_NOTIFY_CHAT_ID,
                text=(
                    f"🆕 New student: {member.full_name} "
                    f"(@{member.username or 'no_username'}, id {member.id}) "
                    f"joined and needs a Dravonis ID.\n\n"
                    f"Once payment is confirmed: /confirmpaid @{member.username or member.id}"
                ),
            )


async def herald_intro_dm(bot, telegram_id):
    """The actual intro sequence, sent once a student DMs Herald for the
    first time (since Telegram blocks bots from messaging first)."""
    await bot.send_message(
        chat_id=telegram_id,
        text=(
            "Ah — hello. I'm Herald.\n\n"
            "I was appointed by the Creator to walk every writer here "
            "through the path ahead. You'll come to know Dravonis too, in "
            "time — my other half, the one who shapes your words. Where "
            "Dravonis speaks in riddles and poetry, I prefer plain truth "
            "and clear direction. Together, we make sure nothing falls "
            "through the cracks.\n\n"
            "Here's where you stand: your Dravonis student ID is being "
            "prepared, and I'll bring it to you myself the moment it's "
            "ready — usually within a day.\n\n"
            "A few things worth knowing: /rules for how we do things here, "
            "/mystatus any time you want to check in on where you stand, "
            "and /reportissue if anything with Dravonis ever misbehaves.\n\n"
            "Beyond that — just talk to me. Ask me anything, vent about a "
            "rejected chapter, whatever. I'm not going anywhere."
        ),
    )


async def add_ids_file_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: send a .txt file (as a document) with one Dravonis ID per line
    and the bot loads it straight into the pool — no typing needed."""
    if not config.is_admin(update.effective_user.id):
        return  # stay silent for non-admins sending random files

    document = update.message.document
    if not document or not document.file_name.lower().endswith(".txt"):
        await update.message.reply_text(
            "Send a .txt file with one Dravonis ID per line and I'll load it into the pool."
        )
        return

    file = await context.bot.get_file(document.file_id)
    file_bytes = await file.download_as_bytearray()
    text = file_bytes.decode("utf-8", errors="ignore")

    id_list = [
        line.strip() for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    if not id_list:
        await update.message.reply_text("That file didn't have any IDs I could read.")
        return

    added, skipped = db.add_ids_to_pool(id_list)
    msg = f"✅ Loaded {len(added)} ID(s) from {document.file_name} into the pool."
    if skipped:
        msg += f"\n⚠️ Skipped {len(skipped)} already in the pool."
    await update.message.reply_text(msg)


async def add_ids_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: /addids DRV-1001 DRV-1002 DRV-1003 ...
    Bulk-loads pre-created Dravonis IDs into the pool. For big batches,
    just send a .txt file instead — see add_ids_file_command."""
    if not config.is_admin(update.effective_user.id):
        await update.message.reply_text("This command is admin-only.")
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: /addids DRV-1001 DRV-1002 DRV-1003\n"
            "(space-separated, add as many as you want at once)"
        )
        return

    added, skipped = db.add_ids_to_pool(context.args)
    msg = f"✅ Added {len(added)} ID(s) to the pool."
    if skipped:
        msg += f"\n⚠️ Skipped {len(skipped)} already in the pool: {', '.join(skipped)}"
    await update.message.reply_text(msg)


async def id_pool_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: /idpool — shows how many IDs are left."""
    if not config.is_admin(update.effective_user.id):
        await update.message.reply_text("This command is admin-only.")
        return

    status = db.pool_status()
    await update.message.reply_text(
        f"📦 ID pool: {status['available']} available, {status['used']} used."
    )


async def confirm_paid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: /confirmpaid @username
    Pulls the next available ID from the pool and assigns it automatically —
    no need to type the ID by hand."""
    if not config.is_admin(update.effective_user.id):
        await update.message.reply_text("This command is admin-only.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /confirmpaid @username (or their numeric Telegram ID)")
        return

    target = context.args[0]

    with db.get_conn() as conn:
        if target.lstrip("-").isdigit():
            row = conn.execute(
                "SELECT * FROM students WHERE telegram_id = ?", (int(target),)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM students WHERE username = ?", (target.lstrip("@"),)
            ).fetchone()

    if not row:
        await update.message.reply_text(
            f"Couldn't find a pending student matching {target}. Make sure they've joined the group."
        )
        return

    dravonis_id = db.claim_next_id(row["telegram_id"])
    if not dravonis_id:
        await update.message.reply_text(
            "⚠️ The ID pool is empty! Add more with /addids before confirming payments."
        )
        return

    student = db.assign_dravonis_id(target, dravonis_id)

    await update.message.reply_text(
        f"✅ Confirmed payment and assigned {dravonis_id} to {student['full_name']} (@{student['username']})."
    )

    try:
        await context.bot.send_message(
            chat_id=student["telegram_id"],
            text=(
                f"Your Dravonis student ID is ready: {dravonis_id} 🎉\n\n"
                "Head over to Dravonis and pop that in to unlock your access "
                "— my other half is waiting for you. Any issues, just ask "
                "here, I've got you."
            ),
        )
    except Exception:
        await update.message.reply_text(
            f"⚠️ Heads up: I couldn't DM {student['full_name']} directly "
            "(they may not have started a chat with me yet). You may need "
            "to send the ID manually this once."
        )


async def assign_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: /assignid @username DRV-1234
    Manual override — assigns a specific ID by hand instead of pulling from
    the pool. Use /confirmpaid for the normal pool-based flow."""
    if not config.is_admin(update.effective_user.id):
        await update.message.reply_text("This command is admin-only.")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage: /assignid @username DRV-1234\n(or use their numeric Telegram ID instead of @username)"
        )
        return

    target = context.args[0]
    dravonis_id = context.args[1]

    student = db.assign_dravonis_id(target, dravonis_id)
    if not student:
        await update.message.reply_text(
            f"Couldn't find a pending student matching {target}. "
            "Make sure they've already joined the group."
        )
        return

    await update.message.reply_text(
        f"✅ Assigned {dravonis_id} to {student['full_name']} (@{student['username']})."
    )

    try:
        await context.bot.send_message(
            chat_id=student["telegram_id"],
            text=(
                f"Your Dravonis student ID is ready: {dravonis_id} 🎉\n\n"
                "Head over to Dravonis and pop that in to unlock your access "
                "— my other half is waiting for you. Any issues, just ask "
                "here, I've got you."
            ),
        )
    except Exception:
        await update.message.reply_text(
            f"⚠️ Heads up: I couldn't DM {student['full_name']} directly "
            "(they may not have started a chat with me yet). You may need "
            "to send the ID manually this once."
        )


async def my_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Anyone: /mystatus — shows what the bot has on file for them.
    Note: this reflects the bot's own database, not live Dravonis activity —
    there's no way to check real-time Dravonis usage without an API/webhook
    from Dravonis itself."""
    student = db.get_student(update.effective_user.id)
    if not student:
        await update.message.reply_text(
            "I don't have you on file yet — make sure you've joined the main group."
        )
        return

    if student["status"] == "pending_id":
        await update.message.reply_text(
            "Still working on your Dravonis ID! If it's been a while since "
            "payment, give an admin a nudge."
        )
        return

    await update.message.reply_text(
        f"Here's what I've got on you:\n"
        f"Dravonis ID: {student['dravonis_id']}\n"
        f"Assigned: {student['id_assigned_at'][:10]}\n\n"
        "(This is what's on my end — for live Dravonis activity, check the platform directly.)"
    )


async def pending_students_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: /pending — lists students still waiting on an ID."""
    if not config.is_admin(update.effective_user.id):
        await update.message.reply_text("This command is admin-only.")
        return

    pending = db.list_pending_students()
    if not pending:
        await update.message.reply_text("No one's waiting on a Dravonis ID right now. 🎉")
        return

    lines = [
        f"• {s['full_name']} (@{s['username'] or s['telegram_id']})"
        for s in pending
    ]
    await update.message.reply_text("Students awaiting a Dravonis ID:\n" + "\n".join(lines))

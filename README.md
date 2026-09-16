# CreateHaven Cohort Bot

A Telegram bot for running the CreateHaven cohort community: onboarding +
Dravonis ID delivery, announcements, sprints, reminders, and an
AI-backed FAQ.

## What it does

- **Onboarding**: when someone joins the group, the bot welcomes them,
  DMs them, and pings you (the admin) that a Dravonis ID needs assigning.
  You run one command, the bot delivers the ID.
- **Announcements**: `/announce <text>` posts to your announcement chat.
- **Sprints**: `/startsprint <title>`, `/endsprint`, `/sprint` (status check).
- **Reminders**: `/remindin <minutes> <text>` or `/remindat <date> <time> <text>`.
- **FAQ**: checks `knowledge_base.md` for a close match first, then falls
  back to Claude for anything else — grounded in your knowledge base so it
  doesn't make things up about cohort specifics.

## 1. Create the bot on Telegram

1. Message **@BotFather** on Telegram.
2. Send `/newbot`, follow the prompts, and save the token it gives you.
   - Give it the display name **Herald** when BotFather asks (or rename
     later with `/setname`).
   - Set her avatar with `/setuserpic` once you have the image ready.
3. Send `/setprivacy` → select your bot → **Disable** (so it can read
   messages in group chats, not just commands — needed for the FAQ to work
   in groups).
4. Add the bot to your cohort group as an **admin** (needed to see new
   member joins and, if the announcement chat is a channel, to post there).

You don't need to run `/setcommands` in BotFather — the bot sets its own
command menus automatically on startup: a slim student-facing menu for
everyone by default, and a full menu (including admin commands) just for
each admin's private chat with the bot. **One catch**: each admin needs to
have DM'd the bot at least once (send `/start`) before their full admin
menu can be set — if you add a new admin later, have them message the bot
once, then restart the bot so it picks up their scoped menu.

## 2. Get your IDs

- **Your Telegram user ID**: message **@userinfobot**, it replies with your ID.
- **Group/channel chat ID**: add **@RawDataBot** to the chat temporarily,
  it'll post the chat ID, then remove it.
- **Topic (thread) ID**, if you use Telegram's Topics feature and want
  announcements to land in a specific tab: on Telegram Desktop or Web,
  right-click the topic's name in the sidebar → **Copy Link**. The link
  looks like `https://t.me/c/1234567890/45` — that last number (`45` here)
  is the Topic ID. If you're on mobile only, ask someone with desktop
  access to grab this one link for you, or open web.telegram.org in a
  browser instead.

## 3. Set up on Replit

1. Create a new Replit project → **Import from GitHub** (if you push this
   folder to a repo) or just create a **Python** Repl and upload these files.
2. In Replit's **Secrets** tab (padlock icon), add each variable from
   `.env.example`:
   - `TELEGRAM_BOT_TOKEN`
   - `ANTHROPIC_API_KEY`
   - `ADMIN_USER_IDS`
   - `ANNOUNCEMENT_CHAT_ID`
   - `ANNOUNCEMENT_TOPIC_ID` (only if announcements go in a specific Topic — skip this one otherwise)
   - `RESOURCE_TOPIC_ID` (only if you want to use `/dropresource` — skip otherwise)
   - `WINS_TOPIC_ID` (only if you want Herald auto-celebrating in Wins & Testimonials — skip otherwise)
   - `ADMIN_NOTIFY_CHAT_ID`
3. Replit auto-installs from `requirements.txt` on first run. If it
   doesn't, open the Shell tab and run:
   ```
   pip install -r requirements.txt
   ```
4. Click **Run**. You should see `Bot is running...` in the console.

## 4. Keep it always on

Replit's free tier sleeps a Repl after inactivity. Two options:

- **Paid**: turn on "Always On" for the Repl in Replit's settings — simplest,
  no extra setup.
- **Free**: this project includes `keep_alive.py`, which spins up a tiny
  web page. Use a free service like **UptimeRobot** to ping your Repl's
  URL every 5 minutes, which keeps it from sleeping. Your Repl's URL shows
  up in the webview panel once you hit Run.

## 5. Editing the FAQ knowledge base

Open `knowledge_base.md` any time and add more `Q:` / `A:` pairs in the
same format. No restart needed for Replit to pick up file changes on the
next question — it's read fresh each time.

## 6. Admin commands cheat sheet

| Command | Who | What it does |
|---|---|---|
| `/addids DRV-1001 DRV-1002 ...` | Admin | Bulk-loads pre-created Dravonis IDs into the pool |
| *(send a .txt file)* | Admin | Drop a file with one ID per line — loaded automatically, no command needed |
| `/idpool` | Admin | Shows how many IDs are available/used |
| `/confirmpaid @username` | Admin | Auto-assigns the next pool ID and DMs the student — no typing an ID by hand |
| `/assignid @username DRV-1234` | Admin | Manual override — assigns one specific ID by hand |
| `/pending` | Admin | Lists students still waiting on an ID |
| `/mystatus` | Anyone | Shows what the bot has on file (their own Dravonis ID + status) |
| `/rules` | Anyone | Posts the community rules |
| `/announce <text>` | Admin | Posts to the announcement chat |
| `/dropresource <text>` | Admin | Posts into the Resources topic |
| `/startsprint <title>` | Admin | Starts a sprint in the current chat |
| `/endsprint` | Admin | Ends the active sprint |
| `/sprint` | Anyone | Checks if a sprint is active |
| `/remindin <mins> <text>` | Admin | Reminder N minutes from now |
| `/remindat <YYYY-MM-DD> <HH:MM> <text>` | Admin | Reminder at a specific UTC time |
| `/reportissue <text>` | Anyone | Logs a problem (e.g. Dravonis bug) and notifies you |
| `/issues` | Admin | Lists open reported issues |
| `/resolveissue <id>` | Admin | Marks an issue as resolved |

## Notes / things to know

- **New-member DMs can fail silently.** Telegram blocks bots from DMing
  someone who hasn't started a chat with the bot first. If that happens,
  the bot still posts in the group and pings you — you may occasionally
  need to nudge a student to press "Start" on the bot's DM once.
- **Batch ID workflow**: for a big batch, just send the bot a `.txt` file
  (one ID per line) as a document, in your DM with it or in the admin
  chat — it reads and loads it into the pool automatically, no command
  needed. `/addids DRV-1001 DRV-2002` still works for typing a few in by
  hand. Then `/confirmpaid @username` pulls the next available one
  automatically per student. `/assignid` still exists for one-off manual
  overrides.
- **`/mystatus` only reflects the bot's own database** — it can't check
  live Dravonis activity, since Dravonis doesn't expose an API/webhook the
  bot can query. It just shows students what ID they were assigned and when.
- **Topics**: Herald automatically stays in whatever topic a conversation
  is already happening in — if someone @mentions her or replies to her in
  the General topic (or any topic), her reply lands right back in that
  same topic, no setup needed. The only things that need a specific Topic
  ID configured are ones where SHE initiates the post rather than
  replying: `/announce` (needs `ANNOUNCEMENT_TOPIC_ID`) and
  `/dropresource` (needs `RESOURCE_TOPIC_ID`). Scheduled reminders also
  remember which topic they were set from and land back there.
- **`/dropresource` posts text only** — for files, videos, or PDFs, just
  forward them into the Resources topic yourself; Herald can't relay
  uploaded files through this command.
- **Wins & Testimonials auto-celebration**: unlike everything else, this
  one needs no command at all — set `WINS_TOPIC_ID` and Herald
  automatically reacts to every text message posted in that topic with a
  short, specific celebration (she reads what was actually written, not a
  canned "congrats!"). If that topic is closed to students-only-posting
  and you'd rather open it up so students post their own wins directly,
  that's a Telegram permission setting on the topic itself, nothing to
  change in the bot.
- **Community rules** live in `rules.md`, edit it like the knowledge base.
  `/rules` posts it as-is to whoever asks.
- **Reminder times are UTC.** Adjust for your timezone (Lagos is UTC+1)
  when scheduling with `/remindat`.
- **The FAQ only responds to what looks like a question**, and only in
  DMs, when the bot is @mentioned, or when someone replies to one of its
  messages — so it won't spam every group message.
- **Database**: everything (students, reminders, sprints) lives in
  `cohort_bot.db`, a SQLite file that persists across restarts on Replit.
  Worth backing it up occasionally (Replit's file panel → download).

## Extending this later

Some natural next additions once this is running smoothly:
- Payment-status gating (auto-mute/notify on missed installment payments)
- Weekly digest of sprint activity and engagement stats
- Slash command for students to self-check their Dravonis ID status

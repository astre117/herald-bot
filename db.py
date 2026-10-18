"""
Lightweight SQLite persistence layer.
Replit's filesystem persists across restarts within the same Repl, so a
local file (cohort_bot.db) is fine here — no external database needed.
"""
import sqlite3
from datetime import datetime
from contextlib import contextmanager

import os
import shutil

_DATA_DIR = os.environ.get("DATA_DIR", "")
if _DATA_DIR:
    os.makedirs(_DATA_DIR, exist_ok=True)
    DB_PATH = os.path.join(_DATA_DIR, "cohort_bot.db")
    # First run on the volume: start from the copy stored in the repo.
    if not os.path.exists(DB_PATH) and os.path.exists("cohort_bot.db"):
        shutil.copy("cohort_bot.db", DB_PATH)
else:
    DB_PATH = "cohort_bot.db"



@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS students (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                joined_at TEXT,
                dravonis_id TEXT,
                id_assigned_at TEXT,
                status TEXT DEFAULT 'pending_id'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                thread_id INTEGER,
                message TEXT,
                run_at TEXT,
                created_by INTEGER,
                sent INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS id_pool (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dravonis_id TEXT UNIQUE,
                added_at TEXT,
                used INTEGER DEFAULT 0,
                used_by INTEGER,
                used_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS issues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                username TEXT,
                full_name TEXT,
                description TEXT,
                reported_at TEXT,
                status TEXT DEFAULT 'open'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sprints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                chat_id INTEGER,
                started_at TEXT,
                ended_at TEXT,
                status TEXT DEFAULT 'active'
            )
        """)


# ---------- Students ----------

def add_pending_student(telegram_id, username, full_name):
    with get_conn() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO students
               (telegram_id, username, full_name, joined_at, status)
               VALUES (?, ?, ?, ?, 'pending_id')""",
            (telegram_id, username, full_name, datetime.utcnow().isoformat()),
        )


def assign_dravonis_id(username_or_id, dravonis_id):
    """Accepts either an @username or a numeric telegram_id as a string."""
    with get_conn() as conn:
        if username_or_id.lstrip("-").isdigit():
            row = conn.execute(
                "SELECT * FROM students WHERE telegram_id = ?",
                (int(username_or_id),),
            ).fetchone()
        else:
            uname = username_or_id.lstrip("@")
            row = conn.execute(
                "SELECT * FROM students WHERE username = ?", (uname,)
            ).fetchone()

        if not row:
            return None

        conn.execute(
            """UPDATE students SET dravonis_id = ?, id_assigned_at = ?, status = 'active'
               WHERE telegram_id = ?""",
            (dravonis_id, datetime.utcnow().isoformat(), row["telegram_id"]),
        )
        return dict(row)


def get_student(telegram_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM students WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        return dict(row) if row else None


def list_pending_students():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM students WHERE status = 'pending_id'"
        ).fetchall()
        return [dict(r) for r in rows]


# ---------- Reminders ----------

def add_reminder(chat_id, message, run_at_iso, created_by, thread_id=None):
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO reminders (chat_id, thread_id, message, run_at, created_by)
               VALUES (?, ?, ?, ?, ?)""",
            (chat_id, thread_id, message, run_at_iso, created_by),
        )
        return cur.lastrowid


def get_due_reminders(now_iso):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM reminders WHERE run_at <= ? AND sent = 0",
            (now_iso,),
        ).fetchall()
        return [dict(r) for r in rows]


def mark_reminder_sent(reminder_id):
    with get_conn() as conn:
        conn.execute("UPDATE reminders SET sent = 1 WHERE id = ?", (reminder_id,))


# ---------- ID Pool (batch-created Dravonis IDs) ----------

def seed_pool_from_file(path="seed_ids.txt"):
    """Runs on startup. Reads one Dravonis ID per line (blank lines and
    lines starting with # are ignored) and loads any new ones into the
    pool. Safe to run every restart — duplicates are skipped automatically."""
    import os
    if not os.path.exists(path):
        return [], []

    with open(path, "r", encoding="utf-8") as f:
        ids = [
            line.strip() for line in f
            if line.strip() and not line.strip().startswith("#")
        ]
    return add_ids_to_pool(ids)


def add_ids_to_pool(id_list):
    """Bulk-adds IDs, skipping any duplicates already in the pool."""
    added, skipped = [], []
    with get_conn() as conn:
        for dravonis_id in id_list:
            dravonis_id = dravonis_id.strip()
            if not dravonis_id:
                continue
            try:
                conn.execute(
                    "INSERT INTO id_pool (dravonis_id, added_at) VALUES (?, ?)",
                    (dravonis_id, datetime.utcnow().isoformat()),
                )
                added.append(dravonis_id)
            except sqlite3.IntegrityError:
                skipped.append(dravonis_id)
    return added, skipped


def pool_status():
    with get_conn() as conn:
        available = conn.execute(
            "SELECT COUNT(*) as c FROM id_pool WHERE used = 0"
        ).fetchone()["c"]
        used = conn.execute(
            "SELECT COUNT(*) as c FROM id_pool WHERE used = 1"
        ).fetchone()["c"]
        return {"available": available, "used": used}


def claim_next_id(telegram_id):
    """Pulls the oldest unused ID from the pool and marks it used. Returns
    the dravonis_id string, or None if the pool is empty."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM id_pool WHERE used = 0 ORDER BY id ASC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE id_pool SET used = 1, used_by = ?, used_at = ? WHERE id = ?",
            (telegram_id, datetime.utcnow().isoformat(), row["id"]),
        )
        return row["dravonis_id"]


# ---------- Issues ----------

def log_issue(telegram_id, username, full_name, description):
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO issues (telegram_id, username, full_name, description, reported_at)
               VALUES (?, ?, ?, ?, ?)""",
            (telegram_id, username, full_name, description, datetime.utcnow().isoformat()),
        )
        return cur.lastrowid


def list_open_issues():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM issues WHERE status = 'open' ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def resolve_issue(issue_id):
    with get_conn() as conn:
        conn.execute("UPDATE issues SET status = 'resolved' WHERE id = ?", (issue_id,))


# ---------- Sprints ----------

def start_sprint(title, chat_id):
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO sprints (title, chat_id, started_at, status)
               VALUES (?, ?, ?, 'active')""",
            (title, chat_id, datetime.utcnow().isoformat()),
        )
        return cur.lastrowid


def end_active_sprint(chat_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM sprints WHERE chat_id = ? AND status = 'active' ORDER BY id DESC LIMIT 1",
            (chat_id,),
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE sprints SET status = 'ended', ended_at = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), row["id"]),
        )
        return dict(row)


def get_active_sprint(chat_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM sprints WHERE chat_id = ? AND status = 'active' ORDER BY id DESC LIMIT 1",
            (chat_id,),
        ).fetchone()
        return dict(row) if row else None

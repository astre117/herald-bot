import sqlite3
from contextlib import closing

import db


def _conn():
    return sqlite3.connect(db.DB_PATH)


def init_conversations():
    with closing(_conn()) as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                tg_message_id INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS ux_conv_msg
            ON conversations(chat_id, role, tg_message_id)
            WHERE tg_message_id IS NOT NULL
        """)
        c.execute("CREATE INDEX IF NOT EXISTS ix_conv_chat ON conversations(chat_id, id)")
        c.commit()


def save_message(chat_id, role, content, tg_message_id=None):
    """Returns False if this exact Telegram message was already saved."""
    try:
        with closing(_conn()) as c:
            c.execute(
                "INSERT INTO conversations (chat_id, role, content, tg_message_id) VALUES (?, ?, ?, ?)",
                (chat_id, role, content, tg_message_id),
            )
            c.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def get_recent(chat_id, limit=12):
    with closing(_conn()) as c:
        rows = c.execute(
            "SELECT role, content FROM conversations WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
            (chat_id, limit),
        ).fetchall()
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]


def count_replies_today():
    with closing(_conn()) as c:
        row = c.execute(
            "SELECT COUNT(*) FROM conversations "
            "WHERE role = 'assistant' AND date(created_at) = date('now')"
        ).fetchone()
    return row[0]


def _paused_conn():
    c = _conn()
    c.execute(
        "CREATE TABLE IF NOT EXISTS paused_chats ("
        "chat_id INTEGER PRIMARY KEY, "
        "paused_at TEXT DEFAULT CURRENT_TIMESTAMP)"
    )
    return c


def pause_chat(chat_id):
    with closing(_paused_conn()) as c:
        c.execute("INSERT OR IGNORE INTO paused_chats (chat_id) VALUES (?)", (chat_id,))
        c.commit()


def resume_chat(chat_id):
    with closing(_paused_conn()) as c:
        c.execute("DELETE FROM paused_chats WHERE chat_id = ?", (chat_id,))
        c.commit()


def is_paused(chat_id):
    with closing(_paused_conn()) as c:
        row = c.execute("SELECT 1 FROM paused_chats WHERE chat_id = ?", (chat_id,)).fetchone()
    return row is not None

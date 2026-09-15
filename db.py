import sqlite3
import threading
import os
import datetime

import config

_lock = threading.Lock()
_conn = None


def _now():
    return datetime.datetime.utcnow().isoformat()


def get_conn():
    global _conn
    if _conn is None:
        os.makedirs(os.path.dirname(config.DATABASE_PATH) or ".", exist_ok=True)
        _conn = sqlite3.connect(config.DATABASE_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
    return _conn


def init_db():
    with _lock:
        conn = get_conn()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                is_banned INTEGER DEFAULT 0,
                is_admin INTEGER DEFAULT 0,
                model TEXT,
                tts_enabled INTEGER DEFAULT 0,
                message_count INTEGER DEFAULT 0,
                image_count INTEGER DEFAULT 0,
                file_count INTEGER DEFAULT 0,
                created_at TEXT,
                last_active TEXT
            );

            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                role TEXT,
                content TEXT,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS broadcast_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message TEXT,
                created_at TEXT,
                sent INTEGER DEFAULT 0,
                total_sent INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level TEXT,
                message TEXT,
                created_at TEXT
            );
            """
        )
        conn.commit()


# ---------------- users ----------------

def get_or_create_user(telegram_id, username=None, first_name=None):
    with _lock:
        conn = get_conn()
        row = conn.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
        if row is None:
            is_admin = 1 if telegram_id in config.ADMIN_IDS else 0
            conn.execute(
                "INSERT INTO users (telegram_id, username, first_name, is_admin, created_at, last_active) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (telegram_id, username, first_name, is_admin, _now(), _now()),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
        else:
            conn.execute(
                "UPDATE users SET username=?, first_name=?, last_active=? WHERE telegram_id=?",
                (username, first_name, _now(), telegram_id),
            )
            conn.commit()
        return dict(row)


def is_banned(telegram_id):
    conn = get_conn()
    row = conn.execute("SELECT is_banned FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
    return bool(row and row["is_banned"])


def is_admin(telegram_id):
    if telegram_id in config.ADMIN_IDS:
        return True
    conn = get_conn()
    row = conn.execute("SELECT is_admin FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
    return bool(row and row["is_admin"])


def set_ban(telegram_id, banned: bool):
    with _lock:
        conn = get_conn()
        conn.execute("UPDATE users SET is_banned=? WHERE telegram_id=?", (1 if banned else 0, telegram_id))
        conn.commit()


def set_admin(telegram_id, admin: bool):
    with _lock:
        conn = get_conn()
        conn.execute("UPDATE users SET is_admin=? WHERE telegram_id=?", (1 if admin else 0, telegram_id))
        conn.commit()


def set_user_model(telegram_id, model):
    with _lock:
        conn = get_conn()
        conn.execute("UPDATE users SET model=? WHERE telegram_id=?", (model, telegram_id))
        conn.commit()


def get_user_model(telegram_id):
    conn = get_conn()
    row = conn.execute("SELECT model FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
    if row and row["model"]:
        return row["model"]
    return get_setting("default_model", config.ANYMODEL_CHAT_MODEL)


def toggle_tts(telegram_id):
    with _lock:
        conn = get_conn()
        row = conn.execute("SELECT tts_enabled FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
        new_val = 0 if (row and row["tts_enabled"]) else 1
        conn.execute("UPDATE users SET tts_enabled=? WHERE telegram_id=?", (new_val, telegram_id))
        conn.commit()
        return bool(new_val)


def tts_enabled(telegram_id):
    conn = get_conn()
    row = conn.execute("SELECT tts_enabled FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
    return bool(row and row["tts_enabled"])


def bump_counter(telegram_id, field):
    assert field in ("message_count", "image_count", "file_count")
    with _lock:
        conn = get_conn()
        conn.execute(
            f"UPDATE users SET {field} = {field} + 1, last_active=? WHERE telegram_id=?",
            (_now(), telegram_id),
        )
        conn.commit()


def list_users(limit=200, offset=0, search=None):
    conn = get_conn()
    if search:
        rows = conn.execute(
            "SELECT * FROM users WHERE CAST(telegram_id AS TEXT) LIKE ? OR username LIKE ? "
            "ORDER BY last_active DESC LIMIT ? OFFSET ?",
            (f"%{search}%", f"%{search}%", limit, offset),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM users ORDER BY last_active DESC LIMIT ? OFFSET ?", (limit, offset)
        ).fetchall()
    return [dict(r) for r in rows]


def all_user_ids():
    conn = get_conn()
    rows = conn.execute("SELECT telegram_id FROM users WHERE is_banned=0").fetchall()
    return [r["telegram_id"] for r in rows]


def get_stats():
    conn = get_conn()
    total_users = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
    banned = conn.execute("SELECT COUNT(*) c FROM users WHERE is_banned=1").fetchone()["c"]
    total_messages = conn.execute("SELECT SUM(message_count) c FROM users").fetchone()["c"] or 0
    total_images = conn.execute("SELECT SUM(image_count) c FROM users").fetchone()["c"] or 0
    total_files = conn.execute("SELECT SUM(file_count) c FROM users").fetchone()["c"] or 0
    today = datetime.date.today().isoformat()
    active_today = conn.execute(
        "SELECT COUNT(*) c FROM users WHERE last_active LIKE ?", (f"{today}%",)
    ).fetchone()["c"]
    return {
        "total_users": total_users,
        "banned": banned,
        "total_messages": total_messages,
        "total_images": total_images,
        "total_files": total_files,
        "active_today": active_today,
    }


# ---------------- conversations ----------------

def add_message(telegram_id, role, content):
    with _lock:
        conn = get_conn()
        conn.execute(
            "INSERT INTO conversations (telegram_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (telegram_id, role, content, _now()),
        )
        conn.commit()


def get_history(telegram_id, limit=None):
    limit = limit or config.HISTORY_LIMIT
    conn = get_conn()
    rows = conn.execute(
        "SELECT role, content FROM conversations WHERE telegram_id=? ORDER BY id DESC LIMIT ?",
        (telegram_id, limit),
    ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def clear_history(telegram_id):
    with _lock:
        conn = get_conn()
        conn.execute("DELETE FROM conversations WHERE telegram_id=?", (telegram_id,))
        conn.commit()


# ---------------- settings ----------------

def get_setting(key, default=None):
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key, value):
    with _lock:
        conn = get_conn()
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        conn.commit()


# ---------------- broadcast queue (used to bridge Flask thread -> bot event loop) ----------------

def queue_broadcast(message):
    with _lock:
        conn = get_conn()
        conn.execute(
            "INSERT INTO broadcast_queue (message, created_at) VALUES (?, ?)",
            (message, _now()),
        )
        conn.commit()


def get_pending_broadcasts():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM broadcast_queue WHERE sent=0 ORDER BY id ASC").fetchall()
    return [dict(r) for r in rows]


def mark_broadcast_sent(broadcast_id, total_sent):
    with _lock:
        conn = get_conn()
        conn.execute(
            "UPDATE broadcast_queue SET sent=1, total_sent=? WHERE id=?", (total_sent, broadcast_id)
        )
        conn.commit()


def list_broadcasts(limit=20):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM broadcast_queue ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------- logs ----------------

def log_event(level, message):
    with _lock:
        conn = get_conn()
        conn.execute(
            "INSERT INTO logs (level, message, created_at) VALUES (?, ?, ?)",
            (level, str(message)[:4000], _now()),
        )
        conn.commit()
        conn.execute(
            "DELETE FROM logs WHERE id NOT IN (SELECT id FROM logs ORDER BY id DESC LIMIT 500)"
        )
        conn.commit()


def get_logs(limit=200):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]

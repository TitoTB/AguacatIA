import sqlite3
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import DATA_DIR, DB_PATH


PUBLIC_LEVEL_SLUG = "public"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT '',
                is_secret INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS access_levels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                rank INTEGER NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS telegram_users (
                telegram_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL DEFAULT '',
                level_id INTEGER NOT NULL,
                is_owner INTEGER NOT NULL DEFAULT 0,
                is_blocked INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(level_id) REFERENCES access_levels(id)
            );

            CREATE TABLE IF NOT EXISTS skills (
                key TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                command TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1,
                required_level_id INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(required_level_id) REFERENCES access_levels(id)
            );

            CREATE TABLE IF NOT EXISTS command_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id TEXT NOT NULL DEFAULT '',
                skill_key TEXT NOT NULL DEFAULT '',
                command TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                message TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            """
        )
        _seed_levels(conn)
        _seed_settings(conn)


def _seed_levels(conn: sqlite3.Connection) -> None:
    defaults = [
        ("Publico", PUBLIC_LEVEL_SLUG, 0),
        ("Aguacatec Friend", "aguacatec_friend", 10),
        ("Aguacatec Lover", "aguacatec_lover", 20),
    ]
    for name, slug, rank in defaults:
        conn.execute(
            "INSERT OR IGNORE INTO access_levels(name, slug, rank) VALUES (?, ?, ?)",
            (name, slug, rank),
        )


def _seed_settings(conn: sqlite3.Connection) -> None:
    defaults = {
        "admin_password_hash": "",
        "admin_session_secret": "",
        "telegram_bot_token": "",
        "bot_enabled": "0",
        "owner_telegram_id": "",
        "bdevices_search_url": "http://bdevices:8010/api/agent/devices/search",
        "bdevices_agent_token": "",
        "ai_provider": "ollama",
        "ollama_base_url": "http://ollama:11434",
        "ollama_model": "llama3.1",
        "openai_api_key": "",
        "gemini_api_key": "",
    }
    now = utc_now()
    for key, value in defaults.items():
        is_secret = 1 if key.endswith("_token") or key.endswith("_key") or key == "admin_password_hash" else 0
        conn.execute(
            "INSERT OR IGNORE INTO settings(key, value, is_secret, updated_at) VALUES (?, ?, ?, ?)",
            (key, value, is_secret, now),
        )


def settings_map(include_secrets: bool = True) -> dict[str, str]:
    with connect() as conn:
        rows = conn.execute("SELECT key, value, is_secret FROM settings").fetchall()
    result = {}
    for row in rows:
        if row["is_secret"] and not include_secrets:
            result[row["key"]] = "********" if row["value"] else ""
        else:
            result[row["key"]] = row["value"]
    return result


def get_setting(key: str, default: str = "") -> str:
    with connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return str(row["value"]) if row else default


def save_setting(key: str, value: str, is_secret: bool = False) -> None:
    now = utc_now()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO settings(key, value, is_secret, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                is_secret = excluded.is_secret,
                updated_at = excluded.updated_at
            """,
            (key, value, 1 if is_secret else 0, now),
        )


def admin_is_configured() -> bool:
    return bool(get_setting("admin_password_hash", "").strip())


def public_level_id() -> int:
    with connect() as conn:
        row = conn.execute("SELECT id FROM access_levels WHERE slug = ?", (PUBLIC_LEVEL_SLUG,)).fetchone()
    if not row:
        init_db()
        return public_level_id()
    return int(row["id"])


def list_levels() -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute("SELECT * FROM access_levels ORDER BY rank ASC").fetchall()


def create_level(name: str, slug: str, rank: int) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO access_levels(name, slug, rank) VALUES (?, ?, ?)",
            (name.strip(), slug.strip(), rank),
        )


def update_level(level_id: int, name: str, rank: int) -> None:
    with connect() as conn:
        conn.execute("UPDATE access_levels SET name = ?, rank = ? WHERE id = ?", (name.strip(), rank, level_id))


def sync_skills(definitions: Iterable[dict[str, Any]]) -> None:
    level_id = public_level_id()
    now = utc_now()
    with connect() as conn:
        for skill in definitions:
            conn.execute(
                """
                INSERT INTO skills(key, title, description, command, enabled, required_level_id, updated_at)
                VALUES (?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    title = excluded.title,
                    description = excluded.description,
                    command = excluded.command
                """,
                (
                    skill["key"],
                    skill["title"],
                    skill.get("description", ""),
                    skill.get("command", ""),
                    level_id,
                    now,
                ),
            )


def list_skills() -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            """
            SELECT s.*, l.name AS required_level_name, l.rank AS required_level_rank
            FROM skills s
            JOIN access_levels l ON l.id = s.required_level_id
            ORDER BY s.key
            """
        ).fetchall()


def get_skill(key: str) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute(
            """
            SELECT s.*, l.rank AS required_level_rank
            FROM skills s
            JOIN access_levels l ON l.id = s.required_level_id
            WHERE s.key = ?
            """,
            (key,),
        ).fetchone()


def update_skill_permission(key: str, enabled: bool, required_level_id: int) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE skills SET enabled = ?, required_level_id = ?, updated_at = ? WHERE key = ?",
            (1 if enabled else 0, required_level_id, utc_now(), key),
        )


def list_users() -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            """
            SELECT u.*, l.name AS level_name, l.rank AS level_rank
            FROM telegram_users u
            JOIN access_levels l ON l.id = u.level_id
            ORDER BY u.is_owner DESC, l.rank DESC, u.telegram_id
            """
        ).fetchall()


def upsert_user(
    telegram_id: str,
    display_name: str = "",
    level_id: int | None = None,
    is_owner: bool = False,
    is_blocked: bool = False,
) -> None:
    level_id = level_id or public_level_id()
    now = utc_now()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO telegram_users(telegram_id, display_name, level_id, is_owner, is_blocked, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                display_name = CASE WHEN excluded.display_name != '' THEN excluded.display_name ELSE telegram_users.display_name END,
                level_id = excluded.level_id,
                is_owner = excluded.is_owner,
                is_blocked = excluded.is_blocked,
                updated_at = excluded.updated_at
            """,
            (str(telegram_id), display_name.strip(), level_id, 1 if is_owner else 0, 1 if is_blocked else 0, now, now),
        )


def ensure_user(telegram_id: str, display_name: str = "") -> None:
    with connect() as conn:
        existing = conn.execute("SELECT telegram_id FROM telegram_users WHERE telegram_id = ?", (str(telegram_id),)).fetchone()
    if existing:
        if display_name:
            with connect() as conn:
                conn.execute(
                    "UPDATE telegram_users SET display_name = ?, updated_at = ? WHERE telegram_id = ? AND display_name = ''",
                    (display_name, utc_now(), str(telegram_id)),
                )
        return
    owner_id = get_setting("owner_telegram_id", "").strip()
    upsert_user(str(telegram_id), display_name, public_level_id(), is_owner=owner_id == str(telegram_id), is_blocked=False)


def get_user_with_level(telegram_id: str) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute(
            """
            SELECT u.*, l.rank AS level_rank, l.name AS level_name
            FROM telegram_users u
            JOIN access_levels l ON l.id = u.level_id
            WHERE u.telegram_id = ?
            """,
            (str(telegram_id),),
        ).fetchone()


def log_command(telegram_id: str, skill_key: str, command: str, status: str, message: str = "") -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO command_log(telegram_id, skill_key, command, status, message, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (str(telegram_id), skill_key, command, status, message[:500], utc_now()),
        )


def recent_logs(limit: int = 50) -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute("SELECT * FROM command_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


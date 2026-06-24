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

            CREATE TABLE IF NOT EXISTS skill_messages (
                skill_key TEXT NOT NULL,
                message_key TEXT NOT NULL,
                label TEXT NOT NULL,
                value TEXT NOT NULL DEFAULT '',
                default_value TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL,
                PRIMARY KEY(skill_key, message_key),
                FOREIGN KEY(skill_key) REFERENCES skills(key) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS skill_triggers (
                skill_key TEXT NOT NULL,
                trigger TEXT NOT NULL,
                normalized TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(skill_key, normalized),
                FOREIGN KEY(skill_key) REFERENCES skills(key) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS bdevices_taxonomies (
                kind TEXT NOT NULL,
                value TEXT NOT NULL,
                normalized TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(kind, value)
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
        "bdevices_taxonomies_url": "http://bdevices:8010/api/agent/devices/taxonomies",
        "bdevices_agent_token": "",
        "bdevices_ai_query_enabled": "0",
        "bdevices_taxonomies_last_sync": "",
        "bdevices_taxonomies_last_status": "Sin sincronizar",
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
                    command = CASE
                        WHEN skills.command = '' THEN excluded.command
                        ELSE skills.command
                    END
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
            for message_key, message in (skill.get("messages") or {}).items():
                default_value = message.get("default", "")
                conn.execute(
                    """
                    INSERT INTO skill_messages(skill_key, message_key, label, value, default_value, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(skill_key, message_key) DO UPDATE SET
                        label = excluded.label,
                        default_value = excluded.default_value
                    """,
                    (
                        skill["key"],
                        message_key,
                        message.get("label", message_key),
                        default_value,
                        default_value,
                        now,
                    ),
                )
            existing_triggers = conn.execute(
                "SELECT 1 FROM skill_triggers WHERE skill_key = ? LIMIT 1",
                (skill["key"],),
            ).fetchone()
            if not existing_triggers:
                for trigger in skill.get("triggers") or []:
                    normalized = normalize_text(trigger)
                    if normalized:
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO skill_triggers(skill_key, trigger, normalized, updated_at)
                            VALUES (?, ?, ?, ?)
                            """,
                            (skill["key"], trigger.strip(), normalized, now),
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


def list_skill_triggers() -> dict[str, list[sqlite3.Row]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM skill_triggers ORDER BY skill_key, trigger"
        ).fetchall()
    grouped: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        grouped.setdefault(row["skill_key"], []).append(row)
    return grouped


def skill_triggers_text(skill_key: str) -> str:
    rows = list_skill_triggers().get(skill_key, [])
    return "\n".join(row["trigger"] for row in rows)


def replace_skill_triggers(skill_key: str, triggers_text: str) -> None:
    now = utc_now()
    rows = []
    seen = set()
    for line in str(triggers_text or "").splitlines():
        trigger = line.strip()
        normalized = normalize_text(trigger)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        rows.append((skill_key, trigger, normalized, now))
    with connect() as conn:
        conn.execute("DELETE FROM skill_triggers WHERE skill_key = ?", (skill_key,))
        conn.executemany(
            """
            INSERT INTO skill_triggers(skill_key, trigger, normalized, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            rows,
        )


def find_skill_trigger(text: str) -> sqlite3.Row | None:
    normalized_text = normalize_text(text)
    if not normalized_text:
        return None
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT t.*, s.enabled, s.command
            FROM skill_triggers t
            JOIN skills s ON s.key = t.skill_key
            WHERE s.enabled = 1
            ORDER BY length(t.normalized) DESC
            """
        ).fetchall()
    for row in rows:
        trigger = row["normalized"]
        if normalized_text == trigger or normalized_text.startswith(f"{trigger} "):
            return row
    return None


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


def get_skill_by_command(command: str) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute(
            """
            SELECT s.*, l.rank AS required_level_rank
            FROM skills s
            JOIN access_levels l ON l.id = s.required_level_id
            WHERE lower(s.command) = lower(?)
            """,
            (command,),
        ).fetchone()


def list_skill_messages() -> dict[str, list[sqlite3.Row]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM skill_messages ORDER BY skill_key, message_key"
        ).fetchall()
    grouped: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        grouped.setdefault(row["skill_key"], []).append(row)
    return grouped


def skill_messages_map(skill_key: str) -> dict[str, str]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT message_key, value, default_value FROM skill_messages WHERE skill_key = ?",
            (skill_key,),
        ).fetchall()
    return {row["message_key"]: row["value"] or row["default_value"] for row in rows}


def get_skill_message(skill_key: str, message_key: str, default: str = "") -> str:
    with connect() as conn:
        row = conn.execute(
            "SELECT value, default_value FROM skill_messages WHERE skill_key = ? AND message_key = ?",
            (skill_key, message_key),
        ).fetchone()
    if not row:
        return default
    return str(row["value"] or row["default_value"] or default)


def update_skill_config(key: str, command: str, enabled: bool, required_level_id: int) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE skills SET command = ?, enabled = ?, required_level_id = ?, updated_at = ? WHERE key = ?",
            (command, 1 if enabled else 0, required_level_id, utc_now(), key),
        )


def update_skill_message(skill_key: str, message_key: str, value: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE skill_messages SET value = ?, updated_at = ? WHERE skill_key = ? AND message_key = ?",
            (value, utc_now(), skill_key, message_key),
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


def replace_bdevices_taxonomies(taxonomies: dict[str, list[str]]) -> int:
    now = utc_now()
    rows = [
        (kind, value.strip(), _normalize_taxonomy(value), now)
        for kind, values in taxonomies.items()
        for value in values
        if str(value).strip()
    ]
    with connect() as conn:
        conn.execute("DELETE FROM bdevices_taxonomies")
        conn.executemany(
            """
            INSERT OR REPLACE INTO bdevices_taxonomies(kind, value, normalized, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            rows,
        )
    return len(rows)


def bdevices_taxonomies_map() -> dict[str, list[str]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT kind, value FROM bdevices_taxonomies ORDER BY kind, value"
        ).fetchall()
    taxonomies: dict[str, list[str]] = {}
    for row in rows:
        taxonomies.setdefault(row["kind"], []).append(row["value"])
    return taxonomies


def bdevices_taxonomies_normalized_map() -> dict[str, dict[str, str]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT kind, value, normalized FROM bdevices_taxonomies ORDER BY kind, value"
        ).fetchall()
    taxonomies: dict[str, dict[str, str]] = {}
    for row in rows:
        taxonomies.setdefault(row["kind"], {})[row["normalized"]] = row["value"]
    return taxonomies


def bdevices_taxonomies_summary() -> dict[str, int]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT kind, COUNT(*) AS count FROM bdevices_taxonomies GROUP BY kind ORDER BY kind"
        ).fetchall()
    return {row["kind"]: int(row["count"]) for row in rows}


def _normalize_taxonomy(value: object) -> str:
    return normalize_text(value)


def normalize_text(value: object) -> str:
    import re
    import unicodedata

    decomposed = unicodedata.normalize("NFKD", str(value or "").lower())
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    plain = re.sub(r"[^\w\s-]", " ", plain)
    return re.sub(r"\s+", " ", plain).strip()

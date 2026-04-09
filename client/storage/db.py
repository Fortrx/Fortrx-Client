import json
import os
import sqlite3
from contextlib import contextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path

from client.config import settings
from client.network.auth import get_me
from client.network.api import set_token
from client.storage.crypto import StorageError, _decrypt, _encrypt

try:
    import sqlcipher3 as sqlcipher_driver
except ImportError:
    try:
        from pysqlcipher3 import dbapi2 as sqlcipher_driver
    except ImportError:
        sqlcipher_driver = None


SQLITE_HEADER = b"SQLite format 3\x00"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _db_path() -> Path:
    return Path(settings.DB_FILE)


def _ensure_parent():
    _db_path().parent.mkdir(parents=True, exist_ok=True)


def _dict_row(cursor, row):
    return {column[0]: row[idx] for idx, column in enumerate(cursor.description)}


def _db_header() -> bytes:
    path = _db_path()
    if not path.exists():
        return b""
    with path.open("rb") as handle:
        return handle.read(16)


def _storage_open_error(exc: Exception) -> StorageError:
    header = _db_header()
    if _using_sqlcipher() and header == SQLITE_HEADER:
        return StorageError(
            "Local storage was created without SQLCipher. Move or migrate "
            f"'{_db_path()}' before using the sqlcipher3-backed client."
        )
    if _using_sqlcipher():
        return StorageError("Wrong storage password or incompatible encrypted database.")
    return StorageError("Could not open local storage.")


def _get_driver():
    return sqlcipher_driver or sqlite3


def _using_sqlcipher() -> bool:
    return sqlcipher_driver is not None


def _connect(password: str | None):
    if not password:
        raise StorageError("No storage password set")
    if not _using_sqlcipher() and not settings.ALLOW_INSECURE_STORAGE:
        raise StorageError(
            "SQLCipher support is required. Install sqlcipher3 or set "
            "ALLOW_INSECURE_STORAGE=true only for local development."
        )

    _ensure_parent()
    driver = _get_driver()
    conn = None
    try:
        conn = driver.connect(str(_db_path()))
        conn.row_factory = _dict_row

        if _using_sqlcipher():
            # Avoid embedding raw user input in SQL text. Use a hex blob literal
            # so only [0-9A-F] reaches the statement payload.
            key_hex = password.encode("utf-8").hex().upper()
            conn.execute(f"PRAGMA key = \"x'{key_hex}'\"")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("SELECT count(*) AS count FROM sqlite_master").fetchone()
        return conn
    except Exception as exc:
        with suppress(Exception):
            if conn is not None:
                conn.close()
        raise _storage_open_error(exc) from exc


def _initialize(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tokens (
            name TEXT PRIMARY KEY,
            value BLOB NOT NULL
        );

        CREATE TABLE IF NOT EXISTS private_keys (
            user_id INTEGER PRIMARY KEY,
            payload BLOB NOT NULL,
            migrated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions (
            contact_id INTEGER PRIMARY KEY,
            payload BLOB NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS verifications (
            contact_id INTEGER PRIMARY KEY,
            safety_number TEXT NOT NULL,
            verified_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS contacts (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            is_online INTEGER NOT NULL DEFAULT 0,
            last_seen_at TEXT
        );

        CREATE TABLE IF NOT EXISTS conversation_summary (
            contact_id INTEGER PRIMARY KEY,
            last_message_id INTEGER,
            last_message_at TEXT,
            last_viewed_at TEXT,
            last_message_preview BLOB,
            last_direction TEXT,
            last_status TEXT,
            unread_count INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_message_id INTEGER UNIQUE,
            contact_id INTEGER NOT NULL,
            direction TEXT NOT NULL,
            sender_id INTEGER,
            recipient_id INTEGER,
            message_number INTEGER,
            plaintext BLOB,
            sealed_blob BLOB,
            created_at TEXT NOT NULL,
            delivered_at TEXT,
            expires_at TEXT,
            status TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_messages_contact_created
        ON messages(contact_id, created_at, id);

        CREATE INDEX IF NOT EXISTS idx_messages_created
        ON messages(created_at, id);

        CREATE INDEX IF NOT EXISTS idx_contacts_username
        ON contacts(username);

        CREATE INDEX IF NOT EXISTS idx_conversation_summary_last_message_at
        ON conversation_summary(last_message_at, contact_id);
        """
    )
    _ensure_summary_columns(conn)
    _rebuild_conversation_summary(conn)
    conn.commit()


def _json_blob(value: dict, password: str) -> bytes:
    raw = json.dumps(value).encode()
    return _encrypt(raw, password)


def _from_json_blob(blob: bytes, password: str) -> dict:
    return json.loads(_decrypt(blob, password))


def _text_blob(value: str | None, password: str) -> bytes | None:
    if value is None:
        return None
    return _encrypt(value.encode(), password)


def _from_text_blob(blob: bytes | None, password: str) -> str | None:
    if blob is None:
        return None
    return _decrypt(blob, password).decode()


def _preview_text(value: str | None, max_len: int = 80) -> str | None:
    if value is None:
        return None
    compact = " ".join(value.split())
    return compact[:max_len]


def _coalesce_timestamp(value: str | None) -> str:
    return value or _utcnow()


def _ensure_summary_columns(conn):
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(conversation_summary)").fetchall()
    }
    if "last_viewed_at" not in columns:
        conn.execute("ALTER TABLE conversation_summary ADD COLUMN last_viewed_at TEXT")


def _rebuild_conversation_summary(conn):
    has_rows = conn.execute(
        "SELECT 1 FROM conversation_summary LIMIT 1"
    ).fetchone()
    if has_rows:
        return

    rows = conn.execute(
        """
        SELECT
            m.id,
            m.contact_id,
            m.direction,
            m.status,
            m.created_at,
            m.plaintext,
            c.username,
            c.is_online
        FROM messages m
        LEFT JOIN contacts c ON c.user_id = m.contact_id
        ORDER BY datetime(m.created_at) ASC, m.id ASC
        """
    ).fetchall()

    pending = {}
    for row in rows:
        pending[row["contact_id"]] = {
            "last_message_id": row["id"],
            "last_message_at": row["created_at"],
            "last_viewed_at": None,
            "last_message_preview": row["plaintext"],
            "last_direction": row["direction"],
            "last_status": row["status"],
            "unread_count": pending.get(row["contact_id"], {}).get("unread_count", 0)
            + (1 if row["direction"] == "incoming" else 0),
        }

    for contact_id, item in pending.items():
        conn.execute(
            """
            INSERT OR REPLACE INTO conversation_summary(
                contact_id,
                last_message_id,
                last_message_at,
                last_viewed_at,
                last_message_preview,
                last_direction,
                last_status,
                unread_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                contact_id,
                item["last_message_id"],
                item["last_message_at"],
                item["last_viewed_at"],
                item["last_message_preview"],
                item["last_direction"],
                item["last_status"],
                item["unread_count"],
            ),
        )


def _legacy_candidates(pattern: str):
    root = Path(settings.LOCAL_STORAGE_PATH)
    if not root.exists():
        return []
    return list(root.glob(pattern))


def _migrate_legacy_files(conn, password: str):
    migrated = conn.execute(
        "SELECT value FROM metadata WHERE key = 'legacy_migrated'"
    ).fetchone()
    if migrated:
        return

    cleanup_paths: list[Path] = []
    token_path = Path(settings.TOKEN_FILE)
    if token_path.exists():
        token = token_path.read_text().strip()
        if token:
            save_token(password, token, conn=conn)
            cleanup_paths.append(token_path)

    key_rows = _legacy_candidates("keys_*.enc")
    legacy_key_file = Path(settings.KEYS_FILE)
    if legacy_key_file.exists():
        key_rows.append(legacy_key_file)
    seen_key_users: set[int] = set()
    for path in key_rows:
        try:
            payload = json.loads(_decrypt(path.read_bytes(), password))
        except Exception:
            continue
        user_id = int(payload["user_id"])
        if user_id in seen_key_users:
            continue
        save_keys(password, payload, conn=conn)
        seen_key_users.add(user_id)
        cleanup_paths.append(path)

    session_path = Path(settings.SESSION_FILE)
    if session_path.exists():
        try:
            sessions = json.loads(_decrypt(session_path.read_bytes(), password))
        except Exception:
            sessions = {}
        for contact_id, state in sessions.items():
            save_session_blob(password, int(contact_id), state, conn=conn)
        cleanup_paths.append(session_path)

    verified_path = Path(settings.VERIFIED_FILE)
    if verified_path.exists():
        try:
            data = json.loads(verified_path.read_text())
        except Exception:
            data = {}
        for user_id, entry in data.items():
            conn.execute(
                """
                INSERT OR REPLACE INTO verifications(contact_id, safety_number, verified_at)
                VALUES(?, ?, ?)
                """,
                (
                    int(user_id),
                    entry["safety_number"],
                    entry.get("verified_at", _utcnow()),
                ),
            )
        cleanup_paths.append(verified_path)

    conn.execute(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES('legacy_migrated', ?)",
        (_utcnow(),),
    )
    conn.commit()
    for path in cleanup_paths:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass


@contextmanager
def open_storage(password: str):
    conn = _connect(password)
    try:
        _initialize(conn)
        _migrate_legacy_files(conn, password)
        yield conn
    finally:
        conn.close()


def save_token(password: str, token: str, conn=None):
    owns_conn = conn is None
    if owns_conn:
        conn = _connect(password)
        _initialize(conn)
        _migrate_legacy_files(conn, password)
    conn.execute(
        "INSERT OR REPLACE INTO tokens(name, value) VALUES('auth', ?)",
        (_text_blob(token, password),),
    )
    conn.commit()
    if owns_conn:
        conn.close()


def load_token(password: str | None = None):
    if not password:
        return None
    try:
        with open_storage(password) as conn:
            row = conn.execute("SELECT value FROM tokens WHERE name = 'auth'").fetchone()
            if not row:
                return None
            token = _from_text_blob(row["value"], password)
            if token:
                set_token(token)
            return token
    except Exception:
        return None


def delete_token(password: str):
    with open_storage(password) as conn:
        conn.execute("DELETE FROM tokens WHERE name = 'auth'")
        conn.commit()


def save_keys(password: str, keys: dict, conn=None):
    owns_conn = conn is None
    if owns_conn:
        conn = _connect(password)
        _initialize(conn)
        _migrate_legacy_files(conn, password)
    conn.execute(
        """
        INSERT OR REPLACE INTO private_keys(user_id, payload, migrated_at)
        VALUES(?, ?, ?)
        """,
        (int(keys["user_id"]), _json_blob(keys, password), _utcnow()),
    )
    conn.commit()
    if owns_conn:
        conn.close()


def load_keys(password: str, user_id: int | None = None):
    with open_storage(password) as conn:
        if user_id is None:
            try:
                me = get_me()
                user_id = me.get("id")
            except Exception:
                user_id = None

        row = None
        if user_id is not None:
            row = conn.execute(
                "SELECT payload FROM private_keys WHERE user_id = ?",
                (int(user_id),),
            ).fetchone()
        if row is None:
            rows = conn.execute(
                "SELECT user_id, payload FROM private_keys ORDER BY user_id"
            ).fetchall()
            if not rows:
                raise StorageError("No keys found. Run 'fortrx init' first.")
            if len(rows) > 1:
                raise StorageError(
                    "Multiple local identities found. Log in before unlocking keys."
                )
            row = rows[0]
        if row is None:
            raise StorageError("No keys found. Run 'fortrx init' first.")
        return _from_json_blob(row["payload"], password)


def keys_exist(password: str | None = None):
    if password:
        try:
            with open_storage(password) as conn:
                row = conn.execute("SELECT 1 FROM private_keys LIMIT 1").fetchone()
                return bool(row)
        except Exception:
            return False
    return _db_path().exists() or Path(settings.KEYS_FILE).exists() or bool(_legacy_candidates("keys_*.enc"))


def save_session_blob(password: str, other_user_id: int, state: dict, conn=None):
    owns_conn = conn is None
    if owns_conn:
        conn = _connect(password)
        _initialize(conn)
        _migrate_legacy_files(conn, password)
    conn.execute(
        """
        INSERT OR REPLACE INTO sessions(contact_id, payload, updated_at)
        VALUES(?, ?, ?)
        """,
        (other_user_id, _json_blob(state, password), _utcnow()),
    )
    conn.commit()
    if owns_conn:
        conn.close()


def load_session_blob(password: str, other_user_id: int):
    with open_storage(password) as conn:
        row = conn.execute(
            "SELECT payload FROM sessions WHERE contact_id = ?",
            (other_user_id,),
        ).fetchone()
        if not row:
            return None
        return _from_json_blob(row["payload"], password)


def load_sessions_map(password: str):
    with open_storage(password) as conn:
        rows = conn.execute("SELECT contact_id, payload FROM sessions").fetchall()
        return {
            str(row["contact_id"]): _from_json_blob(row["payload"], password)
            for row in rows
        }


def save_verification(password: str, user_id: int, safety_number: str):
    with open_storage(password) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO verifications(contact_id, safety_number, verified_at)
            VALUES(?, ?, ?)
            """,
            (user_id, safety_number, _utcnow()),
        )
        conn.commit()


def load_verifications(password: str):
    with open_storage(password) as conn:
        rows = conn.execute(
            "SELECT contact_id, safety_number, verified_at FROM verifications"
        ).fetchall()
        return {
            str(row["contact_id"]): {
                "safety_number": row["safety_number"],
                "verified_at": row["verified_at"],
            }
            for row in rows
        }


def is_verified(password: str, user_id: int) -> bool:
    with open_storage(password) as conn:
        row = conn.execute(
            "SELECT 1 FROM verifications WHERE contact_id = ?",
            (user_id,),
        ).fetchone()
        return bool(row)


def upsert_contact(password: str, user_id: int, username: str | None = None, is_online: bool | None = None):
    with open_storage(password) as conn:
        existing = conn.execute(
            "SELECT username, is_online FROM contacts WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        conn.execute(
            """
            INSERT OR REPLACE INTO contacts(user_id, username, is_online, last_seen_at)
            VALUES(?, ?, ?, ?)
            """,
            (
                user_id,
                username if username is not None else (existing["username"] if existing else None),
                int(is_online if is_online is not None else (existing["is_online"] if existing else 0)),
                _utcnow(),
            ),
        )
        conn.commit()


def list_contacts(password: str):
    with open_storage(password) as conn:
        rows = conn.execute(
            """
            SELECT
                c.user_id,
                c.username,
                c.is_online,
                c.last_seen_at,
                s.last_message_at,
                s.last_direction,
                s.last_status,
                s.unread_count,
                s.last_message_preview
            FROM contacts c
            LEFT JOIN conversation_summary s ON s.contact_id = c.user_id
            ORDER BY
                CASE WHEN s.last_message_at IS NULL THEN 1 ELSE 0 END,
                datetime(s.last_message_at) DESC,
                COALESCE(c.username, c.user_id)
            """
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["last_message_preview"] = _from_text_blob(item["last_message_preview"], password)
            result.append(item)
        return result


def _update_conversation_summary(
    conn,
    password: str,
    *,
    contact_id: int,
    message_id: int,
    created_at: str,
    preview: str | None,
    direction: str,
    status: str,
    unread_delta: int,
):
    existing = conn.execute(
        """
        SELECT unread_count, last_message_at, last_viewed_at
        FROM conversation_summary
        WHERE contact_id = ?
        """,
        (contact_id,),
    ).fetchone()
    last_viewed_at = existing["last_viewed_at"] if existing else None
    next_unread = _count_unread_messages(
        conn,
        contact_id,
        last_viewed_at,
        pending_incoming=1 if unread_delta > 0 else 0,
    )
    conn.execute(
        """
        INSERT INTO conversation_summary(
            contact_id,
            last_message_id,
            last_message_at,
            last_viewed_at,
            last_message_preview,
            last_direction,
            last_status,
            unread_count
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(contact_id) DO UPDATE SET
            last_message_id = excluded.last_message_id,
            last_message_at = excluded.last_message_at,
            last_viewed_at = COALESCE(conversation_summary.last_viewed_at, excluded.last_viewed_at),
            last_message_preview = excluded.last_message_preview,
            last_direction = excluded.last_direction,
            last_status = excluded.last_status,
            unread_count = excluded.unread_count
        """,
        (
            contact_id,
            message_id,
            created_at,
            last_viewed_at,
            _text_blob(_preview_text(preview), password),
            direction,
            status,
            next_unread,
        ),
    )


def _count_unread_messages(conn, contact_id: int, last_viewed_at: str | None, pending_incoming: int = 0) -> int:
    if not last_viewed_at:
        row = conn.execute(
            """
            SELECT COUNT(*) AS unread_count
            FROM messages
            WHERE contact_id = ? AND direction = 'incoming'
            """,
            (contact_id,),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT COUNT(*) AS unread_count
            FROM messages
            WHERE contact_id = ?
              AND direction = 'incoming'
              AND datetime(created_at) > datetime(?)
            """,
            (contact_id, last_viewed_at),
        ).fetchone()
    return int(row["unread_count"]) + pending_incoming


def mark_conversation_viewed(password: str, contact_id: int):
    with open_storage(password) as conn:
        latest = conn.execute(
            """
            SELECT created_at
            FROM messages
            WHERE contact_id = ?
            ORDER BY datetime(created_at) DESC, id DESC
            LIMIT 1
            """,
            (contact_id,),
        ).fetchone()
        if not latest:
            return
        viewed_at = latest["created_at"]
        conn.execute(
            """
            INSERT INTO conversation_summary(contact_id, last_viewed_at, unread_count)
            VALUES(?, ?, 0)
            ON CONFLICT(contact_id) DO UPDATE SET
                last_viewed_at = excluded.last_viewed_at,
                unread_count = 0
            """,
            (contact_id, viewed_at),
        )
        conn.commit()


def mark_all_conversations_viewed(password: str):
    with open_storage(password) as conn:
        rows = conn.execute(
            """
            SELECT contact_id, last_message_at
            FROM conversation_summary
            WHERE last_message_at IS NOT NULL
            """
        ).fetchall()
        for row in rows:
            conn.execute(
                """
                UPDATE conversation_summary
                SET last_viewed_at = ?, unread_count = 0
                WHERE contact_id = ?
                """,
                (row["last_message_at"], row["contact_id"]),
            )
        conn.commit()


def message_exists(password: str, server_message_id: int) -> bool:
    with open_storage(password) as conn:
        row = conn.execute(
            "SELECT 1 FROM messages WHERE server_message_id = ?",
            (server_message_id,),
        ).fetchone()
        return bool(row)


def save_incoming_message(password: str, message: dict):
    with open_storage(password) as conn:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO messages(
                server_message_id, contact_id, direction, sender_id, recipient_id,
                message_number, plaintext, sealed_blob, created_at, delivered_at,
                expires_at, status
            ) VALUES (?, ?, 'incoming', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message["server_message_id"],
                message["contact_id"],
                message["sender_id"],
                message.get("recipient_id"),
                message.get("message_number"),
                _text_blob(message["plaintext"], password),
                _text_blob(message.get("sealed_blob"), password),
                _coalesce_timestamp(message.get("created_at")),
                _utcnow(),
                message.get("expires_at"),
                message.get("status", "delivered"),
            ),
        )
        if cursor.rowcount:
            message_id = cursor.lastrowid
            created_at = _coalesce_timestamp(message.get("created_at"))
            _update_conversation_summary(
                conn,
                password,
                contact_id=message["contact_id"],
                message_id=message_id,
                created_at=created_at,
                preview=message.get("plaintext"),
                direction="incoming",
                status=message.get("status", "delivered"),
                unread_delta=1,
            )
        conn.commit()


def save_outgoing_message(password: str, message: dict):
    with open_storage(password) as conn:
        cursor = conn.execute(
            """
            INSERT INTO messages(
                server_message_id, contact_id, direction, sender_id, recipient_id,
                message_number, plaintext, sealed_blob, created_at, delivered_at,
                expires_at, status
            ) VALUES (?, ?, 'outgoing', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message.get("server_message_id"),
                message["contact_id"],
                message.get("sender_id"),
                message.get("recipient_id"),
                message.get("message_number"),
                _text_blob(message["plaintext"], password),
                _text_blob(message.get("sealed_blob"), password),
                _coalesce_timestamp(message.get("created_at")),
                _coalesce_timestamp(message.get("delivered_at")),
                message.get("expires_at"),
                message.get("status", "sent"),
            ),
        )
        message_id = cursor.lastrowid
        created_at = _coalesce_timestamp(message.get("created_at"))
        _update_conversation_summary(
            conn,
            password,
            contact_id=message["contact_id"],
            message_id=message_id,
            created_at=created_at,
            preview=message.get("plaintext"),
            direction="outgoing",
            status=message.get("status", "sent"),
            unread_delta=0,
        )
        conn.commit()


def list_conversation(password: str, contact_id: int, limit: int = 100, before: str | None = None):
    with open_storage(password) as conn:
        if before:
            rows = conn.execute(
                """
                SELECT * FROM messages
                WHERE contact_id = ?
                  AND datetime(created_at) < datetime(?)
                ORDER BY datetime(created_at) DESC, id DESC
                LIMIT ?
                """,
                (contact_id, before, limit),
            ).fetchall()
            rows = list(reversed(rows))
        else:
            rows = conn.execute(
                """
                SELECT * FROM messages
                WHERE contact_id = ?
                ORDER BY datetime(created_at) DESC, id DESC
                LIMIT ?
                """,
                (contact_id, limit),
            ).fetchall()
            rows = list(reversed(rows))
        result = []
        for row in rows:
            item = dict(row)
            item["plaintext"] = _from_text_blob(item["plaintext"], password)
            item["sealed_blob"] = _from_text_blob(item["sealed_blob"], password)
            item["is_online"] = None
            result.append(item)
        return result


def list_conversation_summaries(password: str, limit: int = 100):
    with open_storage(password) as conn:
        rows = conn.execute(
            """
            SELECT
                c.user_id AS contact_id,
                c.username,
                c.is_online,
                c.last_seen_at,
                s.last_message_id,
                s.last_message_at,
                s.last_viewed_at,
                s.last_direction,
                s.last_status,
                s.unread_count,
                s.last_message_preview
            FROM conversation_summary s
            LEFT JOIN contacts c ON c.user_id = s.contact_id
            ORDER BY datetime(s.last_message_at) DESC, s.contact_id
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["last_message_preview"] = _from_text_blob(item["last_message_preview"], password)
            result.append(item)
        return result


def get_daemon_state_path() -> Path:
    return Path(settings.DAEMON_STATE_FILE)


def save_daemon_state(data: dict):
    path = get_daemon_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def load_daemon_state() -> dict | None:
    path = get_daemon_state_path()
    if not path.exists():
        return None
    return json.loads(path.read_text())

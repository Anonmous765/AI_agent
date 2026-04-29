"""SQLite-backed chat session persistence."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent.parent / "database" / "chat_store.sqlite3"
DEFAULT_SESSION_TITLE = "New Chat"


def _utc_now() -> str:
    """Return an ISO 8601 UTC timestamp for storage."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    """Open a SQLite connection with foreign keys enabled."""
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    """Convert a SQLite row into a plain dict."""
    return dict(row) if row is not None else None


def init_db() -> None:
    """Create the sessions and messages tables if they do not already exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with _connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_updated_at
                ON sessions(updated_at DESC);

            CREATE INDEX IF NOT EXISTS idx_messages_session_created_at
                ON messages(session_id, created_at, id);
            """
        )


def list_sessions() -> list[dict]:
    """Return all chat sessions ordered by last activity."""
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM sessions
            ORDER BY updated_at DESC, created_at DESC
            """
        ).fetchall()

    return [_row_to_dict(row) for row in rows]


def create_session(title: str = DEFAULT_SESSION_TITLE) -> dict:
    """Create a new chat session."""
    session_id = str(uuid.uuid4())
    timestamp = _utc_now()
    normalized_title = title.strip() or DEFAULT_SESSION_TITLE

    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO sessions (id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, normalized_title, timestamp, timestamp),
        )
        row = connection.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM sessions
            WHERE id = ?
            """,
            (session_id,),
        ).fetchone()

    return _row_to_dict(row)


def get_session(session_id: str) -> dict | None:
    """Return a single session by id."""
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM sessions
            WHERE id = ?
            """,
            (session_id,),
        ).fetchone()

    return _row_to_dict(row)


def list_messages(session_id: str) -> list[dict]:
    """Return all messages for a session in chronological order."""
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT id, session_id, role, content, created_at
            FROM messages
            WHERE session_id = ?
            ORDER BY created_at ASC, rowid ASC
            """,
            (session_id,),
        ).fetchall()

    return [_row_to_dict(row) for row in rows]


def rename_session(session_id: str, title: str) -> dict | None:
    """Rename a session and update its activity timestamp."""
    normalized_title = title.strip()
    if not normalized_title:
        raise ValueError("Title is required.")

    timestamp = _utc_now()

    with _connect() as connection:
        cursor = connection.execute(
            """
            UPDATE sessions
            SET title = ?, updated_at = ?
            WHERE id = ?
            """,
            (normalized_title, timestamp, session_id),
        )
        if cursor.rowcount == 0:
            return None

        row = connection.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM sessions
            WHERE id = ?
            """,
            (session_id,),
        ).fetchone()

    return _row_to_dict(row)


def delete_session(session_id: str) -> bool:
    """Delete a session and all of its messages."""
    with _connect() as connection:
        cursor = connection.execute(
            "DELETE FROM sessions WHERE id = ?",
            (session_id,),
        )

    return cursor.rowcount > 0


def add_message_pair(
    session_id: str,
    user_content: str,
    assistant_content: str,
    *,
    title: str | None = None,
) -> dict | None:
    """Store a user/assistant message pair and refresh the session timestamp."""
    timestamp = _utc_now()
    session_title = title.strip() if title else None

    with _connect() as connection:
        existing = connection.execute(
            "SELECT id FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if existing is None:
            return None

        connection.execute(
            """
            INSERT INTO messages (id, session_id, role, content, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (str(uuid.uuid4()), session_id, "user", user_content, timestamp),
        )
        connection.execute(
            """
            INSERT INTO messages (id, session_id, role, content, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (str(uuid.uuid4()), session_id, "assistant", assistant_content, timestamp),
        )

        if session_title:
            connection.execute(
                """
                UPDATE sessions
                SET title = ?, updated_at = ?
                WHERE id = ?
                """,
                (session_title, timestamp, session_id),
            )
        else:
            connection.execute(
                """
                UPDATE sessions
                SET updated_at = ?
                WHERE id = ?
                """,
                (timestamp, session_id),
            )

        row = connection.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM sessions
            WHERE id = ?
            """,
            (session_id,),
        ).fetchone()

    return _row_to_dict(row)

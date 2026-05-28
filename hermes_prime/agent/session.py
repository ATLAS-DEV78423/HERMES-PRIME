from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hermes_prime.utils import new_urn_uuid


class SessionStore:
    def __init__(self, db_path: str | Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                model TEXT DEFAULT 'mistral',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                message_count INTEGER DEFAULT 0,
                token_count INTEGER DEFAULT 0,
                metadata TEXT DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );
            CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
            CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                content, session_id UNINDEXED
            );
        """)
        self._conn.commit()

    def create_session(self, title: str, model: str = "mistral") -> dict[str, Any]:
        session_id = new_urn_uuid()
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO sessions (id, title, model, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, title, model, now, now),
        )
        self._conn.commit()
        return {
            "id": session_id,
            "title": title,
            "model": model,
            "created_at": now,
            "updated_at": now,
            "message_count": 0,
        }

    def append_message(self, session_id: str, message: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        content = message.get("content", "")
        role = message.get("role", "user")
        self._conn.execute(
            "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            (session_id, role, content, now),
        )
        self._conn.execute(
            "INSERT INTO messages_fts (content, session_id) VALUES (?, ?)",
            (content, session_id),
        )
        self._conn.execute(
            """UPDATE sessions SET updated_at=?, message_count=message_count+1 WHERE id=?""",
            (now, session_id),
        )
        self._conn.commit()

    def get_messages(self, session_id: str, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT role, content, timestamp FROM messages WHERE session_id=? ORDER BY id ASC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """SELECT DISTINCT s.id, s.title, s.created_at, s.message_count
               FROM sessions s
               JOIN messages_fts fts ON s.id = fts.session_id
               WHERE messages_fts MATCH ? ORDER BY s.updated_at DESC LIMIT ?""",
            (query, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT id, title, model, created_at, updated_at, message_count FROM sessions ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT id, title, model, created_at, updated_at, message_count FROM sessions WHERE id=?",
            (session_id,),
        ).fetchone()
        return dict(row) if row else None

    def close(self) -> None:
        self._conn.commit()
        self._conn.close()

    def __enter__(self) -> SessionStore:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

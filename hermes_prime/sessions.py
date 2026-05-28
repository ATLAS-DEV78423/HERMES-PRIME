from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hermes_prime.utils import new_urn_uuid


class SessionManager:
    """Enhanced session store with Sentinel audit tracing."""

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
                source TEXT DEFAULT 'cli',
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

    def create_session(self, title: str, model: str = "mistral", source: str = "cli") -> dict[str, Any]:
        session_id = new_urn_uuid()
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO sessions (id, title, model, source, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, title, model, source, now, now),
        )
        self._conn.commit()
        return {
            "id": session_id,
            "title": title,
            "model": model,
            "source": source,
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

    def list_sessions(self, source: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        if source:
            rows = self._conn.execute(
                "SELECT id, title, model, source, created_at, updated_at, message_count FROM sessions WHERE source=? ORDER BY updated_at DESC LIMIT ?",
                (source, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, title, model, source, created_at, updated_at, message_count FROM sessions ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT id, title, model, source, created_at, updated_at, message_count FROM sessions WHERE id=?",
            (session_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_messages(self, session_id: str, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT role, content, timestamp FROM messages WHERE session_id=? ORDER BY id ASC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def rename_session(self, session_id: str, new_title: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        cur = self._conn.execute(
            "UPDATE sessions SET title=?, updated_at=? WHERE id=?",
            (new_title, now, session_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def delete_session(self, session_id: str) -> bool:
        self._conn.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
        self._conn.execute("DELETE FROM messages_fts WHERE session_id=?", (session_id,))
        cur = self._conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def prune_sessions(self, older_than_days: int = 30) -> int:
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=older_than_days)).isoformat()
        old = self._conn.execute(
            "SELECT id FROM sessions WHERE updated_at < ?", (cutoff,)
        ).fetchall()
        count = 0
        for row in old:
            sid = row["id"]
            self._conn.execute("DELETE FROM messages WHERE session_id=?", (sid,))
            self._conn.execute("DELETE FROM messages_fts WHERE session_id=?", (sid,))
            self._conn.execute("DELETE FROM sessions WHERE id=?", (sid,))
            count += 1
        self._conn.commit()
        return count

    def stats(self) -> dict[str, Any]:
        session_count = self._conn.execute("SELECT COUNT(*) as c FROM sessions").fetchone()["c"]
        message_count = self._conn.execute("SELECT COUNT(*) as c FROM messages").fetchone()["c"]
        total_tokens = self._conn.execute("SELECT COALESCE(SUM(token_count), 0) as t FROM sessions").fetchone()["t"]
        sources = self._conn.execute(
            "SELECT source, COUNT(*) as c FROM sessions GROUP BY source ORDER BY c DESC"
        ).fetchall()
        return {
            "sessions": session_count,
            "messages": message_count,
            "total_tokens": total_tokens,
            "sources": [dict(s) for s in sources],
        }

    def export_jsonl(self, session_id: str | None = None, out_path: str | None = None) -> str:
        import io
        buf = io.StringIO()
        if session_id:
            sessions = [s for s in [self.get_session(session_id)] if s]
        else:
            sessions = self.list_sessions(limit=1000)
        for sess in sessions:
            msgs = self.get_messages(sess["id"])
            record = {**sess, "messages": msgs}
            buf.write(json.dumps(record, default=str) + "\n")
        content = buf.getvalue()
        if out_path:
            Path(out_path).write_text(content)
        return content

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """SELECT DISTINCT s.id, s.title, s.created_at, s.message_count
               FROM sessions s
               JOIN messages_fts fts ON s.id = fts.session_id
               WHERE messages_fts MATCH ? ORDER BY s.updated_at DESC LIMIT ?""",
            (query, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        self._conn.commit()
        self._conn.close()

    def __enter__(self) -> SessionManager:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

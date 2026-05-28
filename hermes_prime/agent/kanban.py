from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hermes_prime.utils import new_urn_uuid


class KanbanBoard:
    def __init__(self, db_path: str | Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS kanban_tasks (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'todo',
                priority TEXT DEFAULT 'medium',
                assignee TEXT,
                parent_id TEXT,
                tags TEXT DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS kanban_comments (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                author TEXT DEFAULT 'system',
                body TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (task_id) REFERENCES kanban_tasks(id)
            );
        """)
        self._conn.commit()

    def create(
        self,
        title: str,
        description: str = "",
        status: str = "todo",
        priority: str = "medium",
        assignee: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        task_id = new_urn_uuid()
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT INTO kanban_tasks (id, title, description, status, priority, assignee, tags, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (task_id, title, description, status, priority, assignee, json.dumps(tags or []), now, now),
        )
        self._conn.commit()
        return self.get(task_id)

    def get(self, task_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM kanban_tasks WHERE id=?", (task_id,)
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["tags"] = json.loads(result.get("tags", "[]"))
        return result

    def transition(self, task_id: str, new_status: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        completed_at = now if new_status == "done" else None
        self._conn.execute(
            "UPDATE kanban_tasks SET status=?, updated_at=?, completed_at=? WHERE id=?",
            (new_status, now, completed_at, task_id),
        )
        self._conn.commit()
        return True

    def assign(self, task_id: str, assignee: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE kanban_tasks SET assignee=?, updated_at=? WHERE id=?",
            (assignee, now, task_id),
        )
        self._conn.commit()
        return True

    def add_comment(self, task_id: str, body: str, author: str = "system") -> dict[str, Any]:
        comment_id = new_urn_uuid()
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO kanban_comments (id, task_id, author, body, created_at) VALUES (?, ?, ?, ?, ?)",
            (comment_id, task_id, author, body, now),
        )
        self._conn.commit()
        return {"id": comment_id, "task_id": task_id, "author": author, "body": body, "created_at": now}

    def list_all(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM kanban_tasks ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def list_by_status(self, status: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM kanban_tasks WHERE status=? ORDER BY created_at DESC", (status,)
        ).fetchall()
        return [dict(r) for r in rows]

    def list_by_assignee(self, assignee: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM kanban_tasks WHERE assignee=? ORDER BY created_at DESC", (assignee,)
        ).fetchall()
        return [dict(r) for r in rows]

    def remove(self, task_id: str) -> bool:
        self._conn.execute("DELETE FROM kanban_tasks WHERE id=?", (task_id,))
        self._conn.execute("DELETE FROM kanban_comments WHERE task_id=?", (task_id,))
        self._conn.commit()
        return True

    def format_board(self) -> str:
        sections = {"todo": "To Do", "in_progress": "In Progress", "done": "Done"}
        lines = []
        for status, heading in sections.items():
            tasks = self.list_by_status(status)
            lines.append(f"\n## {heading} ({len(tasks)})")
            if not tasks:
                lines.append("  (empty)")
            else:
                for t in tasks:
                    assignee = f" @{t['assignee']}" if t.get("assignee") else ""
                    lines.append(f"  [{t['priority']}] {t['title'][:50]}{assignee}")
        return "\n".join(lines)

    def close(self) -> None:
        self._conn.close()

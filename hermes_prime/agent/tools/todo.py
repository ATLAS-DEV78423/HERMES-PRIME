from __future__ import annotations

from typing import Any
from hermes_prime.utils import new_urn_uuid, utc_now_iso


class TodoManager:
    def __init__(self):
        self._tasks: dict[str, dict[str, Any]] = {}

    def create(
        self,
        title: str,
        subtasks: list[str] | None = None,
        priority: str = "medium",
    ) -> dict[str, Any]:
        task_id = new_urn_uuid()
        task = {
            "id": task_id,
            "title": title,
            "subtasks": subtasks or [],
            "priority": priority,
            "status": "pending",
            "created_at": utc_now_iso(),
            "completed_at": None,
        }
        self._tasks[task_id] = task
        return task

    def get(self, task_id: str) -> dict[str, Any] | None:
        return self._tasks.get(task_id)

    def complete(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if not task:
            return False
        task["status"] = "done"
        task["completed_at"] = utc_now_iso()
        return True

    def list_all(self, status: str | None = None) -> list[dict[str, Any]]:
        tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t["status"] == status]
        return sorted(tasks, key=lambda t: {"high": 0, "medium": 1, "low": 2}.get(t["priority"], 99))

    def remove(self, task_id: str) -> bool:
        return self._tasks.pop(task_id, None) is not None

    def format_plan(self) -> str:
        tasks = self.list_all()
        if not tasks:
            return "No tasks."
        lines = []
        for t in tasks:
            mark = "✓" if t["status"] == "done" else "○"
            lines.append(f"{mark} [{t['priority']}] {t['title']}")
            for sub in t.get("subtasks", []):
                lines.append(f"   - {sub}")
        return "\n".join(lines)


def get_todo_schema() -> dict[str, Any]:
    return {
        "name": "todo",
        "description": "Manage task plans and track progress",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "complete", "list", "remove", "plan"],
                    "description": "Action to perform",
                },
                "title": {"type": "string", "description": "Task title (for create)"},
                "task_id": {"type": "string", "description": "Task ID (for complete/remove)"},
                "priority": {
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                    "description": "Task priority",
                },
            },
            "required": ["action"],
        },
    }


__all__ = ["TodoManager", "get_todo_schema"]

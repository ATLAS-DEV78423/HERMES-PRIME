from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hermes_prime.utils import new_urn_uuid, utc_now_iso


class SkillStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._skills: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                self._skills = {s["id"]: s for s in data}
            except (json.JSONDecodeError, KeyError):
                self._skills = {}

    def _save(self) -> None:
        self.path.write_text(json.dumps(list(self._skills.values()), indent=2))

    def create(
        self,
        name: str,
        content: str,
        language: str = "python",
        description: str = "",
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        skill_id = new_urn_uuid()
        skill = {
            "id": skill_id,
            "name": name,
            "content": content,
            "language": language,
            "description": description,
            "tags": tags or [],
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
            "usage_count": 0,
            "success_rate": 1.0,
        }
        self._skills[skill_id] = skill
        self._save()
        return skill

    def get(self, skill_id: str) -> dict[str, Any] | None:
        return self._skills.get(skill_id)

    def find_by_name(self, name: str) -> dict[str, Any] | None:
        for s in self._skills.values():
            if s["name"] == name:
                return s
        return None

    def search(self, query: str) -> list[dict[str, Any]]:
        q = query.lower()
        results = []
        for s in self._skills.values():
            if q in s["name"].lower() or q in s["description"].lower():
                results.append(s)
                continue
            for tag in s.get("tags", []):
                if q in tag.lower():
                    results.append(s)
                    break
        return results

    def list_all(self) -> list[dict[str, Any]]:
        return list(self._skills.values())

    def remove(self, skill_id: str) -> bool:
        if skill_id in self._skills:
            del self._skills[skill_id]
            self._save()
            return True
        return False

    def record_usage(self, skill_id: str, success: bool) -> None:
        skill = self._skills.get(skill_id)
        if skill:
            skill["usage_count"] = skill.get("usage_count", 0) + 1
            total = skill["usage_count"]
            prev_successes = total - 1
            skill["success_rate"] = (
                prev_successes * skill.get("success_rate", 1.0)
                + (1.0 if success else 0.0)
            ) / total
            skill["updated_at"] = utc_now_iso()
            self._save()

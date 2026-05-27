from __future__ import annotations

from pathlib import Path
from typing import Any

from hermes_prime.agent.skills.store import SkillStore


class SkillManager:
    def __init__(self, store: SkillStore | None = None):
        self.store = store or SkillStore(Path.cwd() / ".hermes-prime" / "skills.json")

    def skills_list(self, query: str | None = None) -> str:
        if query:
            results = self.store.search(query)
        else:
            results = self.store.list_all()
        if not results:
            return "No skills found."
        lines = [f"Skills ({len(results)}):"]
        for s in results:
            lines.append(
                f"  - {s['name']}: {s.get('description', '')[:60]} (used {s.get('usage_count', 0)}x)"
            )
        return "\n".join(lines)

    def skill_view(self, name: str) -> str:
        skill = self.store.find_by_name(name)
        if not skill:
            return f"Skill '{name}' not found."
        return (
            f"Skill: {skill['name']}\n"
            f"Language: {skill.get('language', 'unknown')}\n"
            f"Tags: {', '.join(skill.get('tags', []))}\n"
            f"Usage: {skill.get('usage_count', 0)}x | Success: {skill.get('success_rate', 1.0):.0%}\n"
            f"---\n{skill['content']}"
        )

    def skill_manage(
        self, action: str, name: str, content: str | None = None, **kwargs: Any
    ) -> str:
        if action == "create":
            if not content:
                return "Content required for create."
            existing = self.store.find_by_name(name)
            if existing:
                return f"Skill '{name}' already exists."
            self.store.create(name=name, content=content, **kwargs)
            return f"Skill '{name}' created."
        elif action == "delete":
            skill = self.store.find_by_name(name)
            if not skill:
                return f"Skill '{name}' not found."
            self.store.remove(skill["id"])
            return f"Skill '{name}' deleted."
        elif action == "edit":
            if not content:
                return "Content required for edit."
            skill = self.store.find_by_name(name)
            if not skill:
                self.store.create(name=name, content=content, **kwargs)
                return f"Skill '{name}' created (didn't exist)."
            self.store.remove(skill["id"])
            self.store.create(name=name, content=content, **kwargs)
            return f"Skill '{name}' updated."
        return f"Unknown action: {action}"

    def get_tool_names(self) -> list[str]:
        return ["skills_list", "skill_view", "skill_manage"]

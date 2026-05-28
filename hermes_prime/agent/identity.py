from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_IDENTITY_FILE = "identity.json"


class AgentIdentity:
    """Persistent agent identity with memory-backed context enrichment."""

    def __init__(self, workspace_root: str | Path, memory_store: Any = None):
        self.workspace_root = Path(workspace_root).resolve()
        self.data_path = self.workspace_root / ".hermes-prime" / _IDENTITY_FILE
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        self.memory_store = memory_store
        self._identity: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if self.data_path.exists():
            try:
                self._identity = json.loads(self.data_path.read_text())
            except (json.JSONDecodeError, OSError):
                self._identity = {}
        if not self._identity:
            self._identity = {
                "agent_name": "Hermes Prime",
                "version": 1,
                "persona": "An intelligent AI assistant with access to tools.",
                "created_at": __import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ).isoformat(),
                "memory_tiers": ["working", "episodic", "reflective", "semantic", "strategic"],
            }
            self._save()

    def _save(self) -> None:
        self.data_path.write_text(json.dumps(self._identity, indent=2, default=str))

    @property
    def name(self) -> str:
        return self._identity.get("agent_name", "Hermes Prime")

    @property
    def persona(self) -> str:
        return self._identity.get("persona", "An intelligent AI assistant with access to tools.")

    def update(self, **kwargs: Any) -> None:
        self._identity.update(kwargs)
        self._save()

    def build_system_prompt(self, config_system_prompt: str = "") -> str:
        prompt = config_system_prompt or self.persona
        lines = [f"You are {self.name}.", prompt]
        if self.memory_store:
            try:
                recent = self.memory_store.recall(
                    limit=5,
                    scope="reflective",
                )
                if recent:
                    lines.append("\nRelevant context from past interactions:")
                    for item in recent[:3]:
                        content = item.get("content", item.get("summary", ""))
                        if isinstance(content, str) and len(content) > 100:
                            content = content[:100] + "..."
                        if content:
                            lines.append(f"- {content}")
            except Exception:
                pass
        lines.append(
            "\nYou can use tools to search the web, execute commands, and manage tasks."
        )
        return "\n".join(lines)

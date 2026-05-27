from __future__ import annotations

from pathlib import Path
from typing import Any

from hermes_prime.agent.tool_registry import ToolRegistry
from hermes_prime.agent.types import AgentContext, AgentResult


class AgentLoop:
    def __init__(
        self,
        workspace_root: str | Path = ".",
        sentinel: Any = None,
        vault: Any = None,
        trust_store: Any = None,
        forge: Any = None,
    ) -> None:
        self.workspace_root = str(Path(workspace_root).resolve())
        self.sentinel = sentinel
        self.vault = vault
        self.trust_store = trust_store
        self.forge = forge
        self.tool_registry = ToolRegistry()

    def register_tool(self, name: str, fn: Any, description: str) -> None:
        self.tool_registry.register(name, fn, description)

    def execute_tool(self, name: str, arguments: dict[str, Any]) -> str:
        return self.tool_registry.execute(name, **arguments)

    def run(self, prompt: str, context: AgentContext | None = None) -> AgentResult:
        ctx = context or AgentContext(workspace_root=self.workspace_root)
        from hermes_prime.utils import new_urn_uuid

        session_id = ctx.session_id or new_urn_uuid()
        result = AgentResult(
            session_id=session_id,
            messages=[],
            tool_calls=[],
            summary=f"Processed: {prompt[:60]}",
            success=True,
        )
        return result

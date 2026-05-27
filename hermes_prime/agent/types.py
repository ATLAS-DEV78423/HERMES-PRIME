from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hermes_prime.agent.tool_registry import ToolRegistry


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    tool_call_id: str


@dataclass
class ToolResult:
    tool_call_id: str
    output: str
    error: str | None = None


@dataclass
class AgentContext:
    workspace_root: str
    model: str = "mistral"
    max_iterations: int = 50
    tool_registry: ToolRegistry = field(default_factory=ToolRegistry)
    system_prompt: str = ""
    messages: list[dict[str, Any]] = field(default_factory=list)
    session_id: str | None = None


@dataclass
class AgentResult:
    session_id: str
    messages: list[dict[str, Any]]
    tool_calls: list[ToolCall]
    summary: str
    success: bool

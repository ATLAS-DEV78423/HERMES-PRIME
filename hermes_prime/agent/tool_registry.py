from __future__ import annotations

from typing import Any, Callable


ToolFn = Callable[..., str]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, tuple[ToolFn, str]] = {}

    def register(self, name: str, fn: ToolFn, description: str) -> None:
        self._tools[name] = (fn, description)

    def execute(self, name: str, **kwargs: Any) -> str:
        entry = self._tools.get(name)
        if entry is None:
            raise ValueError(f"Unknown tool: {name}")
        fn, _ = entry
        return fn(**kwargs)

    def get_schema(self, name: str) -> dict[str, Any] | None:
        entry = self._tools.get(name)
        if entry is None:
            return None
        _, desc = entry
        return {
            "name": name,
            "description": desc,
            "parameters": {"type": "object", "properties": {}},
        }

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def tool_schemas(self) -> list[dict[str, Any]]:
        return [self.get_schema(name) for name in self._tools]

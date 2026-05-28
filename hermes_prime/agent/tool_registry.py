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
        fn, desc = entry
        import inspect

        sig = inspect.signature(fn)
        properties: dict[str, Any] = {}
        required: list[str] = []
        for param_name, param in sig.parameters.items():
            param_type = "string"
            if param.annotation is not inspect.Parameter.empty:
                if param.annotation is int:
                    param_type = "integer"
                elif param.annotation is float:
                    param_type = "number"
                elif param.annotation is bool:
                    param_type = "boolean"
            properties[param_name] = {"type": param_type, "description": f"{param_name}"}
            if param.default is inspect.Parameter.empty:
                required.append(param_name)
        return {
            "name": name,
            "description": desc,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def tool_schemas(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for name in self._tools:
            schema = self.get_schema(name)
            if schema is not None:
                result.append(schema)
        return result

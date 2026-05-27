from __future__ import annotations

import pytest

from hermes_prime.agent.types import AgentContext, ToolCall


def test_agent_context_defaults():
    ctx = AgentContext(workspace_root="/tmp/test")
    assert ctx.workspace_root == "/tmp/test"
    assert ctx.max_iterations == 50
    assert ctx.tool_registry is not None


def test_tool_call_validation():
    tc = ToolCall(name="web_search", arguments={"query": "hello"}, tool_call_id="call_1")
    assert tc.name == "web_search"
    assert tc.arguments["query"] == "hello"


def test_tool_registry_register():
    from hermes_prime.agent.tool_registry import ToolRegistry

    registry = ToolRegistry()

    def my_tool(query: str) -> str:
        return f"result: {query}"

    registry.register("my_tool", my_tool, "A test tool")
    assert "my_tool" in registry.list_tools()
    assert registry.execute("my_tool", query="hello") == "result: hello"


def test_tool_registry_unknown_tool():
    from hermes_prime.agent.tool_registry import ToolRegistry

    registry = ToolRegistry()
    with pytest.raises(ValueError, match="Unknown tool"):
        registry.execute("nonexistent")


def test_agent_loop_constructs():
    from hermes_prime.agent.loop import AgentLoop

    loop = AgentLoop(workspace_root=".")
    assert loop.workspace_root is not None
    assert loop.sentinel is None

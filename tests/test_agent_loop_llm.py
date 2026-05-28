from __future__ import annotations

import pytest


def test_agent_loop_with_system_prompt():
    from hermes_prime.agent.loop import AgentLoop
    from hermes_prime.agent.types import AgentContext

    loop = AgentLoop(workspace_root="/tmp/test")
    ctx = AgentContext(
        workspace_root="/tmp/test",
        system_prompt="You are a helpful assistant.",
    )
    result = loop.run("say hello", context=ctx)
    assert result.success
    assert result.session_id is not None


def test_agent_loop_tool_injection():
    from hermes_prime.agent.loop import AgentLoop

    loop = AgentLoop(workspace_root="/tmp/test")

    def search_tool(query: str) -> str:
        return f"results for {query}"

    loop.register_tool("web_search", search_tool, "Search the web")
    result = loop.execute_tool("web_search", arguments={"query": "hello"})
    assert "results for hello" in result


def test_agent_loop_tool_schemas():
    from hermes_prime.agent.loop import AgentLoop

    loop = AgentLoop(workspace_root="/tmp/test")

    def search_tool(query: str) -> str:
        return f"results for {query}"

    loop.register_tool("web_search", search_tool, "Search the web")
    schemas = loop.get_tool_schemas()
    assert len(schemas) == 1
    assert schemas[0]["name"] == "web_search"
    assert "query" in schemas[0]["parameters"]["properties"]
    assert schemas[0]["parameters"]["properties"]["query"]["type"] == "string"


def test_build_messages():
    from hermes_prime.agent.loop import AgentLoop
    from hermes_prime.agent.types import AgentContext

    loop = AgentLoop()
    ctx = AgentContext(
        workspace_root="/tmp/test",
        system_prompt="You are helpful.",
        messages=[{"role": "user", "content": "previous message"}],
    )
    msgs = loop.build_messages("new message", context=ctx)
    assert len(msgs) == 3
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
    assert msgs[2]["content"] == "new message"

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from hermes_prime.llm.client import LLMRequest, LLMResponse


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


def test_agent_loop_run_with_mock_llm_no_tool_call():
    from hermes_prime.agent.loop import AgentLoop
    from hermes_prime.agent.types import AgentContext

    mock_client = MagicMock()
    mock_client.health_check.return_value = True
    mock_client.infer.return_value = LLMResponse(
        model="mistral",
        message_content="Hello! How can I help you?",
        finish_reason="stop",
        tokens_used=10,
        latency_ms=100,
    )

    loop = AgentLoop(workspace_root="/tmp/test", llm_client=mock_client)
    ctx = AgentContext(workspace_root="/tmp/test", model="mistral")
    result = loop.run("say hello", context=ctx)

    assert result.success
    assert result.summary == "Hello! How can I help you?"
    assert len(result.tool_calls) == 0
    mock_client.infer.assert_called_once()


def test_agent_loop_run_with_mock_llm_tool_call():
    from hermes_prime.agent.loop import AgentLoop
    from hermes_prime.agent.types import AgentContext

    mock_client = MagicMock()
    mock_client.health_check.return_value = True
    # First response: tool call, Second response: final
    mock_client.infer.side_effect = [
        LLMResponse(
            model="mistral",
            message_content='```json\n{"tool": "web_search", "arguments": {"query": "hello"}}\n```',
            finish_reason="stop",
            tokens_used=15,
            latency_ms=100,
        ),
        LLMResponse(
            model="mistral",
            message_content="The search result is here.",
            finish_reason="stop",
            tokens_used=5,
            latency_ms=50,
        ),
    ]

    loop = AgentLoop(workspace_root="/tmp/test", llm_client=mock_client)
    loop.register_tool("web_search", lambda query: f"result for {query}", "Search the web")
    ctx = AgentContext(workspace_root="/tmp/test", model="mistral")
    result = loop.run("search for hello", context=ctx)

    assert result.success
    assert result.summary == "The search result is here."
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "web_search"
    assert mock_client.infer.call_count == 2


def test_agent_loop_run_health_check_fails():
    from hermes_prime.agent.loop import AgentLoop
    from hermes_prime.agent.types import AgentContext

    mock_client = MagicMock()
    mock_client.health_check.return_value = False

    loop = AgentLoop(workspace_root="/tmp/test", llm_client=mock_client)
    result = loop.run("hello")

    assert not result.success
    assert "not available" in result.summary.lower()


def test_agent_loop_run_inference_error():
    from hermes_prime.agent.loop import AgentLoop
    from hermes_prime.agent.types import AgentContext

    mock_client = MagicMock()
    mock_client.health_check.return_value = True
    mock_client.infer.side_effect = RuntimeError("connection refused")

    loop = AgentLoop(workspace_root="/tmp/test", llm_client=mock_client)
    result = loop.run("hello")

    assert not result.success
    assert "connection refused" in result.summary.lower()


def test_agent_loop_run_max_iterations():
    from hermes_prime.agent.loop import AgentLoop
    from hermes_prime.agent.types import AgentContext

    mock_client = MagicMock()
    mock_client.health_check.return_value = True
    mock_client.infer.return_value = LLMResponse(
        model="mistral",
        message_content='```json\n{"tool": "web_search", "arguments": {"query": "loop"}}\n```',
        finish_reason="stop",
        tokens_used=10,
        latency_ms=50,
    )

    loop = AgentLoop(workspace_root="/tmp/test", llm_client=mock_client)
    loop.register_tool("web_search", lambda query: "result", "Search")
    ctx = AgentContext(workspace_root="/tmp/test", model="mistral", max_iterations=3)
    result = loop.run("keep searching", context=ctx)

    assert not result.success
    assert "maximum iterations" in result.summary.lower()
    assert len(result.tool_calls) == 3


def test_agent_loop_run_tool_parsing_error():
    from hermes_prime.agent.loop import AgentLoop
    from hermes_prime.agent.types import AgentContext

    mock_client = MagicMock()
    mock_client.health_check.return_value = True
    # Regex matches because "tool" key exists, but JSON has trailing comma — json.loads fails
    mock_client.infer.side_effect = [
        LLMResponse(
            model="mistral",
            message_content='```json\n{"tool": "web_search", "arguments": {"query": "x",}}\n```',
            finish_reason="stop",
            tokens_used=10,
            latency_ms=50,
        ),
        LLMResponse(
            model="mistral",
            message_content="I'll answer directly.",
            finish_reason="stop",
            tokens_used=5,
            latency_ms=50,
        ),
    ]

    loop = AgentLoop(workspace_root="/tmp/test", llm_client=mock_client)
    ctx = AgentContext(workspace_root="/tmp/test", model="mistral")
    result = loop.run("do something", context=ctx)

    assert result.success
    assert result.summary == "I'll answer directly."


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

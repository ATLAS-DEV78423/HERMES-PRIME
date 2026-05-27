import pytest


def test_terminal_tool_registered():
    from hermes_prime.agent.tools.terminal import terminal_execute
    assert callable(terminal_execute)


def test_terminal_schema():
    from hermes_prime.agent.tools.terminal import get_terminal_schema
    schema = get_terminal_schema()
    assert schema["name"] == "terminal"
    assert "command" in schema["parameters"]["properties"]


def test_terminal_echo():
    from hermes_prime.agent.tools.terminal import terminal_execute
    result = terminal_execute("echo hello")
    assert "hello" in result

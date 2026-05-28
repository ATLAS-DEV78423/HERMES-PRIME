from __future__ import annotations

from pathlib import Path

import pytest


def test_repl_constructs():
    from hermes_prime.agent.repl import GovernedREPL

    repl = GovernedREPL(workspace_root="/tmp/test")
    assert repl.workspace_root == str(Path("/tmp/test").resolve())


def test_repl_process_message():
    from hermes_prime.agent.repl import GovernedREPL

    repl = GovernedREPL(workspace_root="/tmp/test")
    response = repl.process_message("hello", "test-session")
    assert response is not None


def test_repl_register_tools():
    from hermes_prime.agent.repl import GovernedREPL

    repl = GovernedREPL(workspace_root="/tmp/test")
    repl.register_tools()
    tools = repl.agent_loop.tool_registry.list_tools()
    assert "web_search" in tools

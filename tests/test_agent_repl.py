from __future__ import annotations

from pathlib import Path

import pytest


def test_repl_constructs(tmp_path: Path):
    from hermes_prime.agent.repl import GovernedREPL

    root = tmp_path / "workspace"
    root.mkdir()
    repl = GovernedREPL(workspace_root=str(root))
    assert repl.workspace_root == str(root.resolve())


def test_repl_process_message(tmp_path: Path):
    from hermes_prime.agent.repl import GovernedREPL

    root = tmp_path / "workspace"
    root.mkdir()
    repl = GovernedREPL(workspace_root=str(root))
    response = repl.process_message("hello", "test-session")
    assert response is not None


def test_repl_register_tools(tmp_path: Path):
    from hermes_prime.agent.repl import GovernedREPL

    root = tmp_path / "workspace"
    root.mkdir()
    repl = GovernedREPL(workspace_root=str(root))
    repl.register_tools()
    tools = repl.agent_loop.tool_registry.list_tools()
    assert "web_search" in tools

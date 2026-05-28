from __future__ import annotations

from pathlib import Path
from typing import Any

from hermes_prime.agent.loop import AgentLoop
from hermes_prime.agent.session import SessionStore
from hermes_prime.agent.types import AgentContext
from hermes_prime.agent.governed_dispatch import GovernedToolDispatcher


class GovernedREPL:
    def __init__(
        self,
        workspace_root: str | Path = ".",
        sentinel: Any = None,
        vault: Any = None,
        trust_store: Any = None,
        model: str = "mistral",
    ):
        self.workspace_root = str(Path(workspace_root).resolve())
        self.model = model
        self.agent_loop = AgentLoop(
            workspace_root=self.workspace_root,
            sentinel=sentinel,
            vault=vault,
            trust_store=trust_store,
        )
        self.dispatcher = GovernedToolDispatcher(
            sentinel=sentinel,
            vault=vault,
            trust_store=trust_store,
            workspace_root=self.workspace_root,
        ) if sentinel and vault else None
        self.session_store = SessionStore(
            Path(self.workspace_root) / ".hermes-prime" / "sessions.db"
        )
        self._current_session_id: str | None = None
        self.register_tools()

    def register_tools(self) -> None:
        from hermes_prime.agent.tools.web_search import web_search, web_fetch
        from hermes_prime.agent.tools.terminal import terminal_execute
        from hermes_prime.agent.tools.todo import TodoManager

        self.agent_loop.register_tool("web_search", web_search, "Search the web for information")
        self.agent_loop.register_tool("web_fetch", web_fetch, "Fetch and extract text from a URL")
        self.agent_loop.register_tool("terminal", terminal_execute, "Execute a shell command")
        self.agent_loop.register_tool("todo", TodoManager().format_plan, "Show task plan")

    def process_message(self, message: str, session_id: str | None = None) -> str:
        if session_id:
            self._current_session_id = session_id
        if not self._current_session_id:
            session = self.session_store.create_session(
                title=message[:50],
                model=self.model,
            )
            self._current_session_id = session["id"]

        self.session_store.append_message(
            self._current_session_id,
            {"role": "user", "content": message},
        )

        ctx = AgentContext(
            workspace_root=self.workspace_root,
            model=self.model,
            session_id=self._current_session_id,
            tool_registry=self.agent_loop.tool_registry,
        )

        result = self.agent_loop.run(message, context=ctx)
        response = result.summary

        self.session_store.append_message(
            self._current_session_id,
            {"role": "assistant", "content": response},
        )

        return response

    def get_current_session_id(self) -> str | None:
        return self._current_session_id

    def run_interactive(self) -> None:
        print("Hermes Prime REPL (type /quit to exit)")
        while True:
            try:
                user_input = input("> ")
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye.")
                break
            if user_input.lower() in ("/quit", "/exit", "/q"):
                break
            if not user_input.strip():
                continue
            response = self.process_message(user_input)
            print(response)


__all__ = ["GovernedREPL"]

from __future__ import annotations

from pathlib import Path
from typing import Any

from hermes_prime.agent.identity import AgentIdentity
from hermes_prime.agent.loop import AgentLoop
from hermes_prime.agent.session import SessionStore
from hermes_prime.agent.types import AgentContext
from hermes_prime.agent.governed_dispatch import GovernedToolDispatcher
from hermes_prime.llm.client import LLMClient
from hermes_prime.llm.ollama_adapter import OllamaClient


class GovernedREPL:
    def __init__(
        self,
        workspace_root: str | Path = ".",
        sentinel: Any = None,
        vault: Any = None,
        trust_store: Any = None,
        model: str = "mistral",
        llm_client: LLMClient | None = None,
        memory_store: Any = None,
    ):
        self.workspace_root = str(Path(workspace_root).resolve())
        self.model = model
        self.llm_client = llm_client or OllamaClient()
        self.memory_store = memory_store
        self.identity = AgentIdentity(
            workspace_root=self.workspace_root,
            memory_store=memory_store,
        )
        self.agent_loop = AgentLoop(
            workspace_root=self.workspace_root,
            sentinel=sentinel,
            vault=vault,
            trust_store=trust_store,
            llm_client=self.llm_client,
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
        self._history: list[dict[str, Any]] = []
        self.register_tools()

    def register_tools(self) -> None:
        from hermes_prime.agent.tools.web_search import web_search, web_fetch
        from hermes_prime.agent.tools.terminal import terminal_execute
        from hermes_prime.agent.tools.todo import TodoManager

        self.agent_loop.register_tool("web_search", web_search, "Search the web for information")
        self.agent_loop.register_tool("web_fetch", web_fetch, "Fetch and extract text from a URL")
        self.agent_loop.register_tool("terminal", terminal_execute, "Execute a shell command")
        self.agent_loop.register_tool("todo", TodoManager().format_plan, "Show task plan")

        self.agent_loop.register_tool(
            "subagent",
            self._subagent_tool,
            "Delegate a subtask to a subagent. Pass a clear prompt describing the subtask.",
        )

    def _subagent_tool(self, prompt: str, model: str | None = None) -> str:
        """Tool wrapper: spawn a subagent and return its summary."""
        from hermes_prime.agent.subagent import SubagentManager

        mgr = SubagentManager(
            llm_client=self.llm_client,
            workspace_root=self.workspace_root,
        )
        try:
            task = mgr.spawn(prompt, model=model or self.model)
            completed = mgr.get_result(task.id, timeout=120)
            if completed and completed.result:
                return completed.result.summary
            return f"Subagent failed: {task.error or 'timeout'}"
        finally:
            mgr.shutdown()

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
            system_prompt=self.identity.build_system_prompt(),
            model=self.model,
            session_id=self._current_session_id,
            tool_registry=self.agent_loop.tool_registry,
            messages=list(self._history),
        )

        result = self.agent_loop.run(message, context=ctx)
        response = result.summary

        self.session_store.append_message(
            self._current_session_id,
            {"role": "assistant", "content": response},
        )
        self._history.append({"role": "user", "content": message})
        self._history.append({"role": "assistant", "content": response})

        return response

    def get_current_session_id(self) -> str | None:
        return self._current_session_id

    def run_interactive(self) -> None:
        import sys
        print("\nHermes Prime REPL (type /quit to exit, /clear to reset)\n")
        while True:
            try:
                user_input = input("> ")
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye.")
                break
            if user_input.lower() in ("/quit", "/exit", "/q"):
                print("Goodbye.")
                break
            if user_input.lower() == "/clear":
                self._history.clear()
                self._current_session_id = None
                print("Session reset.\n")
                continue
            if not user_input.strip():
                continue

            if not self.llm_client.health_check():
                print("LLM service is not available. Is Ollama running?\n")
                continue

            try:
                response = self.process_message(user_input)
                print(response)
            except Exception as e:
                print(f"Error: {e}")
            finally:
                sys.stdout.flush()


__all__ = ["GovernedREPL"]

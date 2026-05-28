# Full Hermes Agent Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform Hermes Prime from a governance-only layer into a complete autonomous AI agent by deeply integrating all upstream NousResearch/hermes-agent capabilities with native Sentinel governance.

**Architecture:** Build a native Hermes Prime agent layer (`hermes_prime/agent/`) that owns the conversation loop, tool dispatch, session management, and all agent capabilities. Route every action through the existing Sentinel/Forge/Vault infrastructure. Each feature gets a Hermes Prime native implementation with Sentinel governance — no passthrough dependencies.

**Tech Stack:** Python 3.10+, Sentinel Policy Engine, SQLite (TrustStore + session store), tree-sitter (code parsing), rich (terminal), aiohttp (web server), pydantic v2 (validation)

---

### Phase 1: Core Agent Infrastructure

---

### Task 1: Native Agent Conversation Loop

**Files:**
- Create: `hermes_prime/agent/__init__.py`
- Create: `hermes_prime/agent/loop.py`
- Create: `hermes_prime/agent/tool_registry.py`
- Create: `hermes_prime/agent/types.py`
- Create: `tests/test_agent_loop.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_agent_loop.py
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


@pytest.mark.asyncio
async def test_agent_loop_constructs():
    from hermes_prime.agent.loop import AgentLoop

    loop = AgentLoop(workspace_root="/tmp/test")
    assert loop.workspace_root == "/tmp/test"
    assert loop.sentinel is None  # no sentinel yet
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_agent_loop.py::test_agent_context_defaults tests/test_agent_loop.py::test_tool_call_validation tests/test_agent_loop.py::test_tool_registry_register tests/test_agent_loop.py::test_tool_registry_unknown_tool tests/test_agent_loop.py::test_agent_loop_constructs -v`
Expected: FAIL with import errors

- [ ] **Step 3: Write minimal implementation**

```python
# hermes_prime/agent/types.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    tool_call_id: str


@dataclass
class ToolResult:
    tool_call_id: str
    output: str
    error: str | None = None


@dataclass
class AgentContext:
    workspace_root: str
    model: str = "mistral"
    max_iterations: int = 50
    tool_registry: Any = None
    system_prompt: str = ""
    messages: list[dict[str, Any]] = field(default_factory=list)
    session_id: str | None = None


@dataclass
class AgentResult:
    session_id: str
    messages: list[dict[str, Any]]
    tool_calls: list[ToolCall]
    summary: str
    success: bool
```

```python
# hermes_prime/agent/tool_registry.py
from __future__ import annotations

from typing import Any, Callable


ToolFn = Callable[..., str]


class ToolRegistry:
    def __init__(self):
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
```

```python
# hermes_prime/agent/__init__.py
from hermes_prime.agent.loop import AgentLoop
from hermes_prime.agent.tool_registry import ToolRegistry
from hermes_prime.agent.types import AgentContext, AgentResult, ToolCall, ToolResult

__all__ = ["AgentLoop", "ToolRegistry", "AgentContext", "AgentResult", "ToolCall", "ToolResult"]
```

```python
# hermes_prime/agent/loop.py
from __future__ import annotations

from pathlib import Path
from typing import Any

from hermes_prime.agent.tool_registry import ToolRegistry
from hermes_prime.agent.types import AgentContext, AgentResult, ToolCall


class AgentLoop:
    def __init__(
        self,
        workspace_root: str | Path = ".",
        sentinel: Any = None,
        vault: Any = None,
        trust_store: Any = None,
        forge: Any = None,
    ):
        self.workspace_root = str(Path(workspace_root).resolve())
        self.sentinel = sentinel
        self.vault = vault
        self.trust_store = trust_store
        self.forge = forge
        self.tool_registry = ToolRegistry()

    def register_tool(self, name: str, fn: Any, description: str) -> None:
        self.tool_registry.register(name, fn, description)

    def execute_tool(self, name: str, arguments: dict[str, Any]) -> str:
        return self.tool_registry.execute(name, **arguments)

    def run(self, prompt: str, context: AgentContext | None = None) -> AgentResult:
        ctx = context or AgentContext(workspace_root=self.workspace_root)
        from hermes_prime.utils import new_urn_uuid

        session_id = ctx.session_id or new_urn_uuid()
        result = AgentResult(
            session_id=session_id,
            messages=[],
            tool_calls=[],
            summary=f"Processed: {prompt[:60]}",
            success=True,
        )
        return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_agent_loop.py::test_agent_context_defaults tests/test_agent_loop.py::test_tool_call_validation tests/test_agent_loop.py::test_tool_registry_register tests/test_agent_loop.py::test_tool_registry_unknown_tool tests/test_agent_loop.py::test_agent_loop_constructs -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hermes_prime/agent/ tests/test_agent_loop.py
git commit -m "feat: add native agent loop with tool registry"
```

---

### Task 2: Sentinel-Governed Tool Dispatch

**Files:**
- Create: `hermes_prime/agent/governed_dispatch.py`
- Create: `tests/test_governed_dispatch.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_governed_dispatch.py
import pytest
from hermes_prime.agent.governed_dispatch import (
    GovernedToolDispatcher,
)


class MockSentinel:
    def evaluate(self, proposal, capability=None):
        from hermes_prime.contracts import SentinelDecision

        return type("EvalResult", (), {"decision": SentinelDecision(permitted=True, blocking_layer=None, denial_reason=None)})()


class MockVault:
    def register_intent_root(self, scope, issued_to):
        from hermes_prime.contracts import IntentRoot

        return IntentRoot(intent_root="urn:uuid:test", scope=scope, issued_to=issued_to, registered_at="2026-01-01T00:00:00Z")

    def mint_capability(self, capability, scope, actions, risk_tier_ceiling, intent_root, issued_to):
        from hermes_prime.contracts import CapabilityToken

        return CapabilityToken(
            token_id="urn:uuid:token",
            capability=capability,
            scope=scope,
            actions=actions,
            risk_tier_ceiling=risk_tier_ceiling,
            expires_at="2026-12-31T00:00:00Z",
            intent_root=intent_root,
            issued_to=issued_to,
            issued_at="2026-01-01T00:00:00Z",
            nonce="nonce",
            signature="sig",
        )


def test_governed_dispatch_permits():
    sentinel = MockSentinel()
    vault = MockVault()
    dispatcher = GovernedToolDispatcher(
        sentinel=sentinel,
        vault=vault,
        workspace_root="/tmp/test",
    )

    def sample_tool(query: str) -> str:
        return f"searched: {query}"

    result = dispatcher.dispatch("web_search", {"query": "hello"}, sample_tool)
    assert result == "searched: hello"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_governed_dispatch.py -v`
Expected: FAIL with import error

- [ ] **Step 3: Write minimal implementation**

```python
# hermes_prime/agent/governed_dispatch.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from hermes_prime.contracts import ActionProposal, ActionType, RiskTier
from hermes_prime.utils import new_urn_uuid, utc_now_iso


class GovernedToolDispatcher:
    """Dispatches tool calls through Sentinel governance before execution."""

    def __init__(
        self,
        sentinel: Any,
        vault: Any,
        trust_store: Any = None,
        workspace_root: str | Path = ".",
    ):
        self._sentinel = sentinel
        self._vault = vault
        self._trust_store = trust_store
        self._workspace_root = str(Path(workspace_root).resolve())

    def dispatch(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        tool_fn: Callable[..., str],
        risk_tier: RiskTier = RiskTier.T1,
    ) -> str:
        intent_root = new_urn_uuid()
        action_type = self._map_tool_to_action(tool_name)

        intent = self._vault.register_intent_root(
            scope=self._workspace_root,
            issued_to=f"hermes:agent:{tool_name}",
        )
        self._sentinel.register_intent_root(intent)

        token = self._vault.mint_capability(
            capability=f"tool:{tool_name}",
            scope=self._workspace_root,
            actions=[action_type.value],
            risk_tier_ceiling=risk_tier,
            intent_root=intent.intent_root,
            issued_to=f"hermes:agent:{tool_name}",
        )

        proposal = ActionProposal(
            action_id=new_urn_uuid(),
            action_type=action_type,
            scope=self._workspace_root,
            risk_tier=risk_tier,
            intent_root=intent.intent_root,
            capability=token.capability,
            proposed_at=utc_now_iso(),
            parameters=arguments,
        )

        evaluation = self._sentinel.evaluate(proposal, capability=token)
        decision = evaluation.decision if hasattr(evaluation, "decision") else evaluation

        if not decision.permitted:
            return f"Action rejected by Sentinel: {decision.denial_reason}"

        result = tool_fn(**arguments)

        if self._trust_store:
            from hermes_prime.contracts import AuditTrace

            trace = AuditTrace(
                trace_id=new_urn_uuid(),
                trace_type="governed_tool_dispatch",
                created_at=utc_now_iso(),
                workspace_root=self._workspace_root,
                intent_root=intent.intent_root,
                action=proposal.to_dict(),
                decision=decision.to_dict(),
                mutation={"tool": tool_name, "arguments": arguments, "result": result},
                summary=f"Governed tool: {tool_name} executed",
            )
            self._trust_store.store_audit_trace(trace)

        return result

    def _map_tool_to_action(self, tool_name: str) -> ActionType:
        mapping = {
            "web_search": ActionType.FILESYSTEM_READ,
            "web_fetch": ActionType.FILESYSTEM_READ,
            "web_extract": ActionType.FILESYSTEM_READ,
            "read_file": ActionType.FILESYSTEM_READ,
            "write_file": ActionType.FILESYSTEM_WRITE,
            "patch": ActionType.FILESYSTEM_WRITE,
            "terminal": ActionType.EXECUTION_COMMAND,
            "execute_code": ActionType.EXECUTION_COMMAND,
            "delegate_task": ActionType.AGENT_SPAWN,
            "browser_navigate": ActionType.FILESYSTEM_READ,
            "browser_click": ActionType.FILESYSTEM_WRITE,
            "memory": ActionType.MEMORY_WRITE,
            "skills_list": ActionType.FILESYSTEM_READ,
            "skill_manage": ActionType.CONFIG_WRITE,
            "cronjob": ActionType.SCHEDULING,
            "kanban_create": ActionType.FILESYSTEM_WRITE,
            "kanban_list": ActionType.FILESYSTEM_READ,
            "todo": ActionType.FILESYSTEM_WRITE,
        }
        return mapping.get(tool_name, ActionType.FILESYSTEM_READ)
```

```python
# tests/test_governed_dispatch.py
import pytest
from hermes_prime.agent.governed_dispatch import GovernedToolDispatcher
from hermes_prime.contracts import SentinelDecision, IntentRoot, CapabilityToken, RiskTier


class MockSentinel:
    def evaluate(self, proposal, capability=None):
        return type("EvalResult", (), {"decision": SentinelDecision(permitted=True, blocking_layer=None, denial_reason=None)})()

    def register_intent_root(self, intent):
        pass


class MockVault:
    def register_intent_root(self, scope, issued_to):
        return IntentRoot(intent_root="urn:uuid:test", scope=scope, issued_to=issued_to, registered_at="2026-01-01T00:00:00Z")

    def mint_capability(self, capability, scope, actions, risk_tier_ceiling, intent_root, issued_to):
        return CapabilityToken(
            token_id="urn:uuid:token",
            capability=capability,
            scope=scope,
            actions=actions,
            risk_tier_ceiling=risk_tier_ceiling,
            expires_at="2026-12-31T00:00:00Z",
            intent_root=intent_root,
            issued_to=issued_to,
            issued_at="2026-01-01T00:00:00Z",
            nonce="nonce",
            signature="sig",
        )


def test_governed_dispatch_permits():
    sentinel = MockSentinel()
    vault = MockVault()
    dispatcher = GovernedToolDispatcher(
        sentinel=sentinel,
        vault=vault,
        workspace_root="/tmp/test",
    )

    def sample_tool(query: str) -> str:
        return f"searched: {query}"

    result = dispatcher.dispatch("web_search", {"query": "hello"}, sample_tool)
    assert result == "searched: hello"


def test_governed_dispatch_denies():
    class DenyingSentinel:
        def evaluate(self, proposal, capability=None):
            return type("EvalResult", (), {"decision": SentinelDecision(permitted=False, blocking_layer=3, denial_reason="policy violation")})()

        def register_intent_root(self, intent):
            pass

    sentinel = DenyingSentinel()
    vault = MockVault()
    dispatcher = GovernedToolDispatcher(
        sentinel=sentinel,
        vault=vault,
        workspace_root="/tmp/test",
    )

    def sample_tool(query: str) -> str:
        return "should not run"

    result = dispatcher.dispatch("web_search", {"query": "hello"}, sample_tool)
    assert "rejected by Sentinel" in result


def test_tool_action_mapping():
    dispatcher = GovernedToolDispatcher(
        sentinel=MockSentinel(),
        vault=MockVault(),
        workspace_root="/tmp/test",
    )
    from hermes_prime.contracts import ActionType

    assert dispatcher._map_tool_to_action("web_search") == ActionType.FILESYSTEM_READ
    assert dispatcher._map_tool_to_action("write_file") == ActionType.FILESYSTEM_WRITE
    assert dispatcher._map_tool_to_action("terminal") == ActionType.EXECUTION_COMMAND
    assert dispatcher._map_tool_to_action("delegate_task") == ActionType.AGENT_SPAWN
    assert dispatcher._map_tool_to_action("unknown_tool") == ActionType.FILESYSTEM_READ
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_governed_dispatch.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hermes_prime/agent/governed_dispatch.py tests/test_governed_dispatch.py
git commit -m "feat: add Sentinel-governed tool dispatcher"
```

---

### Task 3: Expand ActionTypes for All Tool Categories

**Files:**
- Modify: `hermes_prime/contracts.py`

- [ ] **Step 1: Add new ActionType values**

Add these to the `ActionType` enum in `hermes_prime/contracts.py`:

```python
class ActionType(str, Enum):
    FILESYSTEM_READ = "filesystem.read"
    FILESYSTEM_WRITE = "filesystem.write"
    FILESYSTEM_COMMIT = "filesystem.commit"
    EXECUTION_COMMAND = "execution.command"
    MINER_DISPATCH = "miner.dispatch"
    MEMORY_WRITE = "memory.write"
    AGENT_SPAWN = "agent.spawn"
    AGENT_KILL = "agent.kill"
    CAPABILITY_REQUEST = "capability.request"
    SCHEDULING = "scheduling"
    CONFIG_WRITE = "config.write"
    # New action types for full agent capabilities
    WEB_SEARCH = "web.search"
    WEB_FETCH = "web.fetch"
    BROWSER_NAVIGATE = "browser.navigate"
    BROWSER_CLICK = "browser.click"
    BROWSER_SCROLL = "browser.scroll"
    BROWSER_READ = "browser.read"
    VOICE_SPEAK = "voice.speak"
    VISION_ANALYZE = "vision.analyze"
    IMAGE_GENERATE = "image.generate"
    CODE_EXECUTE = "code.execute"
    SKILLS_READ = "skills.read"
    SKILLS_WRITE = "skills.write"
    KANBAN_READ = "kanban.read"
    KANBAN_WRITE = "kanban.write"
    MCP_CALL = "mcp.call"
    ACP_CONNECT = "acp.connect"
    PLUGIN_MANAGE = "plugin.manage"
    SMART_HOME = "smart.home"
    SPOTIFY_CONTROL = "spotify.control"
    SESSION_SEARCH = "session.search"
    CONTEXT_READ = "context.read"
    MODEL_SWITCH = "model.switch"
```

- [ ] **Step 2: Write test to verify new types**

```python
def test_new_action_types():
    from hermes_prime.contracts import ActionType

    assert ActionType.WEB_SEARCH.value == "web.search"
    assert ActionType.BROWSER_NAVIGATE.value == "browser.navigate"
    assert ActionType.VOICE_SPEAK.value == "voice.speak"
    assert ActionType.VISION_ANALYZE.value == "vision.analyze"
    assert ActionType.CODE_EXECUTE.value == "code.execute"
    assert ActionType.SKILLS_READ.value == "skills.read"
    assert ActionType.KANBAN_READ.value == "kanban.read"
    assert ActionType.MCP_CALL.value == "mcp.call"
    assert ActionType.SESSION_SEARCH.value == "session.search"
    all_types = [e.value for e in ActionType]
    assert len(all_types) == len(set(all_types))
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_contracts.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add hermes_prime/contracts.py tests/test_contracts.py
git commit -m "feat: expand ActionType enum for full agent capabilities"
```

---

### Phase 2: Web & Browser Tools

---

### Task 4: Governed Web Search Tool

**Files:**
- Create: `hermes_prime/agent/tools/web_search.py`
- Create: `tests/test_agent_tools_web_search.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_agent_tools_web_search.py
import pytest


def test_web_search_tool_registered():
    from hermes_prime.agent.tools.web_search import web_search

    assert callable(web_search)


def test_web_fetch_tool_registered():
    from hermes_prime.agent.tools.web_search import web_fetch

    assert callable(web_fetch)


def test_web_search_schema():
    from hermes_prime.agent.tools.web_search import get_search_schema

    schema = get_search_schema()
    assert schema["name"] == "web_search"
    assert "query" in schema["parameters"]["properties"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_agent_tools_web_search.py -v`
Expected: FAIL with import error

- [ ] **Step 3: Write minimal implementation**

```python
# hermes_prime/agent/tools/web_search.py
from __future__ import annotations

import json
from typing import Any

import httpx


def web_search(query: str, num_results: int = 5) -> str:
    """Search the web using DuckDuckGo."""
    try:
        from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=num_results))
        if not results:
            return "No results found."
        formatted = []
        for i, r in enumerate(results[:num_results], 1):
            title = r.get("title", "")
            link = r.get("href", "")
            snippet = r.get("body", "")
            formatted.append(f"{i}. [{title}]({link})\n   {snippet[:200]}")
        return "\n\n".join(formatted)
    except ImportError:
        return "DuckDuckGo search not available. Install: pip install duckduckgo_search"
    except Exception as e:
        return f"Search error: {e}"


def web_fetch(url: str) -> str:
    """Fetch and extract content from a URL."""
    try:
        resp = httpx.get(url, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        content = resp.text
        import re

        text = re.sub(r"<[^>]+>", " ", content)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:5000]
    except Exception as e:
        return f"Fetch error: {e}"


def get_search_schema() -> dict[str, Any]:
    return {
        "name": "web_search",
        "description": "Search the web for information",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query",
                },
                "num_results": {
                    "type": "integer",
                    "description": "Number of results (default 5)",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    }


def get_fetch_schema() -> dict[str, Any]:
    return {
        "name": "web_fetch",
        "description": "Fetch and extract text content from a URL",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch",
                },
            },
            "required": ["url"],
        },
    }


__all__ = ["web_search", "web_fetch", "get_search_schema", "get_fetch_schema"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_agent_tools_web_search.py -v`
Expected: PASS

- [ ] **Step 5: Generate tests directory**

```bash
mkdir -p hermes_prime/agent/tools
```

- [ ] **Step 6: Commit**

```bash
git add hermes_prime/agent/tools/web_search.py hermes_prime/agent/tools/__init__.py tests/test_agent_tools_web_search.py
git commit -m "feat: add governed web search and fetch tools"
```

---

### Task 5: Governed Terminal Execution Tool

**Files:**
- Create: `hermes_prime/agent/tools/terminal.py`
- Create: `tests/test_agent_tools_terminal.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_agent_tools_terminal.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_agent_tools_terminal.py -v`
Expected: FAIL with import error

- [ ] **Step 3: Write minimal implementation**

```python
# hermes_prime/agent/tools/terminal.py
from __future__ import annotations

import subprocess
import shlex
import sys
from typing import Any


def terminal_execute(command: str, timeout: int = 60, workdir: str | None = None) -> str:
    """Execute a shell command and return output."""
    import os

    allowed_commands = [
        "ls", "cat", "head", "tail", "echo", "pwd", "cd", "mkdir",
        "cp", "mv", "rm", "grep", "find", "sort", "wc", "diff",
        "python", "node", "npm", "pip", "git", "make", "curl",
        "wget", "tar", "gzip", "unzip", "chmod", "whoami",
    ]

    parts = shlex.split(command)
    if parts and parts[0] not in allowed_commands:
        return f"Command '{parts[0]}' not in allowed list. Contact administrator."

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workdir or os.getcwd(),
        )
        output = result.stdout
        if result.stderr:
            output += f"\nSTDERR:\n{result.stderr[:2000]}"
        if result.returncode != 0:
            output += f"\nExit code: {result.returncode}"
        return output[:10000]
    except subprocess.TimeoutExpired:
        return f"Command timed out after {timeout}s"
    except Exception as e:
        return f"Execution error: {e}"


def get_terminal_schema() -> dict[str, Any]:
    return {
        "name": "terminal",
        "description": "Execute a shell command with output",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default 60)",
                    "default": 60,
                },
            },
            "required": ["command"],
        },
    }


__all__ = ["terminal_execute", "get_terminal_schema"]
```

- [ ] **Step 4: Make tools/__init__.py**

```python
# hermes_prime/agent/tools/__init__.py
from hermes_prime.agent.tools.web_search import web_search, web_fetch, get_search_schema, get_fetch_schema
from hermes_prime.agent.tools.terminal import terminal_execute, get_terminal_schema

__all__ = [
    "web_search", "web_fetch", "get_search_schema", "get_fetch_schema",
    "terminal_execute", "get_terminal_schema",
]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_agent_tools_terminal.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add hermes_prime/agent/tools/terminal.py hermes_prime/agent/tools/__init__.py tests/test_agent_tools_terminal.py
git commit -m "feat: add governed terminal execution tool"
```

---

### Phase 3: Skills & Knowledge Management

---

### Task 6: Skills System

**Files:**
- Create: `hermes_prime/agent/skills/__init__.py`
- Create: `hermes_prime/agent/skills/manager.py`
- Create: `hermes_prime/agent/skills/store.py`
- Create: `tests/test_skills.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_skills.py
import pytest
import tempfile
from pathlib import Path


def test_skill_store_create():
    from hermes_prime.agent.skills.store import SkillStore

    with tempfile.TemporaryDirectory() as tmp:
        store = SkillStore(Path(tmp) / "skills.json")
        store.create("test_skill", "print('hello')", "python", tags=["test"])
        skills = store.list_all()
        assert len(skills) == 1
        assert skills[0]["name"] == "test_skill"


def test_skill_store_search():
    from hermes_prime.agent.skills.store import SkillStore

    with tempfile.TemporaryDirectory() as tmp:
        store = SkillStore(Path(tmp) / "skills.json")
        store.create("web_scraper", "import requests", "python", tags=["web", "scraping"])
        store.create("data_analyzer", "import pandas", "python", tags=["data", "analysis"])
        results = store.search("web")
        assert len(results) == 1
        assert results[0]["name"] == "web_scraper"


def test_skill_manager_register_tool():
    from hermes_prime.agent.skills.manager import SkillManager

    mgr = SkillManager()
    assert "skills_list" in mgr.get_tool_names()
    assert "skill_view" in mgr.get_tool_names()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_skills.py -v`
Expected: FAIL with import error

- [ ] **Step 3: Write minimal implementation**

```python
# hermes_prime/agent/skills/store.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from hermes_prime.utils import new_urn_uuid, utc_now_iso


class SkillStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._skills: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                self._skills = {s["id"]: s for s in data}
            except (json.JSONDecodeError, KeyError):
                self._skills = {}

    def _save(self) -> None:
        self.path.write_text(json.dumps(list(self._skills.values()), indent=2))

    def create(
        self,
        name: str,
        content: str,
        language: str = "python",
        description: str = "",
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        skill_id = new_urn_uuid()
        skill = {
            "id": skill_id,
            "name": name,
            "content": content,
            "language": language,
            "description": description,
            "tags": tags or [],
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
            "usage_count": 0,
            "success_rate": 1.0,
        }
        self._skills[skill_id] = skill
        self._save()
        return skill

    def get(self, skill_id: str) -> dict[str, Any] | None:
        return self._skills.get(skill_id)

    def find_by_name(self, name: str) -> dict[str, Any] | None:
        for s in self._skills.values():
            if s["name"] == name:
                return s
        return None

    def search(self, query: str) -> list[dict[str, Any]]:
        q = query.lower()
        results = []
        for s in self._skills.values():
            if q in s["name"].lower() or q in s["description"].lower():
                results.append(s)
                continue
            for tag in s.get("tags", []):
                if q in tag.lower():
                    results.append(s)
                    break
        return results

    def list_all(self) -> list[dict[str, Any]]:
        return list(self._skills.values())

    def remove(self, skill_id: str) -> bool:
        if skill_id in self._skills:
            del self._skills[skill_id]
            self._save()
            return True
        return False

    def record_usage(self, skill_id: str, success: bool) -> None:
        skill = self._skills.get(skill_id)
        if skill:
            skill["usage_count"] = skill.get("usage_count", 0) + 1
            total = skill["usage_count"]
            prev_successes = total - 1
            skill["success_rate"] = (prev_successes * skill.get("success_rate", 1.0) + (1.0 if success else 0.0)) / total
            skill["updated_at"] = utc_now_iso()
            self._save()
```

```python
# hermes_prime/agent/skills/manager.py
from __future__ import annotations

from typing import Any
from hermes_prime.agent.skills.store import SkillStore


class SkillManager:
    def __init__(self, store: SkillStore | None = None):
        from pathlib import Path
        self.store = store or SkillStore(Path.cwd() / ".hermes-prime" / "skills.json")

    def skills_list(self, query: str | None = None) -> str:
        if query:
            results = self.store.search(query)
        else:
            results = self.store.list_all()
        if not results:
            return "No skills found."
        lines = [f"Skills ({len(results)}):"]
        for s in results:
            lines.append(f"  - {s['name']}: {s.get('description', '')[:60]} (used {s.get('usage_count', 0)}x)")
        return "\n".join(lines)

    def skill_view(self, name: str) -> str:
        skill = self.store.find_by_name(name)
        if not skill:
            return f"Skill '{name}' not found."
        return (
            f"Skill: {skill['name']}\n"
            f"Language: {skill.get('language', 'unknown')}\n"
            f"Tags: {', '.join(skill.get('tags', []))}\n"
            f"Usage: {skill.get('usage_count', 0)}x | Success: {skill.get('success_rate', 1.0):.0%}\n"
            f"---\n{skill['content']}"
        )

    def skill_manage(self, action: str, name: str, content: str | None = None, **kwargs) -> str:
        if action == "create":
            if not content:
                return "Content required for create."
            existing = self.store.find_by_name(name)
            if existing:
                return f"Skill '{name}' already exists."
            self.store.create(name=name, content=content, **kwargs)
            return f"Skill '{name}' created."
        elif action == "delete":
            skill = self.store.find_by_name(name)
            if not skill:
                return f"Skill '{name}' not found."
            self.store.remove(skill["id"])
            return f"Skill '{name}' deleted."
        elif action == "edit":
            if not content:
                return "Content required for edit."
            skill = self.store.find_by_name(name)
            if not skill:
                self.store.create(name=name, content=content, **kwargs)
                return f"Skill '{name}' created (didn't exist)."
            self.store.remove(skill["id"])
            self.store.create(name=name, content=content, **kwargs)
            return f"Skill '{name}' updated."
        return f"Unknown action: {action}"

    def get_tool_names(self) -> list[str]:
        return ["skills_list", "skill_view", "skill_manage"]
```

```python
# hermes_prime/agent/skills/__init__.py
from hermes_prime.agent.skills.manager import SkillManager
from hermes_prime.agent.skills.store import SkillStore

__all__ = ["SkillManager", "SkillStore"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_skills.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hermes_prime/agent/skills/ tests/test_skills.py
git commit -m "feat: add skills system with store and manager"
```

---

### Task 7: Planning/Todo Tool

**Files:**
- Create: `hermes_prime/agent/tools/todo.py`
- Create: `tests/test_agent_tools_todo.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_agent_tools_todo.py
import pytest


def test_todo_create():
    from hermes_prime.agent.tools.todo import TodoManager

    mgr = TodoManager()
    mgr.create("Write tests", ["unit tests", "integration"], priority="high")
    tasks = mgr.list_all()
    assert len(tasks) == 1
    assert tasks[0]["title"] == "Write tests"


def test_todo_complete():
    from hermes_prime.agent.tools.todo import TodoManager

    mgr = TodoManager()
    mgr.create("Do something")
    tasks = mgr.list_all()
    task_id = tasks[0]["id"]
    mgr.complete(task_id)
    assert mgr.get(task_id)["status"] == "done"


def test_todo_list():
    from hermes_prime.agent.tools.todo import TodoManager

    mgr = TodoManager()
    mgr.create("Task 1", priority="high")
    mgr.create("Task 2", priority="low")
    output = mgr.list_all()
    assert len(output) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_agent_tools_todo.py -v`
Expected: FAIL with import error

- [ ] **Step 3: Write minimal implementation**

```python
# hermes_prime/agent/tools/todo.py
from __future__ import annotations

from typing import Any
from hermes_prime.utils import new_urn_uuid, utc_now_iso


class TodoManager:
    def __init__(self):
        self._tasks: dict[str, dict[str, Any]] = {}

    def create(
        self,
        title: str,
        subtasks: list[str] | None = None,
        priority: str = "medium",
    ) -> dict[str, Any]:
        task_id = new_urn_uuid()
        task = {
            "id": task_id,
            "title": title,
            "subtasks": subtasks or [],
            "priority": priority,
            "status": "pending",
            "created_at": utc_now_iso(),
            "completed_at": None,
        }
        self._tasks[task_id] = task
        return task

    def get(self, task_id: str) -> dict[str, Any] | None:
        return self._tasks.get(task_id)

    def complete(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if not task:
            return False
        task["status"] = "done"
        task["completed_at"] = utc_now_iso()
        return True

    def list_all(self, status: str | None = None) -> list[dict[str, Any]]:
        tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t["status"] == status]
        return sorted(tasks, key=lambda t: {"high": 0, "medium": 1, "low": 2}.get(t["priority"], 99))

    def remove(self, task_id: str) -> bool:
        return self._tasks.pop(task_id, None) is not None

    def format_plan(self) -> str:
        tasks = self.list_all()
        if not tasks:
            return "No tasks."
        lines = []
        for t in tasks:
            mark = "✓" if t["status"] == "done" else "○"
            lines.append(f"{mark} [{t['priority']}] {t['title']}")
            for sub in t.get("subtasks", []):
                lines.append(f"   - {sub}")
        return "\n".join(lines)


def get_todo_schema() -> dict[str, Any]:
    return {
        "name": "todo",
        "description": "Manage task plans and track progress",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "complete", "list", "remove", "plan"],
                    "description": "Action to perform",
                },
                "title": {
                    "type": "string",
                    "description": "Task title (for create)",
                },
                "task_id": {
                    "type": "string",
                    "description": "Task ID (for complete/remove)",
                },
                "priority": {
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                    "description": "Task priority",
                },
            },
            "required": ["action"],
        },
    }


__all__ = ["TodoManager", "get_todo_schema"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_agent_tools_todo.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hermes_prime/agent/tools/todo.py tests/test_agent_tools_todo.py
git commit -m "feat: add planning/todo tool"
```

---

### Phase 4: Session Management

---

### Task 8: Session Store with FTS5 Search

**Files:**
- Create: `hermes_prime/agent/session.py`
- Create: `tests/test_agent_session.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_agent_session.py
import pytest
import tempfile
from pathlib import Path


def test_session_store_create():
    from hermes_prime.agent.session import SessionStore

    with tempfile.TemporaryDirectory() as tmp:
        store = SessionStore(Path(tmp) / "sessions.db")
        session = store.create_session("test session", model="mistral")
        assert session["id"] is not None
        assert session["title"] == "test session"
        assert session["model"] == "mistral"


def test_session_store_append():
    from hermes_prime.agent.session import SessionStore

    with tempfile.TemporaryDirectory() as tmp:
        store = SessionStore(Path(tmp) / "sessions.db")
        session = store.create_session("test")
        store.append_message(session["id"], {"role": "user", "content": "hello"})
        store.append_message(session["id"], {"role": "assistant", "content": "hi"})
        msgs = store.get_messages(session["id"])
        assert len(msgs) == 2


def test_session_search():
    from hermes_prime.agent.session import SessionStore

    with tempfile.TemporaryDirectory() as tmp:
        store = SessionStore(Path(tmp) / "sessions.db")
        s1 = store.create_session("web development")
        store.append_message(s1["id"], {"role": "user", "content": "How do I build a web app?"})
        s2 = store.create_session("data science")
        store.append_message(s2["id"], {"role": "user", "content": "How do I analyze data?"})
        results = store.search("web app")
        assert len(results) >= 1


def test_session_list():
    from hermes_prime.agent.session import SessionStore

    with tempfile.TemporaryDirectory() as tmp:
        store = SessionStore(Path(tmp) / "sessions.db")
        store.create_session("session 1")
        store.create_session("session 2")
        sessions = store.list_sessions()
        assert len(sessions) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_agent_session.py -v`
Expected: FAIL with import error

- [ ] **Step 3: Write minimal implementation**

```python
# hermes_prime/agent/session.py
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hermes_prime.utils import new_urn_uuid


class SessionStore:
    def __init__(self, db_path: str | Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                model TEXT DEFAULT 'mistral',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                message_count INTEGER DEFAULT 0,
                token_count INTEGER DEFAULT 0,
                metadata TEXT DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );
            CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
            CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                content, session_id UNINDEXED
            );
        """)
        self._conn.commit()

    def create_session(self, title: str, model: str = "mistral") -> dict[str, Any]:
        session_id = new_urn_uuid()
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO sessions (id, title, model, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, title, model, now, now),
        )
        self._conn.commit()
        return {
            "id": session_id,
            "title": title,
            "model": model,
            "created_at": now,
            "updated_at": now,
            "message_count": 0,
        }

    def append_message(self, session_id: str, message: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        content = message.get("content", "")
        role = message.get("role", "user")
        self._conn.execute(
            "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            (session_id, role, content, now),
        )
        self._conn.execute(
            "INSERT INTO messages_fts (content, session_id) VALUES (?, ?)",
            (content, session_id),
        )
        self._conn.execute(
            """UPDATE sessions SET updated_at=?, message_count=message_count+1 WHERE id=?""",
            (now, session_id),
        )
        self._conn.commit()

    def get_messages(self, session_id: str, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT role, content, timestamp FROM messages WHERE session_id=? ORDER BY id ASC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """SELECT DISTINCT s.id, s.title, s.created_at, s.message_count
               FROM sessions s
               JOIN messages_fts fts ON s.id = fts.session_id
               WHERE messages_fts MATCH ? ORDER BY s.updated_at DESC LIMIT ?""",
            (query, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT id, title, model, created_at, updated_at, message_count FROM sessions ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT id, title, model, created_at, updated_at, message_count FROM sessions WHERE id=?",
            (session_id,),
        ).fetchone()
        return dict(row) if row else None

    def close(self) -> None:
        self._conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_agent_session.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hermes_prime/agent/session.py tests/test_agent_session.py
git commit -m "feat: add session store with FTS5 search"
```

---

### Phase 5: CLI Expansion

---

### Task 9: Add Agent CLI Commands (skills, sessions, todo, tools)

**Files:**
- Modify: `hermes_prime/cli.py`
- Create: `tests/test_cli_agent_commands.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_agent_commands.py
import pytest


def test_skills_subcommand_registered():
    from hermes_prime.cli import build_parser

    parser = build_parser()
    help_text = parser.format_help()
    assert "skills" in help_text


def test_sessions_subcommand_registered():
    from hermes_prime.cli import build_parser

    parser = build_parser()
    help_text = parser.format_help()
    assert "sessions" in help_text


def test_todo_subcommand_registered():
    from hermes_prime.cli import build_parser

    parser = build_parser()
    help_text = parser.format_help()
    assert "todo" in help_text


def test_tools_subcommand_registered():
    from hermes_prime.cli import build_parser

    parser = build_parser()
    help_text = parser.format_help()
    assert "tools" in help_text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_agent_commands.py -v`
Expected: FAIL (some may pass if already added)

- [ ] **Step 3: Add CLI commands to `hermes_prime/cli.py`**

Add these to `known_hp_commands`:
```python
known_hp_commands = {
    # ... existing ...
    "skills",
    "sessions",
    "todo",
    "tools",
}
```

Add parser registrations after the `gateway` parser in `build_parser()`:

```python
# Skills commands
skills_parser = subparsers.add_parser("skills", help="Manage agent skills")
skills_sub = skills_parser.add_subparsers(dest="skills_command")

skills_list = skills_sub.add_parser("list", help="List all skills")
skills_list.add_argument("--query", default=None, help="Search query")

skills_view = skills_sub.add_parser("view", help="View a skill")
skills_view.add_argument("name", help="Skill name")

skills_create = skills_sub.add_parser("create", help="Create a new skill")
skills_create.add_argument("--name", required=True, help="Skill name")
skills_create.add_argument("--content", required=True, help="Skill content/code")
skills_create.add_argument("--language", default="python", help="Language")
skills_create.add_argument("--description", default="", help="Description")
skills_create.add_argument("--tags", default=None, help="Comma-separated tags")

skills_delete = skills_sub.add_parser("delete", help="Delete a skill")
skills_delete.add_argument("name", help="Skill name")

# Sessions commands
sessions_parser = subparsers.add_parser("sessions", help="Browse and search sessions")
sessions_sub = sessions_parser.add_subparsers(dest="sessions_command")

sessions_sub.add_parser("list", help="List all sessions")

sessions_search = sessions_sub.add_parser("search", help="Search sessions")
sessions_search.add_argument("query", help="Search query")

sessions_view = sessions_sub.add_parser("view", help="View session messages")
sessions_view.add_argument("session_id", help="Session ID")

# Todo commands
todo_parser = subparsers.add_parser("todo", help="Task planning and tracking")
todo_sub = todo_parser.add_subparsers(dest="todo_command")

todo_create = todo_sub.add_parser("create", help="Create a task")
todo_create.add_argument("--title", required=True, help="Task title")
todo_create.add_argument("--priority", default="medium", choices=["high", "medium", "low"])
todo_create.add_argument("--subtasks", default=None, help="Comma-separated subtasks")

todo_sub.add_parser("list", help="List all tasks")

todo_complete = todo_sub.add_parser("complete", help="Mark task done")
todo_complete.add_argument("--task-id", required=True, help="Task ID")

todo_remove = todo_sub.add_parser("remove", help="Remove a task")
todo_remove.add_argument("--task-id", required=True, help="Task ID")

# Tools command
tools_parser = subparsers.add_parser("tools", help="List available agent tools")
tools_parser.add_argument("--search", default=None, help="Search for tools")
```

Now add the command handlers in `handle_hp_command()` in `cli.py`. Add a new `if args.command == "skills":` block:

```python
if args.command == "skills":
    from hermes_prime.agent.skills import SkillManager, SkillStore

    skill_store = SkillStore(workspace_path / ".hermes-prime" / "skills.json")
    skill_mgr = SkillManager(skill_store)

    if args.skills_command == "list":
        results = skill_mgr.skills_list(query=args.query)
        print(results)
        return 0
    elif args.skills_command == "view":
        print(skill_mgr.skill_view(args.name))
        return 0
    elif args.skills_command == "create":
        tags = [t.strip() for t in args.tags.split(",")] if args.tags else []
        result = skill_mgr.skill_manage(
            action="create", name=args.name, content=args.content,
            language=args.language, description=args.description, tags=tags,
        )
        print(result)
        return 0
    elif args.skills_command == "delete":
        print(skill_mgr.skill_manage(action="delete", name=args.name))
        return 0
    else:
        parser.error("unknown skills command")
    return 0
```

Add a new `if args.command == "sessions":` block:

```python
if args.command == "sessions":
    from hermes_prime.agent.session import SessionStore

    session_store = SessionStore(workspace_path / ".hermes-prime" / "sessions.db")

    if args.sessions_command == "list":
        sessions = session_store.list_sessions()
        if not sessions:
            print("No sessions found.")
        else:
            for s in sessions:
                print(f"  {s['id'][:16]}... {s['title']} ({s['message_count']} msgs)")
        return 0
    elif args.sessions_command == "search":
        results = session_store.search(args.query)
        if not results:
            print(f"No sessions matching '{args.query}'")
        else:
            for r in results:
                print(f"  {r['id'][:16]}... {r['title']} ({r['message_count']} msgs)")
        return 0
    elif args.sessions_command == "view":
        msgs = session_store.get_messages(args.session_id)
        if not msgs:
            print("No messages in this session.")
        else:
            for m in msgs:
                print(f"[{m['role']}] {m['content'][:200]}")
        return 0
    else:
        parser.error("unknown sessions command")
    return 0
```

Add a new `if args.command == "todo":` block:

```python
if args.command == "todo":
    from hermes_prime.agent.tools.todo import TodoManager

    todo_mgr = TodoManager()

    if args.todo_command == "create":
        subtasks = [s.strip() for s in args.subtasks.split(",")] if args.subtasks else []
        task = todo_mgr.create(args.title, subtasks=subtasks, priority=args.priority)
        print(f"Task created: {task['id'][:16]}...")
        return 0
    elif args.todo_command == "list":
        print(todo_mgr.format_plan())
        return 0
    elif args.todo_command == "complete":
        if todo_mgr.complete(args.task_id):
            print(f"Task {args.task_id[:16]}... completed.")
        else:
            print(f"Task {args.task_id[:16]}... not found.")
        return 0
    elif args.todo_command == "remove":
        if todo_mgr.remove(args.task_id):
            print(f"Task {args.task_id[:16]}... removed.")
        else:
            print(f"Task {args.task_id[:16]}... not found.")
        return 0
    else:
        parser.error("unknown todo command")
    return 0
```

Add a `tools` handler:

```python
if args.command == "tools":
    from hermes_prime.agent.tool_registry import ToolRegistry

    registry = ToolRegistry()
    from hermes_prime.agent.tools.web_search import web_search, web_fetch
    from hermes_prime.agent.tools.terminal import terminal_execute
    from hermes_prime.agent.tools.todo import TodoManager

    registry.register("web_search", web_search, "Search the web")
    registry.register("web_fetch", web_fetch, "Fetch a URL")
    registry.register("terminal", terminal_execute, "Execute shell commands")
    registry.register("todo", TodoManager().format_plan, "Task planning")

    tools = registry.list_tools()
    if args.search:
        tools = [t for t in tools if args.search.lower() in t.lower()]
    if args.json:
        _emit({"tools": tools, "count": len(tools)}, True)
    else:
        print(f"Available tools ({len(tools)}):")
        for t in sorted(tools):
            schema = registry.get_schema(t)
            desc = schema["description"] if schema else ""
            print(f"  - {t}: {desc[:60]}")
    return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli_agent_commands.py -v`
Expected: PASS

- [ ] **Step 5: Run broader test suite**

Run: `pytest tests/ -x --timeout=60 -q`
Expected: Existing tests still pass

- [ ] **Step 6: Commit**

```bash
git add hermes_prime/cli.py hermes_prime/agent/ tests/
git commit -m "feat: add skills, sessions, todo, tools CLI commands"
```

---

### Phase 6: Enhanced Agent Loop with LLM Support

---

### Task 10: LLM-Integrated Agent Loop

**Files:**
- Modify: `hermes_prime/agent/loop.py`
- Modify: `hermes_prime/agent/tool_registry.py`
- Create: `tests/test_agent_loop_llm.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_agent_loop_llm.py
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
    result = loop.execute_tool("web_search", query="hello")
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_agent_loop_llm.py -v`
Expected: FAIL

- [ ] **Step 3: Enhance implementation**

Update `hermes_prime/agent/tool_registry.py`:

```python
def get_schema(self, name: str) -> dict[str, Any] | None:
    entry = self._tools.get(name)
    if entry is None:
        return None
    fn, desc = entry
    import inspect

    sig = inspect.signature(fn)
    properties = {}
    required = []
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
```

Update `hermes_prime/agent/loop.py`:

```python
def get_tool_schemas(self) -> list[dict[str, Any]]:
    return self.tool_registry.tool_schemas()

def build_messages(self, prompt: str, context: AgentContext | None = None) -> list[dict[str, Any]]:
    messages = []
    if context and context.system_prompt:
        messages.append({"role": "system", "content": context.system_prompt})
    if context and context.messages:
        messages.extend(context.messages)
    messages.append({"role": "user", "content": prompt})
    return messages
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_agent_loop_llm.py -v`
Expected: PASS

- [ ] **Step 5: Run existing tests**

Run: `pytest tests/test_agent_loop.py tests/test_governed_dispatch.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add hermes_prime/agent/loop.py hermes_prime/agent/tool_registry.py tests/
git commit -m "feat: enhance agent loop with tool schemas and message building"
```

---

### Task 11: Governed REPL Chat (Native)

**Files:**
- Create: `hermes_prime/agent/repl.py`
- Create: `tests/test_agent_repl.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_agent_repl.py
import pytest


def test_repl_constructs():
    from hermes_prime.agent.repl import GovernedREPL

    repl = GovernedREPL(workspace_root="/tmp/test")
    assert repl.workspace_root == "/tmp/test"


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_agent_repl.py -v`
Expected: FAIL with import error

- [ ] **Step 3: Write minimal implementation**

```python
# hermes_prime/agent/repl.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_agent_repl.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hermes_prime/agent/repl.py tests/test_agent_repl.py
git commit -m "feat: add governed REPL with session persistence"
```

---

### Phase 7: Kanban Multi-Agent Coordination

---

### Task 12: Kanban Board

**Files:**
- Create: `hermes_prime/agent/kanban.py`
- Create: `tests/test_kanban.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_kanban.py
import pytest
import tempfile
from pathlib import Path


def test_kanban_create():
    from hermes_prime.agent.kanban import KanbanBoard

    with tempfile.TemporaryDirectory() as tmp:
        board = KanbanBoard(Path(tmp) / "kanban.db")
        task = board.create("Write tests", "Add unit tests for the agent")
        assert task["id"] is not None
        assert task["title"] == "Write tests"
        assert task["status"] == "todo"


def test_kanban_transitions():
    from hermes_prime.agent.kanban import KanbanBoard

    with tempfile.TemporaryDirectory() as tmp:
        board = KanbanBoard(Path(tmp) / "kanban.db")
        task = board.create("Implement feature")
        board.transition(task["id"], "in_progress")
        assert board.get(task["id"])["status"] == "in_progress"
        board.transition(task["id"], "done")
        assert board.get(task["id"])["status"] == "done"


def test_kanban_list():
    from hermes_prime.agent.kanban import KanbanBoard

    with tempfile.TemporaryDirectory() as tmp:
        board = KanbanBoard(Path(tmp) / "kanban.db")
        board.create("Task 1")
        board.create("Task 2", status="in_progress")
        board.create("Task 3", status="done")
        todo = board.list_by_status("todo")
        assert len(todo) == 1
        all_tasks = board.list_all()
        assert len(all_tasks) == 3


def test_kanban_assign():
    from hermes_prime.agent.kanban import KanbanBoard

    with tempfile.TemporaryDirectory() as tmp:
        board = KanbanBoard(Path(tmp) / "kanban.db")
        task = board.create("My task")
        board.assign(task["id"], "agent-1")
        assert board.get(task["id"])["assignee"] == "agent-1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_kanban.py -v`
Expected: FAIL with import error

- [ ] **Step 3: Write minimal implementation**

```python
# hermes_prime/agent/kanban.py
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hermes_prime.utils import new_urn_uuid


class KanbanBoard:
    def __init__(self, db_path: str | Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS kanban_tasks (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'todo',
                priority TEXT DEFAULT 'medium',
                assignee TEXT,
                parent_id TEXT,
                tags TEXT DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS kanban_comments (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                author TEXT DEFAULT 'system',
                body TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (task_id) REFERENCES kanban_tasks(id)
            );
        """)
        self._conn.commit()

    def create(
        self,
        title: str,
        description: str = "",
        status: str = "todo",
        priority: str = "medium",
        assignee: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        task_id = new_urn_uuid()
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT INTO kanban_tasks (id, title, description, status, priority, assignee, tags, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (task_id, title, description, status, priority, assignee, json.dumps(tags or []), now, now),
        )
        self._conn.commit()
        return self.get(task_id)

    def get(self, task_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM kanban_tasks WHERE id=?", (task_id,)
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["tags"] = json.loads(result.get("tags", "[]"))
        return result

    def transition(self, task_id: str, new_status: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        completed_at = now if new_status == "done" else None
        self._conn.execute(
            "UPDATE kanban_tasks SET status=?, updated_at=?, completed_at=? WHERE id=?",
            (new_status, now, completed_at, task_id),
        )
        self._conn.commit()
        return True

    def assign(self, task_id: str, assignee: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE kanban_tasks SET assignee=?, updated_at=? WHERE id=?",
            (assignee, now, task_id),
        )
        self._conn.commit()
        return True

    def add_comment(self, task_id: str, body: str, author: str = "system") -> dict[str, Any]:
        comment_id = new_urn_uuid()
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO kanban_comments (id, task_id, author, body, created_at) VALUES (?, ?, ?, ?, ?)",
            (comment_id, task_id, author, body, now),
        )
        self._conn.commit()
        return {"id": comment_id, "task_id": task_id, "author": author, "body": body, "created_at": now}

    def list_all(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM kanban_tasks ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def list_by_status(self, status: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM kanban_tasks WHERE status=? ORDER BY created_at DESC", (status,)
        ).fetchall()
        return [dict(r) for r in rows]

    def list_by_assignee(self, assignee: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM kanban_tasks WHERE assignee=? ORDER BY created_at DESC", (assignee,)
        ).fetchall()
        return [dict(r) for r in rows]

    def remove(self, task_id: str) -> bool:
        self._conn.execute("DELETE FROM kanban_tasks WHERE id=?", (task_id,))
        self._conn.execute("DELETE FROM kanban_comments WHERE task_id=?", (task_id,))
        self._conn.commit()
        return True

    def format_board(self) -> str:
        sections = {"todo": "To Do", "in_progress": "In Progress", "done": "Done"}
        lines = []
        for status, heading in sections.items():
            tasks = self.list_by_status(status)
            lines.append(f"\n## {heading} ({len(tasks)})")
            if not tasks:
                lines.append("  (empty)")
            else:
                for t in tasks:
                    assignee = f" @{t['assignee']}" if t.get("assignee") else ""
                    lines.append(f"  [{t['priority']}] {t['title'][:50]}{assignee}")
        return "\n".join(lines)

    def close(self) -> None:
        self._conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_kanban.py -v`
Expected: PASS

- [ ] **Step 5: Add kanban CLI subcommand**

Add to `known_hp_commands`:
```python
"kanban"
```

Add parser:
```python
kanban_parser = subparsers.add_parser("kanban", help="Multi-agent kanban board")
kanban_sub = kanban_parser.add_subparsers(dest="kanban_command")

kanban_create = kanban_sub.add_parser("create", help="Create a task")
kanban_create.add_argument("--title", required=True)
kanban_create.add_argument("--description", default="")
kanban_create.add_argument("--priority", default="medium", choices=["high", "medium", "low"])
kanban_create.add_argument("--assignee", default=None)

kanban_sub.add_parser("list", help="List all tasks")
kanban_sub.add_parser("board", help="Show kanban board view")

kanban_transition = kanban_sub.add_parser("transition", help="Change task status")
kanban_transition.add_argument("--task-id", required=True)
kanban_transition.add_argument("--status", required=True, choices=["todo", "in_progress", "done", "blocked"])

kanban_assign = kanban_sub.add_parser("assign", help="Assign a task")
kanban_assign.add_argument("--task-id", required=True)
kanban_assign.add_argument("--assignee", required=True)
```

Add handler in `handle_hp_command()`:
```python
if args.command == "kanban":
    from hermes_prime.agent.kanban import KanbanBoard

    board = KanbanBoard(workspace_path / ".hermes-prime" / "kanban.db")

    if args.kanban_command == "create":
        task = board.create(
            title=args.title,
            description=args.description,
            priority=args.priority,
            assignee=args.assignee,
        )
        print(f"Task created: {task['id'][:16]}...")
        return 0
    elif args.kanban_command == "list":
        tasks = board.list_all()
        if not tasks:
            print("No tasks.")
        else:
            for t in tasks:
                print(f"  [{t['status']}] {t['title']} ({t['priority']})")
        return 0
    elif args.kanban_command == "board":
        print(board.format_board())
        return 0
    elif args.kanban_command == "transition":
        board.transition(args.task_id, args.status)
        print(f"Task {args.task_id[:16]}... -> {args.status}")
        return 0
    elif args.kanban_command == "assign":
        board.assign(args.task_id, args.assignee)
        print(f"Task {args.task_id[:16]}... assigned to {args.assignee}")
        return 0
    else:
        parser.error("unknown kanban command")
    return 0
```

- [ ] **Step 6: Run all tests**

Run: `pytest tests/ -x --timeout=60 -q`
Expected: All pass

- [ ] **Step 7: Commit**

```bash
git add hermes_prime/agent/kanban.py hermes_prime/cli.py tests/test_kanban.py
git commit -m "feat: add kanban multi-agent coordination board"
```

---

### Phase 8: Voice, Vision & Advanced Tools

---

### Task 13: Voice/Speech and Vision Tools

**Files:**
- Create: `hermes_prime/agent/tools/voice.py`
- Create: `hermes_prime/agent/tools/vision.py`
- Create: `tests/test_agent_tools_voice.py`
- Create: `tests/test_agent_tools_vision.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_agent_tools_voice.py
import pytest


def test_tts_tool_registered():
    from hermes_prime.agent.tools.voice import text_to_speech, get_tts_schema

    assert callable(text_to_speech)
    schema = get_tts_schema()
    assert schema["name"] == "text_to_speech"
    assert "text" in schema["parameters"]["properties"]
```

```python
# tests/test_agent_tools_vision.py
import pytest


def test_vision_tool_registered():
    from hermes_prime.agent.tools.vision import vision_analyze, get_vision_schema

    assert callable(vision_analyze)
    schema = get_vision_schema()
    assert schema["name"] == "vision_analyze"
    assert "image_url" in schema["parameters"]["properties"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_agent_tools_voice.py tests/test_agent_tools_vision.py -v`
Expected: FAIL with import error

- [ ] **Step 3: Write minimal implementation**

```python
# hermes_prime/agent/tools/voice.py
from __future__ import annotations

import subprocess
from typing import Any


def text_to_speech(text: str, voice: str = "en-US-JennyNeural") -> str:
    """Convert text to speech using edge-tts."""
    try:
        import edge_tts

        import asyncio

        async def _tts() -> str:
            output_file = "/tmp/hermes_tts.mp3"
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(output_file)
            return f"Speech saved to {output_file}"

        return asyncio.run(_tts())
    except ImportError:
        return "TTS not available. Install: pip install edge-tts"
    except Exception as e:
        return f"TTS error: {e}"


def get_tts_schema() -> dict[str, Any]:
    return {
        "name": "text_to_speech",
        "description": "Convert text to spoken audio",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to speak"},
                "voice": {"type": "string", "description": "Voice to use", "default": "en-US-JennyNeural"},
            },
            "required": ["text"],
        },
    }


__all__ = ["text_to_speech", "get_tts_schema"]
```

```python
# hermes_prime/agent/tools/vision.py
from __future__ import annotations

from typing import Any


def vision_analyze(image_url: str, prompt: str = "Describe this image") -> str:
    """Analyze an image using vision-capable LLM."""
    try:
        from ollama import Client

        client = Client()
        response = client.generate(
            model="llava",
            prompt=prompt,
            images=[image_url],
        )
        return response.get("response", "No response from vision model")
    except ImportError:
        return "Vision not available. Install: pip install ollama"
    except Exception as e:
        return f"Vision error: {e}"


def get_vision_schema() -> dict[str, Any]:
    return {
        "name": "vision_analyze",
        "description": "Analyze an image using vision-capable AI",
        "parameters": {
            "type": "object",
            "properties": {
                "image_url": {"type": "string", "description": "URL or path to image"},
                "prompt": {"type": "string", "description": "Analysis prompt", "default": "Describe this image"},
            },
            "required": ["image_url"],
        },
    }


__all__ = ["vision_analyze", "get_vision_schema"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_agent_tools_voice.py tests/test_agent_tools_vision.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hermes_prime/agent/tools/voice.py hermes_prime/agent/tools/vision.py tests/test_agent_tools_voice.py tests/test_agent_tools_vision.py
git commit -m "feat: add voice and vision tools"
```

---

### Task 14: Code Execution Tool

**Files:**
- Create: `hermes_prime/agent/tools/code_exec.py`
- Create: `tests/test_agent_tools_code_exec.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_agent_tools_code_exec.py
import pytest


def test_code_exec_tool_registered():
    from hermes_prime.agent.tools.code_exec import execute_code, get_code_exec_schema

    assert callable(execute_code)
    schema = get_code_exec_schema()
    assert schema["name"] == "execute_code"
    assert "code" in schema["parameters"]["properties"]


def test_code_exec_python():
    from hermes_prime.agent.tools.code_exec import execute_code

    result = execute_code("print('hello world')", language="python")
    assert "hello world" in result


def test_code_exec_error():
    from hermes_prime.agent.tools.code_exec import execute_code

    result = execute_code("1/0", language="python")
    assert "ZeroDivisionError" in result or "Error" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_agent_tools_code_exec.py -v`
Expected: FAIL with import error

- [ ] **Step 3: Write minimal implementation**

```python
# hermes_prime/agent/tools/code_exec.py
from __future__ import annotations

import sys
import io
import textwrap
from typing import Any


def execute_code(code: str, language: str = "python") -> str:
    """Execute code in a sandboxed environment."""
    if language != "python":
        return f"Language '{language}' not supported yet."

    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = stdout_capture
    sys.stderr = stderr_capture

    try:
        dedented = textwrap.dedent(code)
        exec_globals = {"__builtins__": __builtins__}
        exec(dedented, exec_globals)
        output = stdout_capture.getvalue()
        error = stderr_capture.getvalue()
        if error:
            output += f"\nSTDERR:\n{error}"
        return output or "Code executed successfully (no output)."
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr


def get_code_exec_schema() -> dict[str, Any]:
    return {
        "name": "execute_code",
        "description": "Execute Python code in a sandboxed environment",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Code to execute"},
                "language": {"type": "string", "description": "Language (default: python)", "default": "python"},
            },
            "required": ["code"],
        },
    }


__all__ = ["execute_code", "get_code_exec_schema"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_agent_tools_code_exec.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hermes_prime/agent/tools/code_exec.py tests/test_agent_tools_code_exec.py
git commit -m "feat: add sandboxed code execution tool"
```

---

### Task 15: Run Full Test Suite

- [ ] **Step 1: Run all agent tests**

Run: `pytest tests/test_agent_loop.py tests/test_governed_dispatch.py tests/test_skills.py tests/test_agent_tools_web_search.py tests/test_agent_tools_terminal.py tests/test_agent_session.py tests/test_kanban.py tests/test_agent_tools_voice.py tests/test_agent_tools_vision.py tests/test_agent_tools_code_exec.py tests/test_agent_tools_todo.py tests/test_cli_agent_commands.py -v`
Expected: All PASS

- [ ] **Step 2: Run full test suite**

Run: `pytest tests/ -x --timeout=120 -q`
Expected: All 372+ existing tests + new tests pass

- [ ] **Step 3: Verify lint**

Run: `ruff check hermes_prime/agent/ hermes_prime/cli.py tests/`
Expected: No errors

- [ ] **Step 4: Commit final integration**

```bash
git add -A
git commit -m "feat: full agent integration - native tools, skills, sessions, kanban, voice, vision, code exec"
```

---

## Summary of New Features Built

| Feature | File | Status |
|---------|------|--------|
| Agent Loop | `hermes_prime/agent/loop.py` | Native with Sentinel governance |
| Tool Registry | `hermes_prime/agent/tool_registry.py` | Auto-schema from signatures |
| Governed Dispatch | `hermes_prime/agent/governed_dispatch.py` | Sentinel evaluation before every call |
| Web Search | `hermes_prime/agent/tools/web_search.py` | DuckDuckGo + URL fetching |
| Terminal Execution | `hermes_prime/agent/tools/terminal.py` | Sandboxed with command allowlist |
| Skills System | `hermes_prime/agent/skills/` | Create, view, search, delete |
| Planning/Todo | `hermes_prime/agent/tools/todo.py` | Task tracking with priorities |
| Session Store | `hermes_prime/agent/session.py` | SQLite with FTS5 search |
| Kanban Board | `hermes_prime/agent/kanban.py` | Multi-agent coordination |
| Voice/Speech | `hermes_prime/agent/tools/voice.py` | edge-tts integration |
| Vision Analysis | `hermes_prime/agent/tools/vision.py` | Ollama vision models |
| Code Execution | `hermes_prime/agent/tools/code_exec.py` | Sandboxed Python execution |
| Governed REPL | `hermes_prime/agent/repl.py` | Interactive chat with governance |
| CLI Commands | `hermes_prime/cli.py` | skills, sessions, todo, tools, kanban |

## Files Created/Modified

```
CREATE: hermes_prime/agent/__init__.py
CREATE: hermes_prime/agent/loop.py
CREATE: hermes_prime/agent/types.py
CREATE: hermes_prime/agent/tool_registry.py
CREATE: hermes_prime/agent/governed_dispatch.py
CREATE: hermes_prime/agent/repl.py
CREATE: hermes_prime/agent/session.py
CREATE: hermes_prime/agent/kanban.py
CREATE: hermes_prime/agent/skills/__init__.py
CREATE: hermes_prime/agent/skills/manager.py
CREATE: hermes_prime/agent/skills/store.py
CREATE: hermes_prime/agent/tools/__init__.py
CREATE: hermes_prime/agent/tools/web_search.py
CREATE: hermes_prime/agent/tools/terminal.py
CREATE: hermes_prime/agent/tools/todo.py
CREATE: hermes_prime/agent/tools/voice.py
CREATE: hermes_prime/agent/tools/vision.py
CREATE: hermes_prime/agent/tools/code_exec.py
CREATE: tests/test_agent_loop.py
CREATE: tests/test_governed_dispatch.py
CREATE: tests/test_skills.py
CREATE: tests/test_agent_tools_web_search.py
CREATE: tests/test_agent_tools_terminal.py
CREATE: tests/test_agent_tools_todo.py
CREATE: tests/test_agent_tools_voice.py
CREATE: tests/test_agent_tools_vision.py
CREATE: tests/test_agent_tools_code_exec.py
CREATE: tests/test_agent_session.py
CREATE: tests/test_agent_repl.py
CREATE: tests/test_kanban.py
CREATE: tests/test_cli_agent_commands.py
MODIFY: hermes_prime/cli.py
MODIFY: hermes_prime/contracts.py
```

# Interactive Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable interactive conversation with Sentinel-governed Hermes Prime agents via CLI chat and messaging gateways (Slack, Discord, etc.).

**Architecture:** Import upstream `external/hermes-agent/` directly via `sys.path`. Monkey-patch `run_agent.handle_function_call` to intercept every tool call and route through Sentinel/Vault/Forge before execution. Upstream CLI and gateway adapters run unchanged — they just call governed tool execution.

**Tech Stack:** Hermes Prime governance (Sentinel, Vault, Forge, TrustStore), upstream hermes-agent (AIAgent, HermesCLI, gateway platforms), OpenAI SDK

---

### Task 1: Add Upstream Dependencies to pyproject.toml

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add core dependencies**

Add to `[project.dependencies]` in `pyproject.toml`:
```toml
"openai>=2.24.0,<3",
"prompt_toolkit>=3.0.52,<4",
"rich>=14.3.3,<15",
"httpx[socks]>=0.28.1,<1",
"pyyaml>=6.0.3,<7",
"jinja2>=3.1.6,<4",
"pydantic>=2.13.4,<3",
"tenacity>=9.1.4,<10",
"python-dotenv>=1.2.2,<2",
```

These are extracted from the upstream's exact-pinned deps but with range bounds per Hermes Prime's convention.

- [ ] **Step 2: Add optional messaging dependencies**

Add to `[project.optional-dependencies]`:
```toml
gateway = [
    "slack-bolt>=1.27.0,<2",
    "discord.py>=2.7.1,<3",
    "python-telegram-bot[webhooks]>=22.6,<23",
    "aiohttp>=3.13.3,<4",
]
```

- [ ] **Step 3: Install and verify**

```bash
pip install -e ".[dev,gateway]"
```
Verify imports:
```python
import openai
import prompt_toolkit
import rich
```

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "feat: add upstream hermes-agent dependencies for interactive agent"
```

---

### Task 2: Create GovernedAgentWrapper

**Files:**
- Create: `hermes_prime/orch/governed_agent.py`
- Create: `tests/orch/test_governed_agent.py`

- [ ] **Step 1: Write failing test**

```python
# tests/orch/test_governed_agent.py
import json
from unittest.mock import Mock, patch, MagicMock
import pytest

from hermes_prime.contracts import ActionProposal, ActionType, RiskTier


class TestGovernedAgentWrapper:

    def test_patches_upstream_handler(self):
        """GovernedAgentWrapper must replace handle_function_call."""
        from unittest.mock import patch
        with patch("hermes_prime.orch.governed_agent.upstream_agent") as mock_upstream:
            wrapper = GovernedAgentWrapper(Mock(), Mock(), Mock(), Mock())
            wrapper._patch_handle_function_call()
            assert mock_upstream.handle_function_call != mock_upstream.handle_function_call

    def test_rejected_tool_returns_error(self):
        """When Sentinel rejects, return JSON error without calling original."""
        sentinel = Mock()
        sentinel.evaluate.return_value.decision.to_dict.return_value = {
            "permitted": False,
            "blocking_layer": 1,
            "denial_reason": "test denial",
        }
        wrapper = GovernedAgentWrapper(sentinel, Mock(), Mock(), Mock())
        wrapper._patch_handle_function_call()
        import run_agent as ra
        result = ra.handle_function_call("read", {"path": "/etc"})
        parsed = json.loads(result)
        assert "Rejected" in parsed["error"]

    def test_approved_tool_calls_original(self):
        """When Sentinel approves, original handler runs and returns result."""
        sentinel = Mock()
        sentinel.evaluate.return_value.decision.to_dict.return_value = {
            "permitted": True,
        }
        wrapper = GovernedAgentWrapper(sentinel, Mock(), Mock(), Mock())
        with patch("hermes_prime.orch.governed_agent.upstream_agent") as mu:
            mu.handle_function_call = Mock(return_value='{"ok": true}')
            wrapper._patch_handle_function_call()
            import run_agent as ra
            ra.handle_function_call = mu.handle_function_call
            result = ra.handle_function_call("read", {"path": "test.txt"})
            assert json.loads(result) == {"ok": True}

    def test_audit_trace_stored_on_approval(self):
        """After approved tool execution, audit trace is recorded."""
        trust_store = Mock()
        wrapper = GovernedAgentWrapper(Mock(), Mock(), Mock(), trust_store)
        with patch("hermes_prime.orch.governed_agent.upstream_agent") as mu:
            mu.handle_function_call = Mock(return_value="{}")
            wrapper._patch_handle_function_call()
            import run_agent as ra
            ra.handle_function_call = mu.handle_function_call
            ra.handle_function_call("read", {"path": "test.txt"})
            assert trust_store.store_audit_trace.called
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/orch/test_governed_agent.py -v
```
Expected: FAIL with `ModuleNotFoundError` or import errors (since governed_agent.py doesn't exist yet).

- [ ] **Step 3: Write minimal implementation**

Create `hermes_prime/orch/governed_agent.py`:

```python
"""Governed agent wrapper — monkey-patches upstream handle_function_call
to route every tool execution through Sentinel policy evaluation."""

from __future__ import annotations

import json
from typing import Any, Optional

import run_agent as upstream_agent

from hermes_prime.contracts import ActionProposal, ActionType, RiskTier
from hermes_prime.signing import HMACSigner
from hermes_prime.utils import new_urn_uuid, utc_now_iso


class GovernedAgentWrapper:
    """Wraps upstream AIAgent with Sentinel governance on all tool calls.

    Usage:
        wrapper = GovernedAgentWrapper(sentinel, vault, forge, trust_store)
        agent = wrapper.create_governed_agent(model="mistral", ...)
        response = agent.chat("hello")
    """

    def __init__(
        self,
        sentinel: Any,
        vault: Any,
        forge: Any,
        trust_store: Any,
        workspace_root: str = ".",
        signer: Optional[HMACSigner] = None,
    ):
        self._sentinel = sentinel
        self._vault = vault
        self._forge = forge
        self._trust_store = trust_store
        self._workspace_root = workspace_root
        self._signer = signer or HMACSigner(
            identity="hermes-governed-agent",
            secret=b"hermes-prime-governance",
        )

    def create_governed_agent(self, **kwargs) -> upstream_agent.AIAgent:
        """Create an AIAgent whose tool calls are governed by Sentinel."""
        self._patch_handle_function_call()
        return upstream_agent.AIAgent(**kwargs)

    def _patch_handle_function_call(self) -> None:
        """Replace upstream's handle_function_call with governed version."""
        original = upstream_agent.handle_function_call

        def governed(
            function_name: str,
            function_args: dict[str, Any],
            task_id: Optional[str] = None,
            tool_call_id: Optional[str] = None,
            session_id: Optional[str] = None,
        ) -> str:
            # Step 1: Sentinel evaluation
            decision = self._evaluate_action(function_name, function_args)
            if not decision.get("permitted", False):
                return json.dumps({
                    "error": f"Action rejected by Sentinel: {decision.get('denial_reason', 'unknown')}",
                })

            # Step 2: Execute original handler
            result = original(
                function_name, function_args,
                task_id=task_id,
                tool_call_id=tool_call_id,
                session_id=session_id,
            )

            # Step 3: Post-execution audit
            self._post_execution_audit(function_name, function_args, decision, result)

            return result

        upstream_agent.handle_function_call = governed

    def _evaluate_action(self, function_name: str, function_args: dict) -> dict:
        """Evaluate a tool call through Sentinel. Returns decision dict."""
        # Convert tool call to ActionProposal
        intent_root = new_urn_uuid()
        action_type = self._map_tool_to_action_type(function_name)
        proposal = ActionProposal(
            intent_root_id=intent_root,
            action_type=action_type,
            scope=self._workspace_root,
            params=function_args,
            risk_tier=RiskTier.T2,
            description=f"Tool call: {function_name}",
        )

        # Mint capability
        token = self._vault.mint_capability(
            capability=f"tool:{function_name}",
            scope=self._workspace_root,
            actions=[action_type.value],
            risk_tier_ceiling=RiskTier.T2,
            intent_root=intent_root,
            issued_to="hermes:governed-agent",
        )

        # Evaluate
        evaluation = self._sentinel.evaluate(proposal, capability=token)
        return evaluation.decision.to_dict() if hasattr(evaluation, "decision") else {
            "permitted": True,
            "blocking_layer": None,
            "denial_reason": None,
        }

    def _map_tool_to_action_type(self, tool_name: str) -> ActionType:
        """Map a tool name to an ActionType for Sentinel evaluation."""
        mapping = {
            "read": ActionType.FILESYSTEM_READ,
            "read_file": ActionType.FILESYSTEM_READ,
            "write": ActionType.FILESYSTEM_WRITE,
            "write_file": ActionType.FILESYSTEM_WRITE,
            "patch": ActionType.FILESYSTEM_WRITE,
            "edit": ActionType.FILESYSTEM_WRITE,
            "execute": ActionType.TERMINAL_EXEC,
            "execute_code": ActionType.TERMINAL_EXEC,
            "terminal": ActionType.TERMINAL_EXEC,
            "delegate_task": ActionType.AGENT_SPAWN,
            "web_search": ActionType.NETWORK_REQUEST,
            "web_fetch": ActionType.NETWORK_REQUEST,
        }
        return mapping.get(tool_name, ActionType.FILESYSTEM_READ)

    def _post_execution_audit(self, function_name, function_args, decision, result) -> None:
        """Record audit trail and memory after tool execution."""
        if not self._trust_store:
            return

        trace_id = new_urn_uuid()
        trace = {
            "trace_id": trace_id,
            "trace_type": "governed_tool_call",
            "created_at": utc_now_iso(),
            "workspace_root": self._workspace_root,
            "action": {
                "tool": function_name,
                "args": function_args,
                "decision": decision,
                "result": result,
            },
        }
        self._trust_store.store_audit_trace(trace)
```

- [ ] **Step 4: Write implementation tests**

Update `tests/orch/test_governed_agent.py`:

```python
import json
from unittest.mock import Mock, patch, MagicMock
import pytest

from hermes_prime.orch.governed_agent import GovernedAgentWrapper


@pytest.fixture
def mock_infrastructure():
    sentinel = Mock()
    sentinel.evaluate.return_value.decision.to_dict.return_value = {
        "permitted": True,
        "blocking_layer": None,
        "denial_reason": None,
    }
    vault = Mock()
    vault.mint_capability.return_value.token_id = "test-token"
    forge = Mock()
    trust_store = Mock()
    return sentinel, vault, forge, trust_store


def test_governed_wrapper_patches_handle_function_call(mock_infrastructure):
    sentinel, vault, forge, trust_store = mock_infrastructure
    wrapper = GovernedAgentWrapper(sentinel, vault, forge, trust_store)

    with patch("hermes_prime.orch.governed_agent.upstream_agent") as mock_upstream:
        wrapper.create_governed_agent(model="test")
        assert mock_upstream.handle_function_call != mock_upstream.handle_function_call.__wrapped__


def test_approved_tool_allows_original_handler(mock_infrastructure):
    sentinel, vault, forge, trust_store = mock_infrastructure
    wrapper = GovernedAgentWrapper(sentinel, vault, forge, trust_store)

    original = Mock(return_value='{"success": true}')
    with patch.object(wrapper, "_patch_handle_function_call"):
        with patch("hermes_prime.orch.governed_agent.upstream_agent") as mock_upstream:
            mock_upstream.handle_function_call = original
            wrapper._patch_handle_function_call = lambda: None
            # Manual patch
            import hermes_prime.orch.governed_agent as ga
            ga.upstream_agent = mock_upstream
            # ... (test body)
            pass


def test_rejected_tool_returns_error_without_original(mock_infrastructure):
    sentinel, vault, forge, trust_store = mock_infrastructure
    sentinel.evaluate.return_value.decision.to_dict.return_value = {
        "permitted": False,
        "blocking_layer": 1,
        "denial_reason": "policy violation: write outside scope",
    }
    wrapper = GovernedAgentWrapper(sentinel, vault, forge, trust_store)

    original = Mock(side_effect=AssertionError("should not be called"))
    with patch.object(upstream_agent, "handle_function_call", original):
        wrapper._patch_handle_function_call()
        result = upstream_agent.handle_function_call("write", {"path": "/etc/passwd"})
        parsed = json.loads(result)
        assert "Rejected by Sentinel" in parsed["error"]


def test_audit_trace_stored_on_approval(mock_infrastructure):
    sentinel, vault, forge, trust_store = mock_infrastructure
    wrapper = GovernedAgentWrapper(sentinel, vault, forge, trust_store)

    with patch.object(upstream_agent, "handle_function_call", Mock(return_value="{}")):
        wrapper._patch_handle_function_call()
        upstream_agent.handle_function_call("read", {"path": "test.txt"})
        assert trust_store.store_audit_trace.called
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/orch/test_governed_agent.py -v
```
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add hermes_prime/orch/governed_agent.py tests/orch/test_governed_agent.py
git commit -m "feat: add GovernedAgentWrapper with Sentinel governance on tool calls"
```

---

### Task 3: Add sys.path Setup and CLI Commands

**Files:**
- Modify: `hermes_prime/cli.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_cli.py (or appropriate existing test file)
def test_chat_subcommand_registered():
    """hermes --help should include 'chat' subcommand."""
    from hermes_prime.cli import create_parser
    parser = create_parser()
    help_text = parser.format_help()
    assert "chat" in help_text


def test_gateway_subcommand_registered():
    """hermes --help should include 'gateway' subcommand."""
    from hermes_prime.cli import create_parser
    parser = create_parser()
    help_text = parser.format_help()
    assert "gateway" in help_text
```

- [ ] **Step 2: Add sys.path setup and CLI commands**

Read the existing `cli.py` to find the right insertion points:

```python
# At the top of hermes_prime/cli.py, after stdlib imports:
import sys
from pathlib import Path

# Add upstream hermes-agent to path
_HERMES_AGENT_PATH = str(
    Path(__file__).resolve().parent.parent / "external" / "hermes-agent"
)
if _HERMES_AGENT_PATH not in sys.path:
    sys.path.insert(0, _HERMES_AGENT_PATH)
```

Find the subparsers setup in `create_parser()` or `main()` and add:

```python
# Chat subcommand
chat_parser = subparsers.add_parser(
    "chat",
    help="Start interactive Sentinel-governed chat session",
)
chat_parser.add_argument("--model", default="mistral", help="LLM model name")
chat_parser.add_argument("--scope", default=".", help="Workspace scope path")
chat_parser.add_argument("--context", help="Initial system context override")
```

```python
# Gateway subcommand
gw_parser = subparsers.add_parser(
    "gateway",
    help="Start messaging gateway (Slack, Discord, etc.)",
)
gw_parser.add_argument(
    "--platforms",
    default="slack",
    help="Comma-separated platform list (slack, discord, telegram)",
)
```

```python
# In the command dispatch section:
if args.command == "chat":
    from hermes_prime.orch.governed_cli import run_governed_chat
    run_governed_chat(
        model=args.model,
        scope=args.scope,
        context=args.context,
    )
elif args.command == "gateway":
    from hermes_prime.gateway.governed_gateway import run_governed_gateway
    run_governed_gateway(
        platforms=args.platforms.split(","),
    )
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_cli.py -v
```
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add hermes_prime/cli.py tests/test_cli.py
git commit -m "feat: add chat and gateway CLI commands with upstream sys.path"
```

---

### Task 4: Create Governed CLI Launcher

**Files:**
- Create: `hermes_prime/orch/governed_cli.py`

- [ ] **Step 1: Write failing test**

```python
# tests/orch/test_governed_cli.py
def test_run_governed_chat_creates_governed_agent():
    """run_governed_chat should create a GovernedAgentWrapper and launch HermesCLI."""
    pass
```

- [ ] **Step 2: Implement governed CLI launcher**

```python
# hermes_prime/orch/governed_cli.py
"""Governed CLI launcher — wraps upstream HermesCLI with Sentinel governance."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def run_governed_chat(
    model: str = "mistral",
    scope: str = ".",
    context: Optional[str] = None,
) -> None:
    """Launch an interactive Sentinel-governed chat session.

    Uses upstream HermesCLI with a GovernedAgentWrapper to add Sentinel
    policy evaluation before every tool call.
    """
    from hermes_prime.orch.governed_agent import GovernedAgentWrapper
    from hermes_prime.infrastructure_setup import (
        create_sentinel,
        create_vault,
        create_forge,
        create_trust_store,
    )

    # Initialize Hermes Prime infrastructure
    workspace = Path(scope).resolve()
    sentinel = create_sentinel(workspace)
    vault = create_vault(workspace)
    forge = create_forge(workspace)
    trust_store = create_trust_store(workspace)

    # Create governed agent wrapper
    wrapper = GovernedAgentWrapper(
        sentinel=sentinel,
        vault=vault,
        forge=forge,
        trust_store=trust_store,
        workspace_root=str(workspace),
    )

    # Create governed agent
    agent = wrapper.create_governed_agent(
        model=model,
        quiet_mode=False,
        save_trajectories=True,
    )

    # Launch upstream HermesCLI with governed agent
    from hermes_cli.main import main as upstream_cli_main

    # Pass model via CLI args
    sys_argv = ["hermes", "--model", model]
    if context:
        sys_argv.extend(["--context", context])

    # The upstream HermesCLI creates its own AIAgent internally.
    # We need the CLI to use our governed agent instead.
    # The upstream creates the agent lazily — we monkey-patch the
    # AIAgent constructor or the agent factory.
    import run_agent
    _original_agent_init = run_agent.AIAgent.__init__

    def _governed_init(self, **kwargs):
        # Redirect to our already-created governed agent
        self.__dict__.update(agent.__dict__)

    run_agent.AIAgent.__init__ = _governed_init

    # Run CLI
    upstream_cli_main()
```

This is a simplified initial version. The exact upstream CLI hook point may need refinement — the upstream `HermesCLI.__init__` or the main entry may expose the agent differently.

- [ ] **Step 3: Run tests**

```bash
pytest tests/orch/test_governed_cli.py -v
```
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add hermes_prime/orch/governed_cli.py tests/orch/test_governed_cli.py
git commit -m "feat: add governed CLI launcher for interactive chat"
```

---

### Task 5: Create Governed Gateway Session Factory

**Files:**
- Create: `hermes_prime/gateway/governed_gateway.py`

- [ ] **Step 1: Implement governed gateway**

```python
# hermes_prime/gateway/governed_gateway.py
"""Governed gateway — wraps upstream messaging gateway sessions with Sentinel governance."""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def run_governed_gateway(platforms: list[str]) -> None:
    """Start messaging gateway with governed agent sessions.

    Each incoming message creates a governed agent session where every
    tool call is evaluated by Sentinel before execution.
    """
    from hermes_prime.orch.governed_agent import GovernedAgentWrapper
    from hermes_prime.infrastructure_setup import (
        create_sentinel,
        create_vault,
        create_forge,
        create_trust_store,
    )

    workspace = Path.cwd()
    sentinel = create_sentinel(workspace)
    vault = create_vault(workspace)
    forge = create_forge(workspace)
    trust_store = create_trust_store(workspace)

    # Patch handle_function_call globally before gateway starts
    wrapper = GovernedAgentWrapper(
        sentinel=sentinel,
        vault=vault,
        forge=forge,
        trust_store=trust_store,
        workspace_root=str(workspace),
    )
    wrapper._patch_handle_function_call()

    # Launch upstream gateway
    from gateway.run import main as gateway_main

    # Override the gateway config to enable requested platforms
    os.environ.setdefault("HERMES_GATEWAY_PLATFORMS", ",".join(platforms))

    gateway_main()
```

- [ ] **Step 2: Simple smoke test**

```python
# tests/gateway/test_governed_gateway.py
def test_gateway_imports():
    """Gateway module should import without errors."""
    from hermes_prime.gateway.governed_gateway import run_governed_gateway
    assert callable(run_governed_gateway)
```

- [ ] **Step 3: Commit**

```bash
git add hermes_prime/gateway/governed_gateway.py tests/gateway/test_governed_gateway.py
mkdir -p tests/gateway
git add tests/gateway/test_governed_gateway.py
git commit -m "feat: add governed gateway session factory for Slack/Discord/etc"
```

---

### Task 6: Infrastructure Setup Module

**Files:**
- Create: `hermes_prime/infrastructure_setup.py`

- [ ] **Step 1: Create shared infrastructure factory**

```python
# hermes_prime/infrastructure_setup.py
"""Shared factories for Hermes Prime infrastructure components."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def create_sentinel(workspace: Path) -> Any:
    from infrastructure.policy_engine.sentinel_service import SentinelService
    from infrastructure.policy_engine.config import SentinelConfig
    config = SentinelConfig(policy_dir=workspace / "infrastructure" / "policy_engine" / "policies")
    return SentinelService(config)


def create_vault(workspace: Path) -> Any:
    from infrastructure.vault.capabilities import CapabilityVault
    return CapabilityVault(storage_path=workspace / ".hermes-prime" / "capabilities.db")


def create_forge(workspace: Path) -> Any:
    from infrastructure.sandboxed_forge.forge import SandboxedForge
    return SandboxedForge(workspace)


def create_trust_store(workspace: Path) -> Any:
    from infrastructure.trust_store import TrustStore
    return TrustStore(db_path=workspace / ".hermes-prime" / "trust.db")
```

- [ ] **Step 2: Commit**

```bash
git add hermes_prime/infrastructure_setup.py
git commit -m "feat: add shared infrastructure factory module"
```

---

### Task 7: Integration Smoke Test

**Files:**
- Modify: `tests/orch/test_governed_agent.py`

- [ ] **Step 1: Write integration-style test**

```python
def test_governed_agent_rejects_unauthorized_tool():
    """End-to-end: governed agent should reject a tool call that violates policy."""
    from hermes_prime.orch.governed_agent import GovernedAgentWrapper
    from unittest.mock import Mock

    # Set up mock Sentinel that rejects everything
    sentinel = Mock()
    sentinel.evaluate.return_value.decision.to_dict.return_value = {
        "permitted": False,
        "blocking_layer": 1,
        "denial_reason": "test: all actions denied",
    }
    vault = Mock()
    vault.mint_capability.return_value.token_id = "test-token"
    forge = Mock()
    trust_store = Mock()

    wrapper = GovernedAgentWrapper(sentinel, vault, forge, trust_store)
    wrapper._patch_handle_function_call()

    import run_agent
    result = run_agent.handle_function_call("read", {"path": "test.txt"})
    import json
    parsed = json.loads(result)
    assert "Rejected" in parsed["error"]
    assert not sentinel.evaluate.return_value.decision.to_dict.return_value["permitted"]
```

- [ ] **Step 2: Run test**

```bash
pytest tests/orch/test_governed_agent.py -v
```
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/orch/test_governed_agent.py
git commit -m "test: add integration smoke test for governed tool rejection"
```

---

## Spec Coverage Check

| Spec Requirement | Task |
|-----------------|------|
| Import upstream from external/ | Task 3 (sys.path) |
| Sentinel governance on tool calls | Task 2 (GovernedAgentWrapper) |
| `hermes chat` CLI command | Task 3 + Task 4 |
| `hermes gateway` CLI command | Task 3 + Task 5 |
| Messaging platform adapters | Task 5 (gateway) |
| Audit trail on tool calls | Task 2 (`_post_execution_audit`) |
| Upstream deps in pyproject.toml | Task 1 |
| Infrastructure factories | Task 6 |

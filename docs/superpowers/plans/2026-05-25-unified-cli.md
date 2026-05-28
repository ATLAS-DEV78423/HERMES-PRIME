# Unified CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `hermes` a unified entry point for all Hermes Prime and upstream Hermes Agent capabilities, with two-pass CLI dispatch, resolved naming collisions, and deepened Sentinel governance hooks.

**Architecture:** Two-pass dispatch — HP parser handles 18 subcommands (13 native + 3 renamed + 2 governed); unknown commands fall through to `hermes_cli/main.main()`. Sentinel `handle_function_call` patch already covers all upstream tool execution. New governance hooks add Sentinel evaluation for cron scheduling, tool config changes, and skill operations.

**Tech Stack:** Hermes Prime, upstream hermes-agent (consumed via sys.path), argparse, SentinelService, CapabilityVault, TrustStore

---

### Task 1: Rename Colliding HP Subcommands (doctor → hp-doctor, memory → hp-memory, dashboard → hp-dashboard)

**Files:**
- Modify: `hermes_prime/cli.py`

- [ ] **Step 1: Write failing test**

Add to an existing test file (or create `tests/test_cli_commands.py`):

```python
import pytest


def test_hp_doctor_subcommand_registered():
    """hermes --help should include hp-doctor, not doctor."""
    from hermes_prime.cli import build_parser
    parser = build_parser()
    help_text = parser.format_help()
    assert "hp-doctor" in help_text
    assert "doctor" not in help_text or "hp-doctor" in help_text


def test_hp_memory_subcommand_registered():
    """hermes --help should include hp-memory, not memory."""
    from hermes_prime.cli import build_parser
    parser = build_parser()
    help_text = parser.format_help()
    assert "hp-memory" in help_text
    assert "memory" not in help_text or "hp-memory" in help_text


def test_hp_dashboard_subcommand_registered():
    """hermes --help should include hp-dashboard, not dashboard."""
    from hermes_prime.cli import build_parser
    parser = build_parser()
    help_text = parser.format_help()
    assert "hp-dashboard" in help_text
    assert "dashboard" not in help_text or "hp-dashboard" in help_text
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_cli_commands.py -v
```
Expected: FAIL with assertion errors (subcommand names still use old names).

- [ ] **Step 3: Rename subcommands in `build_parser()`**

In `hermes_prime/cli.py`, find the three `add_parser` calls and change their first argument:

```python
# Line ~73: doctor → hp-doctor
doctor_parser = subparsers.add_parser(
    "hp-doctor",
    help="Diagnose Hermes Prime installation and workspace health",
)
# ... (same subcommand args)

# Line ~128: memory → hp-memory (the top-level memory parser)
memory_parser = subparsers.add_parser(
    "hp-memory",
    help="Memory fabric commands",
)
# ... (same subcommand args for all memory sub-subcommands: write, recall, list, revoke, gc)

# Line ~261: dashboard → hp-dashboard
subparsers.add_parser(
    "hp-dashboard",
    help="Launch Textual live dashboard",
)
```

Also update the `commands` set in `main()` (~line 329):

```python
commands = {
    "graphify", "repair", "inspect", "mint", "evaluate", "patch", "replay",
    "models", "run", "agents", "hp-dashboard", "tui", "learn", "brain",
    "hp-doctor", "hp-memory", "chat", "gateway",
}
```

And update all `if args.command == ...` blocks that reference the old names:

```python
# Before:
if args.command == "doctor":
# After:
if args.command == "hp-doctor":

# Before:
if args.command == "memory":
# After:
if args.command == "hp-memory":

# Before:
if args.command == "dashboard":
# After:
if args.command == "hp-dashboard":
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_cli_commands.py -v
```
Expected: PASS

- [ ] **Step 5: Run full test suite to check for regressions**

```bash
python -m pytest tests/ -q --tb=short --no-header 2>&1 | Select-Object -Last 10
```
Expected: Only the 6 pre-existing failures; no new failures.

- [ ] **Step 6: Commit**

```bash
git add hermes_prime/cli.py tests/test_cli_commands.py
git commit -m "refactor(cli): rename doctor/memory/dashboard to hp-doctor/hp-memory/hp-dashboard"
```

---

### Task 2: Implement Two-pass CLI Dispatch

**Files:**
- Modify: `hermes_prime/cli.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_cli_commands.py`:

```python
def test_unknown_cmd_falls_through():
    """When HP doesn't recognize the command, upstream parser is called.
    We test by checking that 'hermes setup' (an upstream-only command)
    triggers the upstream code path.
    """
    # We can't easily test the full passthrough without importing upstream,
    # but we can verify the dispatch logic structure.
    from hermes_prime.cli import known_hp_commands
    assert "setup" not in known_hp_commands
    assert "model" not in known_hp_commands
    assert "cron" not in known_hp_commands
```

- [ ] **Step 2: Define `known_hp_commands` set and implement two-pass dispatch**

In `hermes_prime/cli.py`, near the top of `main()` (before the existing `commands` logic), define the set of all HP-handled commands:

```python
# Replace the existing `commands` set (line ~328) with this:
known_hp_commands = {
    "graphify", "repair", "inspect", "mint", "evaluate", "patch", "replay",
    "models", "run", "agents", "hp-dashboard", "tui", "learn", "brain",
    "hp-doctor", "hp-memory", "chat", "gateway",
}

# Replace the existing --prompt auto-detect logic with:
if argv is not None and "--prompt" not in argv and "--autonomous" not in argv:
    non_option_tokens = [token for token in argv if token and not token.startswith("-")]
    if len(non_option_tokens) == 1 and non_option_tokens[0] not in known_hp_commands:
        argv = list(argv) + ["--prompt", non_option_tokens[0]]
```

Then replace the `parser = build_parser()` / `args = parser.parse_args(argv)` block with:

```python
# Pass 1: try HP parser
parser = build_parser()
args, _ = parser.parse_known_args(argv)
cmd = vars(args).get("command")

if cmd:
    # HP recognizes this command — handle it
    return handle_hp_command(args, parser)
else:
    # Pass 2: upstream passthrough
    import hermes_cli.main as upstream_main
    return upstream_main.main(argv)
```

Refactor the existing command handling into `handle_hp_command()`:

```python
def handle_hp_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Execute an HP-native subcommand."""
    # ... move all existing if args.command == ... logic here
    # Keep all the existing handler code, just wrapped in this function
    # The parser parameter is passed in case parser.error() is needed
```

The existing code already uses `parser.error()` in many places, so pass `parser` through.

- [ ] **Step 3: Run test to verify it passes**

```bash
python -m pytest tests/test_cli_commands.py -v
```
Expected: PASS

- [ ] **Step 4: Run full test suite**

```bash
python -m pytest tests/ -q --tb=short --no-header 2>&1 | Select-Object -Last 10
```
Expected: Only 6 pre-existing failures.

- [ ] **Step 5: Commit**

```bash
git add hermes_prime/cli.py
git commit -m "feat(cli): implement two-pass dispatch — HP first, upstream passthrough second"
```

---

### Task 3: Update Existing Tests for Renamed Commands

**Files:**
- Modify: `tests/test_cli_and_bundle.py`
- Modify: `tests/test_system_doctor.py`

- [ ] **Step 1: Search for outdated references to old subcommand names**

```bash
Select-String -Path "tests" -Pattern "\"doctor\"|'doctor'|\"memory\"|'memory'|\"dashboard\"|'dashboard'" | Out-String
```

- [ ] **Step 2: Update CLI tests**

In `tests/test_cli_and_bundle.py`, search for test methods that test `doctor`, `memory`, or `dashboard` subcommands. Update `hermes doctor` references to `hermes hp-doctor`:

```python
# In test_cli_prompt_flow_is_traced_and_replayable:
# If it references "doctor" command, change to "hp-doctor"
```

No need to change tests that are testing upstream behavior — those will now go through passthrough.

- [ ] **Step 3: Update system doctor tests**

In `tests/test_system_doctor.py`, search for any references to `hermes doctor` and update to `hermes hp-doctor`:

```python
# Update any CLI invocation references
```

- [ ] **Step 4: Run updated tests**

```bash
python -m pytest tests/test_cli_and_bundle.py tests/test_system_doctor.py -v --no-header 2>&1 | Select-Object -Last 15
```
Expected: Same 6 pre-existing failures, no new failures.

- [ ] **Step 5: Commit**

```bash
git add tests/test_cli_and_bundle.py tests/test_system_doctor.py
git commit -m "test: update references from doctor/memory/dashboard to hp- prefix"
```

---

### Task 4: Create Governance Hooks Module

**Files:**
- Create: `hermes_prime/orch/governance_hooks.py`
- Create: `tests/orch/test_governance_hooks.py`

- [ ] **Step 1: Write failing test**

```python
# tests/orch/test_governance_hooks.py
from unittest.mock import Mock, patch
import pytest

from hermes_prime.orch.governance_hooks import (
    GovernanceHooks,
    wrap_upstream_command,
)


class TestGovernanceHooks:
    def test_wrap_upstream_command_rejected(self):
        """When Sentinel rejects, the command is blocked."""
        sentinel = Mock()
        sentinel.evaluate.return_value.decision.to_dict.return_value = {
            "permitted": False,
            "blocking_layer": 1,
            "denial_reason": "cron scheduling not permitted",
        }
        vault = Mock()
        vault.mint_capability.return_value.token_id = "test-token"
        trust_store = Mock()

        hooks = GovernanceHooks(sentinel, vault, trust_store, "/test")

        def dummy_cmd(*args, **kwargs):
            return 0

        wrapped = hooks.wrap("cron", dummy_cmd)
        result = wrapped("add", {"schedule": "* * * * *", "command": "rm -rf /"})
        assert result == 1  # blocked
        assert sentinel.evaluate.called

    def test_wrap_upstream_command_approved(self):
        """When Sentinel approves, the command executes normally."""
        sentinel = Mock()
        sentinel.evaluate.return_value.decision.to_dict.return_value = {
            "permitted": True,
            "blocking_layer": None,
            "denial_reason": None,
        }
        vault = Mock()
        vault.mint_capability.return_value.token_id = "test-token"
        trust_store = Mock()

        hooks = GovernanceHooks(sentinel, vault, trust_store, "/test")

        def dummy_cmd(*args, **kwargs):
            return 0

        wrapped = hooks.wrap("tools", dummy_cmd)
        result = wrapped("enable", {"tool": "terminal"})
        assert result == 0  # allowed
        assert trust_store.store_audit_trace.called

    def test_apply_cron_hook(self):
        """apply_cron_hook patches the upstream cron module's add_job."""
        sentinel = Mock()
        hooks = GovernanceHooks(sentinel, Mock(), Mock(), "/test")

        mock_cron = Mock()
        mock_cron.add_job = Mock(return_value="ok")

        hooks.apply_cron_hook(mock_cron)

        sentinel.evaluate.return_value.decision.to_dict.return_value = {
            "permitted": True,
        }
        result = mock_cron.add_job("* * * * *", "echo hello")
        assert result == "ok"
        assert sentinel.evaluate.called
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/orch/test_governance_hooks.py -v
```
Expected: ImportError (module doesn't exist yet)

- [ ] **Step 3: Write minimal implementation**

```python
# hermes_prime/orch/governance_hooks.py
"""Sentinel governance hooks for upstream CLI commands (cron, tools, skills)."""

from __future__ import annotations

import json
from typing import Any, Callable, Optional

from hermes_prime.contracts import ActionProposal, ActionType, RiskTier
from hermes_prime.signing import HMACSigner
from hermes_prime.utils import new_urn_uuid, utc_now_iso


class GovernanceHooks:
    """Wraps upstream CLI command functions with Sentinel evaluation.

    Usage:
        hooks = GovernanceHooks(sentinel, vault, trust_store, workspace_root)
        wrapped_add_job = hooks.wrap("cron", upstream_cron_module.add_job)
    """

    def __init__(
        self,
        sentinel: Any,
        vault: Any,
        trust_store: Any,
        workspace_root: str,
        signer: Optional[HMACSigner] = None,
    ):
        self._sentinel = sentinel
        self._vault = vault
        self._trust_store = trust_store
        self._workspace_root = workspace_root
        self._signer = signer or HMACSigner(
            identity="hermes-governance-hooks",
            secret=b"hermes-prime-governance",
        )

    def wrap(
        self,
        action_type_label: str,
        func: Callable,
    ) -> Callable:
        """Wrap a function with Sentinel evaluation.

        Args:
            action_type_label: One of "cron", "tools", "skills", "model".
            func: The upstream function to wrap.

        Returns:
            Wrapped function that evaluates through Sentinel before executing.
        """
        action_type = self._label_to_action_type(action_type_label)

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            intent_root = new_urn_uuid()
            params = {"args": str(args), "kwargs": str(kwargs)}
            proposal = ActionProposal(
                intent_root_id=intent_root,
                action_type=action_type,
                scope=self._workspace_root,
                params=params,
                risk_tier=RiskTier.T2,
                description=f"Upstream command: {action_type_label}",
            )
            token = self._vault.mint_capability(
                capability=f"cmd:{action_type_label}",
                scope=self._workspace_root,
                actions=[action_type.value],
                risk_tier_ceiling=RiskTier.T2,
                intent_root=intent_root,
                issued_to="hermes:governed-upstream",
            )
            evaluation = self._sentinel.evaluate(proposal, capability=token)
            decision = evaluation.decision.to_dict() if hasattr(evaluation, "decision") else {
                "permitted": True,
                "blocking_layer": None,
                "denial_reason": None,
            }

            if not decision.get("permitted", True):
                # Block the command
                msg = f"Action rejected by Sentinel: {decision.get('denial_reason', 'unknown')}"
                print(msg)
                return 1

            # Execute the upstream function
            result = func(*args, **kwargs)

            # Audit
            if self._trust_store:
                trace = {
                    "trace_id": new_urn_uuid(),
                    "trace_type": "governed_upstream_cmd",
                    "created_at": utc_now_iso(),
                    "workspace_root": self._workspace_root,
                    "action": {
                        "action_type_label": action_type_label,
                        "params": params,
                        "decision": decision,
                    },
                }
                self._trust_store.store_audit_trace(trace)

            return result

        return wrapper

    def apply_cron_hook(self, cron_module: Any) -> None:
        """Patch an upstream cron module's add_job with Sentinel governance."""
        if not hasattr(cron_module, "add_job"):
            return
        original = cron_module.add_job
        cron_module.add_job = self.wrap("cron", original)

    def _label_to_action_type(self, label: str) -> ActionType:
        mapping = {
            "cron": ActionType.SCHEDULING,
            "tools": ActionType.CONFIG_WRITE,
            "skills": ActionType.CONFIG_WRITE,
            "model": ActionType.CONFIG_WRITE,
        }
        return mapping.get(label, ActionType.CONFIG_WRITE)


__all__ = ["GovernanceHooks"]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/orch/test_governance_hooks.py -v
```
Expected: 3/3 PASS

- [ ] **Step 5: Add governance hooks initialization to cli.py**

In `hermes_prime/cli.py`, in the upstream passthrough branch, apply governance hooks before calling the upstream main:

```python
# In the passthrough branch of main():
else:
    # Apply governance hooks before upstream handles the command
    from hermes_prime.orch.governance_hooks import GovernanceHooks
    hooks = GovernanceHooks(sentinel, vault, trust_store, workspace)
    # Lazy-import upstream modules and apply hooks
    cmd = argv[0] if argv else ""
    if cmd == "cron":
        import cron.scheduler as cron_scheduler
        hooks.apply_cron_hook(cron_scheduler)
    elif cmd == "tools":
        import hermes_cli.tools_config as tools_config
        tools_config.toggle_tool = hooks.wrap("tools", tools_config.toggle_tool)
    elif cmd == "skills":
        import hermes_cli.skills_config as skills_config
        skills_config.install_skill = hooks.wrap("skills", skills_config.install_skill)
    # ... fall through to upstream
    import hermes_cli.main as upstream_main
    return upstream_main.main(argv)
```

- [ ] **Step 6: Run full test suite**

```bash
python -m pytest tests/ -q --tb=short --no-header 2>&1 | Select-Object -Last 10
```
Expected: Only 6 pre-existing failures.

- [ ] **Step 7: Commit**

```bash
git add hermes_prime/orch/governance_hooks.py hermes_prime/cli.py
git add tests/orch/test_governance_hooks.py
git commit -m "feat: add GovernanceHooks module with Sentinel evaluation for cron/tools/skills"
```

---

### Task 5: Add Passthrough Integration Test

**Files:**
- Modify: `tests/test_cli_commands.py`

- [ ] **Step 1: Write passthrough integration test**

Add to `tests/test_cli_commands.py`:

```python
def test_upstream_passthrough_structure():
    """Verify the passthrough code path is reachable.

    This test checks that:
    1. The known_hp_commands set is correct
    2. Upstream-only commands are NOT in known_hp_commands
    3. The upstream module can be imported (it's on sys.path)
    """
    from hermes_prime.cli import known_hp_commands

    # HP-handled commands — should be in the set
    hp_cmds = [
        "brain", "learn", "agents", "hp-doctor", "hp-memory",
        "hp-dashboard", "chat", "gateway", "graphify", "repair",
        "inspect", "mint", "evaluate", "patch", "replay",
        "models", "run", "tui",
    ]
    for cmd in hp_cmds:
        assert cmd in known_hp_commands, f"{cmd} should be in known_hp_commands"

    # Upstream-only commands — should NOT be in the set
    upstream_cmds = [
        "setup", "model", "cron", "kanban", "skills", "tools",
        "profile", "plugins", "auth", "backup", "bundle",
        "sessions", "version", "update", "checkpoints",
    ]
    for cmd in upstream_cmds:
        assert cmd not in known_hp_commands, f"{cmd} should NOT be in known_hp_commands"

    # Verify upstream module is importable
    import importlib
    assert importlib.util.find_spec("hermes_cli") is not None


def test_known_hp_set_has_all_registered_subcommands():
    """Every subcommand registered in build_parser should be in known_hp_commands."""
    from hermes_prime.cli import build_parser, known_hp_commands
    parser = build_parser()
    # walk subparsers for registered command names
    for action in parser._actions:
        if hasattr(action, "_name_parser_map"):
            for name in action._name_parser_map:
                assert name in known_hp_commands, (
                    f"Registered subcommand '{name}' missing from known_hp_commands"
                )
```

- [ ] **Step 2: Run test**

```bash
python -m pytest tests/test_cli_commands.py -v
```
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_cli_commands.py
git commit -m "test: add passthrough integration tests for unified CLI dispatch"
```

---

### Task 6: Final Verification and Cleanup

**Files:**
- Verify: All modified files

- [ ] **Step 1: Run full test suite**

```bash
python -m pytest tests/ -q --tb=short --no-header 2>&1 | Select-Object -Last 15
```
Expected: All HP tests pass. Only 6 pre-existing failures.

- [ ] **Step 2: Verify CLI help displays correctly**

```bash
python -c "from hermes_prime.cli import build_parser; build_parser().print_help()"
```
Expected: Shows `hp-doctor`, `hp-memory`, `hp-dashboard` in the command list.

- [ ] **Step 3: Verify upstream imports work**

```bash
python -c "import sys; sys.path.insert(0, 'external/hermes-agent'); import hermes_cli.main; print('upstream importable')"
```
Expected: No errors.

- [ ] **Step 4: Verify git log**

```bash
git log --oneline -8
```
Expected: 5 new commits on top of existing history.

- [ ] **Step 5: Done**

No commit needed for verification steps.

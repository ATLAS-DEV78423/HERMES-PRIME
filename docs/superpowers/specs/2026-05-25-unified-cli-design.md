# Unified CLI — Design Spec

**Date:** 2026-05-25
**Status:** Draft
**Supersedes:** `2026-05-25-interactive-agent-design.md`

## 1. Goal

Make `hermes` a unified entry point for **all** capabilities of both Hermes Prime and the upstream Hermes Agent, so the user has one CLI that exposes:

- Hermes Prime's unique governance features (Sentinel, Vault, Forge, TrustStore, Brain, Learning Loop, Agent Mesh)
- The upstream Hermes Agent's full surface (~30 CLI subcommands, ~80 tools, ~25 messaging platforms, ~25 skill categories, ~18 plugins, all model providers)

All upstream tool execution is already Sentinel-governed via the `handle_function_call` monkey-patch. This spec extends governance hooks to additional upstream commands and resolves naming collisions between the two CLI surfaces.

## 2. Architecture

### Principle: Import, Don't Copy

The upstream `external/hermes-agent/` is consumed in place via `sys.path`. All its CLI subcommands, tools, gateway platforms, skills, and plugins remain untouched. Hermes Prime adds:

1. **Two-pass CLI dispatch** — HP handles its own subcommands; everything else falls through to the upstream parser
2. **Subcommand renaming** — 3 HP subcommands that collide with upstream names get `hp-` prefixes
3. **Governance deepening** — Sentinel hooks extend beyond `handle_function_call` to command-level governance

### Two-pass Dispatch

```
hermes <cmd> [args]
    │
    ├── 1. HP parser (parse_known_args)
    │     │
    │     ├── HP-native cmd? → HP handler (brain, learn, agents, etc.)
    │     ├── HP-renamed cmd? → HP handler (hp-doctor, hp-memory, hp-dashboard)
    │     ├── HP-governed upstream? → HP wrapper → upstream (chat, gateway)
    │     └── Unknown? → fall through
    │
    └── 2. Upstream passthrough
          │
          └── hermes_cli/main.main(argv)
                → Sentinel governance already active via sys.path monkey-patch
```

The upstream parser handles ~30 subcommands (`setup`, `model`, `cron`, `kanban`, `skills`, `tools`, `profile`, `plugins`, `backup`, `auth`, `sessions`, etc.) without HP needing to know about them.

### Subcommand Classification

All 18 current HP subcommands plus the upstream's ~30 are classified into four categories:

| Category | Count | Rule | Examples |
|---|---|---|---|
| HP-native | 13 | Keep as-is | `graphify`, `repair`, `inspect`, `mint`, `evaluate`, `patch`, `replay`, `models`, `run`, `agents`, `learn`, `brain`, `tui` |
| HP-renamed | 3 | Prefix with `hp-` | `hp-doctor`, `hp-memory`, `hp-dashboard` |
| HP-governed upstream | 2 | Keep as-is (already governed) | `chat`, `gateway` |
| Upstream-native | ~30 | Automatic passthrough | `setup`, `model`, `cron`, `kanban`, etc. |

### Collision Resolution

Three collisions exist because HP and upstream use the same name for different concepts:

| Name | HP concept | Upstream concept | Resolution |
|---|---|---|---|
| `doctor` | HP workspace health (trust store, memory, policy engine, SQLite) | Upstream config/env health (`~/.hermes/config.yaml`) | `hermes hp-doctor` → HP; `hermes doctor` → upstream |
| `memory` | Local fact store (write/recall/list/revoke/gc with depth tiers) | Upstream memory provider config (honcho, mem0, etc.) | `hermes hp-memory` → HP; `hermes memory` → upstream |
| `dashboard` | Textual TUI live dashboard (rich terminal) | Upstream web dashboard (Flask/React on port 9119) | `hermes hp-dashboard` → HP; `hermes dashboard` → upstream |

### Passthrough Implementation

See section 3.2 for the full two-pass dispatch implementation. The core approach:

1. Call `parser.parse_known_args(argv)` — if HP recognizes the command, handle it
2. Otherwise, call `hermes_cli/main.main(argv)` — upstream handles everything else

## 3. Components

### 3.1 CLI Renaming (`hermes_prime/cli.py`)

Three argparse subcommands change name:

```python
# Before:
doctor_parser = subparsers.add_parser("doctor", ...)

# After:
doctor_parser = subparsers.add_parser("hp-doctor", ...)

# Similarly for memory → hp-memory, dashboard → hp-dashboard
```

The `known_hp` set in `main()` is updated accordingly. All internal handler code within the `if args.command == ...` blocks stays identical — only the parser registration name changes.

### 3.2 Two-pass Dispatch

```python
def main(argv: list[str] | None = None) -> int:
    from hermes_prime.recovery import install_signal_handlers
    install_signal_handlers()

    if argv is None:
        argv = sys.argv[1:]

    # Also check for --prompt auto-detect (only for HP-unique commands)
    known_hp = {
        "graphify", "repair", "inspect", "mint", "evaluate",
        "patch", "replay", "models", "run", "agents",
        "learn", "brain", "tui", "chat", "gateway",
        "hp-doctor", "hp-memory", "hp-dashboard",
    }
    if "--prompt" not in argv and "--autonomous" not in argv:
        non_option = [t for t in argv if t and not t.startswith("-")]
        if len(non_option) == 1 and non_option[0] not in known_hp and non_option[0] not in ("-h", "--help"):
            argv = list(argv) + ["--prompt", non_option[0]]

    # Pass 1: try HP parser
    parser = build_parser()
    args, _ = parser.parse_known_args(argv)
    if vars(args).get("command"):
        return handle_hp_command(args)

    # Pass 2: upstream passthrough
    import hermes_cli.main as upstream
    return upstream.main(argv)
```

The `SystemExit` catch handles the case where argparse exits on an unrecognized command. The upstream parser then takes over cleanly.

### 3.3 Governance Deepening

Beyond the existing `handle_function_call` monkey-patch, add Sentinel evaluation hooks for:

1. **`hermes cron` (upstream)** — before a cron job is scheduled, validate the job's command through Sentinel policy. If rejected, the cron job is denied with an audit trace.

2. **`hermes tools` (upstream)** — tool enable/disable operations get audited through TrustStore. Policy can deny enabling high-risk tools in restricted workspaces.

3. **`hermes model` (upstream)** — model switches are audited in TrustStore with the previous and new model recorded for traceability.

4. **`hermes skills` (upstream)** — skill install/update operations are checked against Sentinel policy for provenance verification.

These hooks use the same `SentinelService.evaluate()` path as tool calls, but with different `ActionType` values:

```python
ActionType.SCHEDULING  # for cron
ActionType.CONFIG_WRITE  # for tools/model/skills config changes
```

Implementation approach for each upstream command hook:

```python
# In governed_cli.py or a new governance_hooks.py module

def wrap_upstream_command(command_name: str, action_type: ActionType):
    """Decorator/context manager that evaluates upstream CLI actions through Sentinel."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Evaluate action through Sentinel
            proposal = ActionProposal(
                action_type=action_type,
                scope=workspace_root,
                params={"command": command_name, "args": args, "kwargs": kwargs},
            )
            decision = sentinel.evaluate(proposal, capability=...)
            if not decision.permitted:
                print(f"Action rejected by Sentinel: {decision.denial_reason}")
                return 1
            result = func(*args, **kwargs)
            trust_store.store_audit_trace(...)
            return result
        return wrapper
    return decorator
```

These hooks are applied lazily — only when the user invokes the corresponding upstream subcommand — by patching the upstream module's function references just-in-time before the passthrough dispatch.

### 3.4 CLI Command Display

When `hermes` is run without arguments or with `--help`, show a combined summary:

```
usage: hermes <command> [<args>]

Hermes Prime commands:
  brain           Neural brain network commands
  learn           Learning loop commands
  agents          Agent orchestration
  hp-doctor       Diagnose Hermes Prime workspace health
  ...

Upstream commands (passthrough):
  chat            Start interactive chat session (governed)
  gateway         Start messaging gateway (governed)
  setup           Run setup wizard
  model           Select and configure models
  ...
```

This is accomplished by printing HP's help, then importing the upstream parser's help text and appending it.

## 4. File Changes

| File | Change |
|---|---|
| `hermes_prime/cli.py` | Rename `doctor`→`hp-doctor`, `memory`→`hp-memory`, `dashboard`→`hp-dashboard`; add two-pass dispatch in `main()`; update `known_hp` set |
| `hermes_prime/__init__.py` | No change (exports are by module, not by CLI name) |
| `hermes_prime/orch/governance_hooks.py` | **New** — upstream command governance wrapper functions |
| `tests/test_cli.py` | Update tests for renamed subcommands; add passthrough dispatch tests |
| `tests/test_cli_and_bundle.py` | Update any references to renamed commands |
| `tests/orch/` | Update imports if needed |

## 5. Data Flow

```
User: hermes setup
  → HP parser: unknown cmd
  → Upstream passthrough
  → hermes_cli/main.main(["setup"])
  → Sentinel handle_function_call already active
  → Works exactly like upstream hermes, but every tool call is governed

User: hermes hp-doctor --strict
  → HP parser: hp-doctor matched
  → HP doctor handler (unchanged logic, just renamed)
  → Same health checks as before

User: hermes chat --model claude
  → HP parser: chat matched
  → run_governed_chat()
  → GovernedCLI launcher → upstream HermesCLI
  → Every tool call through Sentinel

User: hermes cron list
  → HP parser: unknown cmd
  → Upstream passthrough
  → cron handler runs upstream
  → Before scheduling: Sentinel evaluates the cron command
  → Audit trace stored
```

## 6. Governance Hooks Detail

### 6.1 Cron Hook

```python
# Patched into upstream cron module at passthrough time
def _governed_add_job(schedule: str, command: str, *args, **kwargs):
    proposal = ActionProposal(
        action_type=ActionType.SCHEDULING,
        scope=workspace_root,
        params={"schedule": schedule, "command": command},
    )
    token = vault.mint_capability(...)
    decision = sentinel.evaluate(proposal, token)
    if not decision.permitted:
        raise PermissionError(f"Cron job rejected: {decision.denial_reason}")
    return _original_add_job(schedule, command, *args, **kwargs)
```

### 6.2 Tool Config Hook

```python
def _governed_toggle_tool(tool_name: str, enable: bool):
    proposal = ActionProposal(
        action_type=ActionType.CONFIG_WRITE,
        scope=workspace_root,
        params={"tool": tool_name, "enable": enable},
    )
    token = vault.mint_capability(...)
    decision = sentinel.evaluate(proposal, token)
    if not decision.permitted:
        raise PermissionError(f"Tool config rejected: {decision.denial_reason}")
    return _original_toggle_tool(tool_name, enable)
```

### 6.3 Skill Hook

```python
def _governed_install_skill(skill_name: str, source: str):
    proposal = ActionProposal(
        action_type=ActionType.CONFIG_WRITE,
        scope=workspace_root,
        params={"skill": skill_name, "source": source, "operation": "install"},
    )
    token = vault.mint_capability(...)
    decision = sentinel.evaluate(proposal, token)
    if not decision.permitted:
        raise PermissionError(f"Skill install rejected: {decision.denial_reason}")
    return _original_install_skill(skill_name, source)
```

## 7. Testing Strategy

| Test | What it covers |
|---|---|
| `test_renamed_subcommands_registered` | `hp-doctor`, `hp-memory`, `hp-dashboard` appear in parser |
| `test_original_names_removed` | `doctor`, `memory`, `dashboard` no longer in HP parser (they're upstream's) |
| `test_unknown_cmd_falls_through` | When HP doesn't recognize the cmd, upstream parser is called |
| `test_governed_chat_still_works` | Chat command unchanged after rename |
| `test_governed_gateway_still_works` | Gateway command unchanged after rename |
| `test_cron_governance_hook` | Cron scheduling is evaluated by Sentinel |
| `test_tool_config_governance_hook` | Tool enable/disable is Sentinel-evaluated |
| `test_skill_install_governance_hook` | Skill install is Sentinel-evaluated |
| `test_doctor_handler_renamed` | `hp-doctor` runs the same doctor logic |
| `test_memory_handler_renamed` | `hp-memory` runs the same memory logic |
| `test_dashboard_handler_renamed` | `hp-dashboard` runs the same dashboard logic |

## 8. Out of Scope (Phase 1)

- Ink/React TUI integration (`ui-tui/`) — deferred
- Model provider-level governance — defers to upstream's existing credential/API key management
- Upstream update tracking — the `sys.path` import means HP automatically uses whatever version is in `external/hermes-agent/`

# Interactive Agent — Design Spec

**Date:** 2026-05-25
**Status:** Draft
**Supersedes:** N/A

## 1. Goal

Enable interactive conversation with a Sentinel-governed Hermes Prime agent through:
- A terminal chat session (`hermes chat`)
- External messaging gateways (Slack, Discord, Telegram, etc.)

Without duplicating the conversation loop, streaming, CLI, or gateway infrastructure already built in the upstream `external/hermes-agent/`.

## 2. Architecture

### Principle: Import, Don't Rewrite

The upstream `external/hermes-agent/` already provides:
- `AIAgent` (`run_agent.py`) — conversation loop with streaming, tool calling, message history, budget tracking
- `HermesCLI` (`hermes_cli/`) — interactive `prompt_toolkit` CLI with markdown rendering, tool display, slash commands
- `gateway/platforms/` — adapters for Slack, Discord, Telegram, WhatsApp, Signal, Matrix, etc.
- `gateway/run.py` — messaging gateway runner with session management

Hermes Prime adds **governance hooks** that intercept tool execution and route it through Sentinel policy evaluation before the tool runs.

### Diagram

```
hermes chat ──┐
              ├── hermes_prime/cli.py ── adds external/hermes-agent to sys.path
hermes gateway ┘                        │
                                  ┌─────┴─────────────────┐
                                  │  GovernedAgentWrapper   │
                                  │  (hermes_prime/orch/)   │
                                  │                         │
                                  │  wraps AIAgent:          │
                                  │    run_conversation()    │
                                  │      ↓                  │
                                  │    pre_tool_hook ──→ Sentinel.evaluate()
                                  │      ↓                  │
                                  │    upstream tool exec    │
                                  │      ↓                  │
                                  │    post_tool_hook        │
                                  │      → audit trail       │
                                  │      → memory store      │
                                  └─────────────────────────┘
```

### Import Path

`external/hermes-agent/` is added to `sys.path` in Hermes Prime's CLI entry point. No copy, no symlink, no install — the upstream code is consumed in place.

```python
# hermes_prime/cli.py
import sys
from pathlib import Path
_HERMES_AGENT = str(Path(__file__).parent.parent / "external" / "hermes-agent")
if _HERMES_AGENT not in sys.path:
    sys.path.insert(0, _HERMES_AGENT)
```

The upstream's dependencies (`openai`, `prompt_toolkit`, `rich`, `httpx`, `pyyaml`, etc.) are added to Hermes Prime's `pyproject.toml` as core dependencies.

## 3. Components

### 3.1. GovernedAgentWrapper (`hermes_prime/orch/governed_agent.py`)

Wraps the upstream `AIAgent` to inject Sentinel governance into the tool-calling loop.

**Interface:**
```python
class GovernedAgentWrapper:
    def __init__(self, agent: AIAgent, sentinel: SentinelService, vault: CapabilityVault,
                 forge: SandboxedForge, trust_store: TrustStore, workspace_root: str):
        ...

    def run_conversation(self, user_message: str, ...) -> dict:
        """Delegates to AIAgent.run_conversation() with governance hooks injected."""
```

**Governance flow for each tool call:**

1. **pre_tool_hook** — called before upstream executes a tool:
   - Parse tool name + args into `ActionProposal`
   - Mint capability token via `Vault.mint_capability()`
   - Evaluate via `Sentinel.evaluate(proposal, token)`
   - If **REJECTED**: return denial to agent as tool error result, log audit trace
   - If **APPROVED**: proceed to step 2

2. **Upstream tool execution** — the upstream `handle_function_call()` runs normally

3. **post_tool_hook** — called after tool returns:
   - Store audit trace in `TrustStore`
   - Write execution outcome to memory store
   - Record outcome for learning loop

**Hook injection:** The upstream `AIAgent` uses `handle_function_call()` (imported from `model_tools` into `run_agent` module namespace). After importing `run_agent`, replace `run_agent.handle_function_call` with the governed version:

```python
import run_agent
_original = run_agent.handle_function_call

def _governed(name, args, task_id=None, tool_call_id=None, session_id=None):
    # Sentinel evaluation
    proposal = ActionProposal(...)
    token = vault.mint_capability(...)
    decision = sentinel.evaluate(proposal, token)
    if not decision.permitted:
        return json.dumps({"error": f"Rejected by Sentinel: {decision.denial_reason}"})
    # Audit
    trust_store.store_audit_trace(...)
    return _original(name, args, task_id, tool_call_id, session_id)

run_agent.handle_function_call = _governed
agent = run_agent.AIAgent(...)
```

This intercepts every tool call before it executes, routes through Sentinel, and either allows or denies — all without touching upstream code.

### 3.2. Governed CLI (`hermes_prime/orch/governed_cli.py`)

Wraps the upstream `HermesCLI` to use a governed agent.

```python
class GovernedCLI(HermesCLI):
    def __init__(self, governed_agent: GovernedAgentWrapper, ...):
        self.governed_agent = governed_agent
        ...
```

Or composition-based:
```python
def create_governed_cli(sentinel, vault, forge, trust_store, workspace_root):
    upstream_agent = AIAgent(...)
    governed = GovernedAgentWrapper(upstream_agent, ...)
    cli = HermesCLI(agent=governed, ...)
    return cli
```

The upstream `HermesCLI` exposes the agent as a parameter or via a callback. If it doesn't, a thin monkey-patch at initialization time replaces the agent reference.

### 3.3. Gateway Wrapper

The upstream `gateway/run.py` creates `AIAgent` sessions for each incoming message. A governed gateway wrapper replaces the upstream's agent factory with `GovernedAgentWrapper`.

```python
# hermes_prime/gateway/governed_gateway.py
def create_governed_session(platform: str, message: dict,
                            sentinel, vault, forge, trust_store) -> GovernedAgentWrapper:
    upstream_agent = AIAgent(...)
    return GovernedAgentWrapper(upstream_agent, ...)
```

### 3.4. CLI Commands (`hermes_prime/cli.py`)

```
hermes chat [--model <model>] [--scope <path>]
    Launches interactive CLI session with governed agent.

hermes gateway start [--platforms slack,discord]
    Starts messaging gateway with governed sessions.
```

The `hermes` entry point already points to `hermes_prime.cli:main`. The `chat` and `gateway` subcommands are added to the existing argparse tree, alongside existing commands like `run`, `agents`, `doctor`, `mint`, `evaluate`, etc.

## 4. Dependencies

Add to `pyproject.toml` `[project.dependencies]` from upstream:

```
openai>=2.24.0,<3
prompt_toolkit>=3.0.52,<4
rich>=14.3.3,<15
httpx>=0.28.1,<1
pyyaml>=6.0.3,<7
jinja2>=3.1.6,<4
pydantic>=2.13.4,<3
tenacity>=9.1.4,<10
python-dotenv>=1.2.2,<2
```

Messaging gateway extras (`[gateway]`):
```
slack-bolt>=1.27.0,<2
discord.py>=2.7.1,<3
python-telegram-bot>=22.6,<23
```

## 5. File Changes

| File | Change |
|------|--------|
| `pyproject.toml` | Add upstream deps (`openai`, `prompt_toolkit`, `rich`, etc.) |
| `hermes_prime/cli.py` | Add sys.path setup, add `chat` + `gateway` subcommands |
| `hermes_prime/orch/governed_agent.py` | **New** — `GovernedAgentWrapper` class |
| `hermes_prime/orch/governed_cli.py` | **New** — governed CLI launcher |
| `hermes_prime/gateway/governed_gateway.py` | **New** — governed gateway session factory |

No changes to `external/hermes-agent/` — it stays as-is, consumed in place.

## 6. Data Flow (per conversation turn)

```
User types message
  ↓
HermesCLI receives input
  ↓
AIAgent.run_conversation(message)
  ↓   ↓         ↓
  [for each tool call in LLM response]:
    pre_tool_hook:
      parse action → ActionProposal
      mint capability → CapabilityToken
      Sentinel.evaluate(proposal, token)
      if REJECTED → return denial to agent
      if APPROVED → proceed
    ↓
    upstream handle_function_call() → tool result
    ↓
    post_tool_hook:
      TrustStore.store_audit_trace()
      MemoryStore.write(claim)
      OutcomeTracker.record()
  ↓
Agent returns response to user
```

## 7. Out of Scope (Phase 1)

- New TUI framework — the upstream's `prompt_toolkit` CLI is sufficient for v1. The upstream's Ink/React TUI (`hermes --tui`) can be added later.
- Dashboard / web UI — the upstream's `hermes dashboard` covers this.
- Non-messaging gateways — cron, kanban, etc. are upstream features that don't need governance wrapping initially.

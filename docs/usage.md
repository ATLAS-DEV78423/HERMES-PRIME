# Hermes Prime — Usage Manual

This manual covers everyday operation of the Hermes Prime CLI: health checks, repairs, governance, memory, and autonomous execution.

All commands work as **`hermes`**, **`hermes-prime`**, or **`sentinel`**.

---

## Command overview

| Command | Purpose |
|---------|---------|
| `hermes doctor` | Diagnose installation and workspace health |
| `hermes repair` | Auto-fix safe workspace issues |
| `hermes inspect` | Show policy bundle and backend manifest |
| `hermes mint` | Create intent root + capability token |
| `hermes evaluate` | Run Sentinel on an action proposal |
| `hermes patch` | Governed file mutation via Sandboxed Forge |
| `hermes replay` | View audit traces in TrustStore |
| `hermes memory` | Memory fabric (write, recall, list, revoke, gc) |
| `hermes run` | Autonomous LLM-driven task |
| `hermes agents` | Agent mesh orchestration |
| `hermes graphify` | Knowledge graph build/query |
| `hermes dashboard` | Textual live dashboard |
| `hermes tui` | Terminal UI components |
| `hermes repl` | Interactive governed REPL |
| `hermes sessions` | Session management |
| `hermes skills` | Skills hub (search, install, manage) |
| `hermes cron` | Scheduled job management |
| `hermes profile` | Multi-instance profile management |
| `hermes gateway` | Multi-platform messaging gateway |

Global flags (most commands):

| Flag | Description |
|------|-------------|
| `--workspace PATH` | Workspace root (default: current directory) |
| `--json` | Machine-readable JSON output |

---

## System health: `doctor` and `repair`

Use these commands first when something fails, after upgrading, or on a new machine.

### `hermes doctor`

Runs a full diagnostic across layout, policy bundle, backends, Python dependencies, SQLite stores, and Vault connectivity.

```bash
hermes doctor
```

**Example output:**

```text
Hermes Prime v0.2.1 — healthy
  Python: 3.12.10
  Workspace: /path/to/HERMES-PRIME
  Auto-fixable issues: 1 (run: hermes repair)

WARNING:
  - [layout] Missing subdirectory: .hermes-prime/palace [fixable]

INFO:
  - [dependencies] Optional: ollama not installed (local LLM (Ollama))
  ...

9 checks passed.
```

#### Options

| Flag | Description |
|------|-------------|
| `--strict` | Exit code `1` if any **ERROR**-level check fails |
| `--json` | Emit structured JSON (for CI or scripts) |

```bash
hermes doctor --strict
hermes doctor --json | jq '.healthy'
```

#### What `doctor` checks

| Category | Checks |
|----------|--------|
| **layout** | `.hermes-prime/`, `bin/`, `palace/` |
| **policy** | `infrastructure/policy_engine`, policies/schemas, bundle availability |
| **backends** | OPA + tree-sitter readiness |
| **dependencies** | Required: pydantic, tree-sitter, wasmtime, requests |
| **dependencies (optional)** | chromadb, mempalace, graphify, ollama, hvac |
| **storage** | `trust.db` and `memory.db` integrity |
| **fabric** | Fabric pattern root (warning if missing) |
| **vault** | HashiCorp Vault or env fallback |

---

### `hermes repair`

Applies **safe, automatic fixes** for issues flagged by `doctor`. Does not install pip packages or download OPA.

```bash
hermes repair
```

#### What `repair` fixes

| Action | Description |
|--------|-------------|
| Create `.hermes-prime/` | State directory |
| Create `bin/`, `palace/` | Subdirectories for tools and MemPalace |
| Create `policies/`, `schemas/` | Only if missing (never overwrites Rego) |
| Initialize `trust.db` | Trust store schema |
| Initialize `memory.db` | Default SQLite memory backend |
| Rebuild corrupt DBs | With `.bak.<timestamp>` backup (see `--force`) |
| WAL checkpoint | Truncate SQLite WAL on healthy databases |

#### Options

| Flag | Description |
|------|-------------|
| `--dry-run` | Show planned fixes without changing files |
| `--force` | Rebuild corrupted SQLite databases (backs up first) |
| `--json` | JSON report; includes `post_repair` doctor summary when not dry-run |

```bash
# Preview
hermes repair --dry-run

# Fix layout and init databases
hermes repair

# Recover from corrupt trust.db / memory.db
hermes repair --force

# Verify
hermes doctor
```

#### Recommended workflow

```bash
hermes doctor          # See what's wrong
hermes repair          # Fix auto-fixable items
hermes doctor --strict # Confirm clean (for CI)
```

---

## Governance workflow

Typical secure flow: inspect → mint → evaluate → patch → replay.

```bash
# 1. Inspect policy bundle and backends
hermes inspect --json

# 2. Mint scoped intent + capability
hermes mint \
  --scope /workspace/project \
  --issued-to operator_1 \
  --capability cap:file-read:scoped \
  --actions filesystem.read

# 3. Evaluate a proposed action
hermes evaluate \
  --intent-root <urn:uuid:...> \
  --token-id <urn:uuid:...> \
  --action-type filesystem.read \
  --scope /workspace/project/src

# 4. Patch a file (Sandboxed Forge)
hermes patch \
  --intent-root <urn:uuid:...> \
  --token-id <urn:uuid:...> \
  --path src/main.py \
  --content "<new content>" \
  --commit

# 5. Replay audit trail
hermes replay --trace-id <urn:uuid:...>
```

---

## Memory fabric

Default backend is SQLite (`--memory-backend sqlite`).

```bash
# Write (requires existing intent root from mint)
hermes memory write \
  --intent-root <urn:uuid:...> \
  --claim "User prefers tabs over spaces" \
  --confidence 0.9

# Search
hermes memory recall --query "tabs spaces" --limit 10

# List all claims
hermes memory list

# Revoke / garbage collect
hermes memory revoke --fact-id <urn:uuid:...>
hermes memory gc --before 2025-01-01T00:00:00Z
```

Optional backends (install extra packages first):

```bash
hermes memory write --memory-backend mempalace --memory-backend-config ~/.hermes-prime/palace ...
hermes memory write --memory-backend graphify ...
```

---

## Autonomous execution

Requires a running Ollama (or vLLM) instance when using real models:

```bash
hermes models --provider ollama
hermes run --task "Summarize the README" --model mistral --scope .
```

Prompt-driven orchestrator (fabric + policy, no LLM):

```bash
hermes --prompt "read sample"
```

---

## Agent orchestration

```bash
hermes agents list
hermes agents spawn --task "analyze src/" --scope ./src --parent <agent-id>
hermes agents kill --agent-id <urn:uuid:...>
```

### Governance hooks
Sentinel policy evaluation is automatically applied to agent actions, cron jobs, tool execution, and skills:

```bash
# Cron governance
hermes cron list
hermes cron add --schedule "0 0 * * *" --task "daily-health-check"

# Tool governance
hermes tools list
hermes tools execute --name terminal --args '{"command": "ls"}'
```

### Kanban multi-agent board
Coordinate multiple agents through a shared kanban board:

```bash
hermes kanban list
hermes kanban add --column backlog --title "Implement feature X" --description "..."
hermes kanban move --card-id <id> --column in-progress
```

---

## Graphify knowledge graph

```bash
hermes graphify status
hermes graphify build --target .
hermes graphify query "authentication" --depth 2
hermes graphify import
```

---

## Terminal UI

```bash
hermes dashboard          # Live Textual dashboard
hermes tui logo           # Branding
hermes tui boot           # Boot animation
```

---

## Interactive REPL

Start a governed interactive session with LLM-based conversation, tool calling, and persistent history:

```bash
hermes repl
```

Once inside the REPL:
- Type any question or command — the LLM responds conversationally
- Use tools automatically (web_search, web_fetch, terminal, todo)
- `/clear` — reset conversation history
- `/quit` or `/exit` — exit the REPL

### Options

| Flag | Description |
|------|-------------|
| `--model` | LLM model to use (default: mistral) |

---

## Session management

Persistent session store with FTS5 full-text search, source tagging, and JSONL export.

```bash
hermes sessions list                          # List all sessions
hermes sessions list --source cli             # Filter by source
hermes sessions list --limit 20               # Limit results
hermes sessions search "deployment"           # Full-text search
hermes sessions view <session-id>             # View messages
hermes sessions rename <session-id> "new"     # Rename session
hermes sessions delete <session-id>           # Delete session
hermes sessions export --output sessions.jsonl  # Export as JSONL
hermes sessions stats                         # Store statistics
hermes sessions prune --older-than 30         # Prune old sessions
```

---

## Skills hub

Search, browse, inspect, install, and manage skills from upstream registries.

```bash
hermes skills list                            # List installed skills
hermes skills search "code review"            # Search registries
hermes skills browse --page 1                 # Browse all skills
hermes skills inspect <identifier>            # Preview a skill
hermes skills install <identifier>            # Install from hub
hermes skills check                           # Check for updates
hermes skills uninstall <name>                # Remove a skill
```

All skills operations are audited via Sentinel audit tracing.

---

## Cron scheduler

Schedule recurring or one-shot tasks with duration, cron expression, or ISO timestamp formats.

```bash
hermes cron list                              # List scheduled jobs
hermes cron list --all                        # Include disabled jobs
hermes cron create \
  --name "daily-backup" \
  --schedule "0 3 * * *" \
  --prompt "Run database backup" \
  --model mistral \
  --workdir /path/to/project
hermes cron pause <job-id>                    # Pause a job
hermes cron resume <job-id>                   # Resume a job
hermes cron run <job-id>                      # Trigger immediately
hermes cron remove <job-id>                   # Remove a job
hermes cron status                            # Check scheduler status
```

Schedule format: `30m` (duration), `0 9 * * *` (cron), `2026-06-01T09:00:00Z` (ISO).

---

## Profile management

Multi-instance support with fully isolated HERMES_HOME directories.

```bash
hermes profile list                           # List all profiles
hermes profile create dev --description "Dev environment"
hermes profile switch dev                     # Switch active profile
hermes profile rename dev staging             # Rename a profile
hermes profile delete dev                     # Delete a profile
hermes profile active                         # Show active profile
```

Each profile has its own config, API keys, memory, sessions, and skills.

---

## Gateway

Multi-platform messaging gateway (wraps upstream gateway system).

```bash
hermes gateway --platforms slack              # Start Slack gateway
hermes gateway --platforms telegram,discord   # Multi-platform
```

---

## Exit codes

| Command | Exit `0` | Exit non-zero |
|---------|----------|----------------|
| `doctor` | Healthy, or not `--strict` | `--strict` and ERROR-level issues |
| `repair` | All applied actions succeeded | Any applied action failed |
| Other commands | Success | Failure / Sentinel deny |

---

## Further reading

- [Setup Manual](setup.md)
- [Memory Governance](memory_governance.md)
- [Guardrails](guardrails.md)
- [Hermes doctrine](../hermes/DOCTRINE.md)

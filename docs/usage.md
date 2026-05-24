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

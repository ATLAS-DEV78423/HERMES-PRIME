# HERMES-PRIME

*A sovereign, deterministic governance engine for autonomous operations.*

## Description

HERMES-PRIME is a local-first, high-trust cognitive infrastructure designed for AI agent orchestration. Unlike traditional probabilistic agent architectures, HERMES-PRIME flips the paradigm: **it builds deterministic governance first.** 

Instead of relying on an LLM to police itself, HERMES-PRIME forces every generated action proposal through a brutal, deterministic safety shield (Sentinel) and an isolated execution environment (Forge). It guarantees that agents can reason autonomously, but cannot act destructively, bypass capability scopes, or hallucinate credentials.

**Key Features:**
* **Sentinel Core:** A 7-layer blocking deterministic policy engine (powered by OPA/Rego).
* **Sandboxed Forge:** Overlaid, hash-chained filesystem for safe mutation and instant rollback.
* **Bounded Extractors:** Ripgrep and Tree-sitter powered file miners that return signed attestations, not context-wasting raw dumps.
* **Cognitive Trust Store:** Verifiable cryptographic provenance and capability tokens for every action.
* **Elite Terminal UI:** A custom-designed, industrial "deep archive" visual identity that commands operational clarity.

---

## Installation

HERMES-PRIME is built on Python 3.10+ and relies on native binary fallbacks when necessary. 

### Prerequisites

* Python 3.10 or higher
* `git`
* (Optional) Local `opa` binary for optimized policy enforcement
* (Optional) `rg` (ripgrep) installed on system path for accelerated file mining

### One-Liner Install

For convenience, you can install HERMES-PRIME securely using our setup script (pinned to the v0.2.1 release):

```bash
curl -sSL https://raw.githubusercontent.com/ATLAS-DEV78423/HERMES-PRIME/v0.2.1/install.sh | bash
```

### Manual Quick Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/ATLAS-DEV78423/HERMES-PRIME.git
   cd HERMES-PRIME
   ```

2. **Install the package:**
   We recommend installing within a virtual environment.
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
   pip install -e .
   ```

3. **Verify installation:**
   ```bash
   hermes doctor
   hermes repair    # if doctor reports fixable issues
   hermes doctor    # confirm healthy
   ```

   The `hermes` command is the recommended CLI name (`hermes-prime` and `sentinel` are aliases).

---

## System health (`doctor` & `repair`)

Hermes can diagnose and repair its own workspace automatically.

| Command | Purpose |
|---------|---------|
| `hermes doctor` | Check backends, policy bundle, databases, and dependencies |
| `hermes repair` | Create `.hermes-prime/`, init SQLite stores, fix layout issues |

```bash
hermes doctor              # human-readable report
hermes doctor --strict     # exit 1 on errors (for CI/scripts)
hermes doctor --json       # machine-readable output

hermes repair              # apply safe fixes
hermes repair --dry-run    # preview without changes
hermes repair --force      # rebuild corrupt DBs (backs up first)
```

See the [Setup Manual](docs/setup.md) and [Usage Manual](docs/usage.md) for full details.

---

## Usage Guide

HERMES-PRIME provides a secure CLI built around explicit intent delegation and capability minting. 

```bash
# 0. Check system health (recommended first step)
hermes doctor

# 1. Inspect the loaded Sentinel policy bundle
hermes-prime inspect --json

# 2. Mint a scoped intent root and capability token
hermes-prime mint --scope /workspace/project --issued-to operator_1 --capability file-read --actions filesystem.read

# 3. Evaluate a proposed action against the deterministic Sentinel Core
hermes-prime evaluate --intent-root <urn:uuid:...> --token-id <urn:uuid:...> --action-type filesystem.read --scope /workspace/project/src

# 4. Patch a file via the Sandboxed Forge (requires Sentinel approval)
hermes-prime patch --intent-root <urn:uuid:...> --token-id <urn:uuid:...> --path src/main.py --content "<new content>" --commit

# 5. Review the immutable audit log / provenance trail
hermes-prime replay --trace-id <urn:uuid:...>
```

### Interactive REPL
Start a governed interactive session with persistent history and tool access:
```bash
hermes repl
```

Session management:
```bash
hermes sessions list                    # List all sessions
hermes sessions search "query"          # Search session content
hermes sessions view <id>               # View messages in a session
hermes sessions rename <id> "new name"  # Rename a session
hermes sessions delete <id>             # Delete a session
hermes sessions export --output out.jsonl  # Export sessions as JSONL
hermes sessions stats                   # Show session store statistics
hermes sessions prune --older-than 30   # Prune old sessions
```

### Skills Hub
Search, install, and manage skills from upstream registries:
```bash
hermes skills list                      # List installed skills
hermes skills search "code review"      # Search skill registries
hermes skills browse                    # Browse all available skills
hermes skills inspect <identifier>      # Preview a skill
hermes skills install <identifier>      # Install a skill
hermes skills check                     # Check for skill updates
hermes skills uninstall <name>          # Remove a skill
```

### Cron Scheduler
Schedule recurring or one-shot tasks:
```bash
hermes cron list                        # List scheduled jobs
hermes cron create --name backup --schedule "0 3 * * *" --prompt "Run backup"
hermes cron pause <id>                  # Pause a job
hermes cron resume <id>                 # Resume a job
hermes cron run <id>                    # Trigger a job immediately
hermes cron remove <id>                 # Remove a job
hermes cron status                      # Check scheduler status
```

### Profile Management
Isolated multi-instance support:
```bash
hermes profile list                     # List all profiles
hermes profile create dev               # Create a new profile
hermes profile switch dev               # Switch active profile
hermes profile rename dev prod          # Rename a profile
hermes profile delete dev               # Delete a profile
hermes profile active                   # Show active profile
```

### Gateway
Multi-platform messaging gateway:
```bash
hermes gateway --platforms slack        # Start gateway for Slack
hermes gateway --platforms telegram,discord  # Multi-platform
```

### Prompt-Driven Execution
For bounded autonomous execution driven by Fabric extraction:
```bash
hermes-prime --prompt "read sample"
```

## Agent Tools

Hermes Prime provides a sandboxed tool system for agent execution:

| Tool | Description |
|------|-------------|
| `terminal` | Governed shell execution with command allowlisting |
| `code_exec` | Isolated Python code execution with stdout/stderr capture |
| `web_search` | Governed web search with configurable result limits |
| `web_fetch` | URL content fetching with markdown/text/html output |
| `voice` | Text-to-speech and speech-to-text via system audio |
| `vision` | Image capture and processing (webcam, screen, file) |
| `todo` | Persistent task management with create/update/list/delete |

All tools pass through Sentinel policy evaluation before execution.

## Memory & Learning

The memory fabric provides tiered storage with consolidation:

- **Working memory**: short-term scratchpad (24h TTL)
- **Episodic memory**: observed events (90d TTL)  
- **Reflective memory**: post-task consolidation (30d TTL)
- **Semantic memory**: extracted facts (permanent)
- **Strategic memory**: compressed learnings (permanent)
- **Governance memory**: policies and trust rules (immutable)

Memory claims are cryptographically signed with HMAC provenance and consolidated via `ReflectiveConsolidator`.

## Documentation

### Operator manuals (`docs/`)

* [Setup Manual](docs/setup.md) — installation, verification, troubleshooting
* [Usage Manual](docs/usage.md) — CLI reference (`doctor`, `repair`, mint, memory, agents, …)
* [Memory Governance](docs/memory_governance.md) — memory fabric and trust tiers
* [Guardrails](docs/guardrails.md) — security and runtime recommendations
* [Documentation index](docs/index.md) — full doc map

### Architecture & doctrine (`hermes/`)

* [FOUNDATIONAL_PRIMITIVES.md](FOUNDATIONAL_PRIMITIVES.md) — core philosophy
* [CLI_IDENTITY.md](hermes/CLI_IDENTITY.md) — visual and operational tone
* [SCHEMA_REGISTRY.md](hermes/SCHEMA_REGISTRY.md) — strict boundary types

## Upstream Infrastructure & Submodules

HERMES-PRIME acts as the deterministic governance orchestrator across several powerful upstream primitives. The following external repositories are utilized either as core dependencies, submodules, or reference architectures (tracked via our `WORKSPACE_MANIFEST.yaml`):

* **Policy & Governance:** [Open Policy Agent (OPA)](https://github.com/open-policy-agent/opa)
* **File Extraction & Mining:** [Ripgrep](https://github.com/BurntSushi/ripgrep) and [Tree-sitter](https://github.com/tree-sitter/tree-sitter)
* **Trust & Cryptography:** [Sigstore](https://github.com/sigstore/sigstore) and [HashiCorp Vault](https://github.com/hashicorp/vault)
* **Orchestration references:** [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) and [Fabric](https://github.com/danielmiessler/fabric)

*Note: These external systems are tracked as Git submodules (or references) to avoid bloating the HERMES-PRIME repository with duplicate upstream code.*

## License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Developer Quickstart

Install dev tools and run tests locally:

```bash
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -U pip
pip install -r requirements-dev.txt
pip install -e .
ruff check .
pytest -q
```

Install pre-commit hooks:

```bash
pip install pre-commit
pre-commit install
pre-commit run --all-files
```

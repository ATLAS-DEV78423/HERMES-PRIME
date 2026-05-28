# Hermes Prime — Setup Manual

This guide walks through installing Hermes Prime, verifying your environment, and repairing common workspace issues.

## Requirements

| Component | Version / notes |
|-----------|-----------------|
| Python | 3.10 or higher (3.12 recommended) |
| Git | Any recent version |
| OS | Linux, macOS, or Windows |

### Optional (improves performance or unlocks features)

| Tool | Purpose |
|------|---------|
| [OPA](https://www.openpolicyagent.org/) | Native policy evaluation (fallback: WASM bundle + wasmtime) |
| [ripgrep](https://github.com/BurntSushi/ripgrep) (`rg`) | Faster file mining |
| [Ollama](https://ollama.ai/) | Local LLM for `hermes run` |
| HashiCorp Vault (`hvac`) | Production secrets backend |
| chromadb | Mem0 / Atlas memory backends |
| mempalace | MemPalace memory backend |

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/ATLAS-DEV78423/HERMES-PRIME.git
cd HERMES-PRIME
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv .venv
```

Activate it:

- **Linux / macOS:** `source .venv/bin/activate`
- **Windows (PowerShell):** `.venv\Scripts\Activate.ps1`
- **Windows (cmd):** `.venv\Scripts\activate.bat`

### 3. Install Hermes Prime

```bash
pip install -U pip
pip install -e ".[dev]"
```

This registers three CLI entry points (same program, different names):

| Command | Alias |
|---------|--------|
| `hermes` | Short name (recommended) |
| `hermes-prime` | Package name |
| `sentinel` | Legacy alias |

### 4. Verify installation

Run the built-in health check:

```bash
hermes doctor
```

You should see **healthy** (or a short list of fixable warnings). If directories or databases are missing:

```bash
hermes repair
hermes doctor
```

### 5. One-line install (release pin)

```bash
curl -sSL https://raw.githubusercontent.com/ATLAS-DEV78423/HERMES-PRIME/v0.2.1/install.sh | bash
```

---

## First-time workspace layout

After `hermes repair`, Hermes creates a local state directory under your workspace:

```
.your-project/
└── .hermes-prime/
    ├── trust.db      # Audit traces, intents, capabilities
    ├── memory.db     # Default SQLite memory fabric
    ├── bin/          # Optional local OPA binary location
    └── palace/       # MemPalace backend data (if used)
```

Policy files live in the repository (not generated):

```
infrastructure/policy_engine/
├── policies/    # Rego rules
└── schemas/     # JSON schemas for actions
```

---

## Environment variables

| Variable | Purpose |
|----------|---------|
| `HERMES_PRIME_OPA_BINARY` | Path to `opa` executable |
| `HERMES_PRIME_OPA_WASM_BUNDLE` | Path to compiled policy WASM |
| `HERMES_*` | Vault/env fallback prefix for secrets |

---

## Troubleshooting setup

### `hermes doctor` reports missing critical backends

Install Python dependencies:

```bash
pip install -e ".[dev]"
```

Ensure **tree-sitter** grammars and **wasmtime** are present (included in default `pyproject.toml` dependencies). For native OPA:

```bash
# Example: download OPA for your OS from openpolicyagent.org
export HERMES_PRIME_OPA_BINARY=/path/to/opa
hermes doctor
```

### Corrupt or locked SQLite databases

```bash
hermes repair --force
```

This backs up `trust.db` / `memory.db` with a timestamped `.bak.*` file before rebuilding.

### Strict CI-style check

```bash
hermes doctor --strict
```

Exits with code `1` if any **ERROR**-level issue is found (useful in scripts).

### JSON output for automation

```bash
hermes doctor --json
hermes repair --json
```

---

## Developer setup

```bash
pip install -e ".[dev]"
ruff check .
mypy hermes_prime/ infrastructure/ miners/ --ignore-missing-imports --no-strict-optional
pytest tests/ -q
```

See [CONTRIBUTING.md](../CONTRIBUTING.md) for contribution guidelines.

---

## Next steps

- [Usage Manual](usage.md) — day-to-day CLI commands
- [Memory Governance](memory_governance.md) — memory fabric design
- [Guardrails](guardrails.md) — security and operations
- [Repository README](../README.md) — overview and feature list

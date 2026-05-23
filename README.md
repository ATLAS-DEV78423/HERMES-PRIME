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

3. **Verify Installation:**
   Check the readiness of your fallback backends and local toolchains.
   ```bash
   hermes-prime doctor
   ```

---

## Usage Guide

HERMES-PRIME provides a secure CLI built around explicit intent delegation and capability minting. 

```bash
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

### Prompt-Driven Execution
For bounded autonomous execution driven by Fabric extraction:
```bash
hermes-prime --prompt "read sample"
```

## Documentation

The `hermes/` directory contains the complete doctrine, invariants, gates, and architecture decisions for the project. Start here:
* [FOUNDATIONAL_PRIMITIVES.md](hermes/FOUNDATIONAL_PRIMITIVES.md) - The core philosophy.
* [CLI_IDENTITY.md](hermes/CLI_IDENTITY.md) - The visual and operational tone guidelines.
* [SCHEMA_REGISTRY.md](hermes/SCHEMA_REGISTRY.md) - The strict boundary types.

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

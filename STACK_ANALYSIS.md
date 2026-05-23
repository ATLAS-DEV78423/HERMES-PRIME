# Hermes Prime Stack Analysis

This is the working synthesis of the upstream repositories cloned into `external/`.

The goal is not to absorb every repo wholesale. The goal is to identify which pieces become Hermes Prime primitives, which ones act as references, and which ones remain optional integrations.

## Core repos

### `hermes-agent`

Primary orchestration substrate. This is the closest thing in the set to a runtime agent operating environment.

What it contributes:

- subagents
- skills
- memory
- sandboxing
- tooling
- scheduling
- multi-platform execution
- isolated workstreams

Hermes Prime use:

- good reference for the outer agent shell
- good source of orchestration UX patterns
- not the trust root by itself

### `ATLAS-AI`

Local multi-agent pipeline with planner / researcher / executor structure.

What it contributes:

- a simple multi-agent decomposition
- memory via ChromaDB
- task logging
- feedback-driven reuse of prior responses

Hermes Prime use:

- useful as a lightweight memory-and-workflow prototype
- good reminder that the first version of Atlas can stay simple
- should be subordinated to the stronger provenance model in `cognitive-trust/`

### `SENTINAL`

The repo is currently thin at the root, but the architecture docs define the intended subsystem.

What it contributes:

- VS Code extension surface
- session guardian runtime
- contradiction interception
- bad-practice analysis
- vault brain / durable project memory
- MCP hub
- LLM harness

Hermes Prime use:

- this is the strongest local match for Sentinel as doctrine enforcement
- it should stay deterministic on the blocking path
- its role is governance, not cleverness

## Retrieval and reasoning references

### `fabric`

Prompt/pattern infrastructure with a strong human-augmentation orientation.

Hermes Prime use:

- reference for prompt patterning and structured task prompts
- useful for the retrieval fabric layer
- should not define the trust boundary

### `tree-sitter`

Incremental parsing library and parser generator.

Hermes Prime use:

- foundational AST-aware primitive for file miners
- one of the clearest "must-have" dependencies in the stack

### `ripgrep`

Deterministic recursive search tool.

Hermes Prime use:

- foundational retrieval primitive
- best first-pass search engine for miners and agents

### `llama_index`

Structured retrieval and indexing framework.

Hermes Prime use:

- reference for retrieval and index composition
- optional if the Hermes Prime miner layer stays deterministic-first

### `cody`

The official repository has transitioned to private; the public snapshot is the practical clone target.

What it contributes:

- codebase understanding inside IDE workflows
- semantic search across local and remote repositories
- agentic code-assist patterns

Hermes Prime use:

- reference for semantic navigation and UX
- useful benchmark for what "good codebase cognition" feels like

## Governance and security references

### `opa`

Open Policy Agent.

Hermes Prime use:

- direct reference for Sentinel policy enforcement
- one of the clearest primitives in the stack
- strongest candidate for the deterministic blocking layer

### `vault`

Secret storage, dynamic secrets, leasing, and revocation.

Hermes Prime use:

- direct reference for the Vault subsystem
- essential for capability minting and secret isolation

### `gitleaks`

Secret detector for git repos and files.

Hermes Prime use:

- reference for write-boundary scanning
- useful for Sentinel and Forge hardening

### `trufflehog`

Credential discovery, classification, validation, and analysis.

Hermes Prime use:

- reference for deeper secret scanning and validation
- especially useful where lifecycle-sensitive secrets matter

## Provenance and trust references

### `sigstore`

Shared sigstore framework code.

Hermes Prime use:

- one of the most important provenance references
- strong candidate for the attestation spine

### `in-toto`

Software supply chain layout and link metadata.

Hermes Prime use:

- direct conceptual match for artifact lineage
- excellent model for intent -> step -> output chaining

### `python-tuf`

Reference implementation of TUF.

Hermes Prime use:

- update integrity and revocation patterns
- good reference for trusted distribution / metadata validation

### `slsa`

Supply-chain security framework and specification repo.

Hermes Prime use:

- policy vocabulary for artifact trust levels
- useful for defining provenance maturity

## Runtime and serving references

### `ollama`

Local model runtime and integration launcher.

Hermes Prime use:

- backend primitive, not architecture
- good for local execution and testing

### `vllm`

High-throughput LLM inference and serving.

Hermes Prime use:

- backend primitive for scaling model serving
- should stay below the orchestration and trust layers

## Memory and graph references

### `neo4j`

Graph database.

Hermes Prime use:

- candidate backend for Atlas-like memory graphs
- only worth adopting if the graph query model is truly needed

### `mem0`

Memory layer for personalized AI.

Hermes Prime use:

- useful reference for memory APIs and multi-level state
- strongest caution flag: the default memory model is easy to over-trust

### `zep`

Context engineering platform with relationship-aware retrieval.

Hermes Prime use:

- useful reference for relationship-driven context assembly
- good bridge between retrieval and memory

## Agent and orchestration references

### `continue`

Source-controlled AI checks enforced in CI.

Hermes Prime use:

- excellent reference for policy-as-code in the developer workflow
- useful for review gates and check files

### `aider`

Terminal pair-programming agent.

Hermes Prime use:

- reference for code-edit loop ergonomics
- useful for UI and Git integration patterns

### `langgraph`

Low-level orchestration framework for stateful agents.

Hermes Prime use:

- strong reference for long-running stateful workflows
- useful if Hermes Prime needs explicit graph-based orchestration

## Conclusion

The most important primitive set is:

1. `ripgrep` + `tree-sitter` for deterministic retrieval
2. `OPA` for policy enforcement
3. `Vault` for secret isolation and capability minting
4. `Sigstore` + `in-toto` + `TUF` + `SLSA` for provenance and lineage
5. `hermes-agent`, `ATLAS-AI`, and `SENTINAL` as the core product surfaces

Everything else is either:

- a reference implementation to learn from
- a backend to plug into the architecture
- or an optional runtime enhancement

That division keeps Hermes Prime from becoming an undisciplined pile of agent tools.


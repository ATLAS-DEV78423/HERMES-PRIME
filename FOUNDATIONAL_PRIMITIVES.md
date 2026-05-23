# Foundational Primitives

This document freezes the minimum set of primitives that Hermes Prime should treat as foundational.

The point is to stop the system from becoming recursive, over-agentized, or dependent on too many moving parts before the trust spine is stable.

## Core primitives

### 1. Deterministic retrieval

Use `ripgrep` for fast content search and `tree-sitter` for syntax-aware mining.

Why it matters:

- keeps navigation cheap
- keeps retrieval deterministic
- avoids wasting main-agent context on filesystem walking

### 2. Policy enforcement

Use an OPA-style policy layer for Sentinel.

Why it matters:

- blocking decisions stay deterministic
- policy becomes inspectable and versionable
- the model never gets final authority

### 3. Secret isolation and capability minting

Use Vault-style isolation for secrets and scoped capability tokens.

Why it matters:

- the agent never owns raw secrets
- privileges are short-lived and narrow
- secret handling stays outside model cognition

### 4. Provenance and lineage

Use Sigstore, in-toto, TUF, and SLSA ideas for attestation and trust chains.

Why it matters:

- every meaningful artifact can be traced
- verification becomes reconstructable
- revocation becomes possible

### 5. Retrieval fabric

Use Fabric-style pattern/reasoning infrastructure to convert raw filesystem search into structured reports.

Why it matters:

- the main agent sees answers, not search noise
- reports can be validated before ingestion
- subagents absorb the search complexity

### 6. Memory with provenance

Use graph-backed memory only if it preserves source, time, confidence, and contradiction state.

Why it matters:

- memory is evidence, not truth
- delayed poisoning becomes visible
- retrieval can be audited

### 7. Local model runtime

Use local model runtimes like Ollama or vLLM as execution backends, not as architecture.

Why it matters:

- models are replaceable components
- routing and policy stay above the backend
- the system does not become model-coupled

## What is reference, not primitive

- `OpenDevin`
- `Continue`
- `Aider`
- `LangGraph`
- `Cody`
- `LlamaIndex`

These are useful implementation references, but they should not define the trust boundary or the core object model.

## What not to optimize for too early

- more agents
- more recursion
- more self-improvement loops
- more abstraction layers
- more memory before provenance

If a component cannot be removed without collapsing the system, it is not yet a primitive. It is a dependency that needs to earn its place.

## Build order

1. retrieval and file-mining primitives
2. policy and gating
3. provenance and attestation
4. memory and graph storage
5. orchestration and higher-level agent UX

That order keeps the trust spine ahead of the cleverness.


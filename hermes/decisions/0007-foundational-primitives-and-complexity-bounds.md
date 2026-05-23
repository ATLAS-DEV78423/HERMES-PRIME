# ADR 0007: Codifying Foundational Primitives and Complexity Boundaries

**Status:** Accepted  
**Date:** 2026-05-23  
**Doctrine references:** P1, P2, P3, P7, P9, CP1, CP2, CP5, CP8, CP10  

---

## Context

As the Hermes Prime architecture scales, we face a critical systemic pressure: the temptation to solve complex operational problems by increasing agentic abstraction. This manifest as spawning nested agent swarms, introducing deep recursive reasoning loops, adopting highly abstract multi-agent frameworks (e.g., LangGraph, recursive memory systems), and allowing the agent plane to autonomously modify its own execution code under the guise of "self-improvement."

If left unchecked, this agentic drift destroys the security and reliability posture of the system. Specifically, it violates several core tenets of the Hermes Doctrine:
1. **Correlated Stochastic Failure (§10.4):** Composing probabilistic models in recursive loops does not yield statistical independence; it amplifies error boundaries exponentially, leading to cascading, unpredictable failures.
2. **Exploding Verification Cost (§P2, §10.3):** If a plan is generated recursively across multiple layers of autonomous agents, the cost of verifying the safety and correctness of the downstream actions far exceeds the generation cost. It makes human or deterministic validation impossible, resulting in unsafe autonomy.
3. **Intent Lineage Collapse (§P3, §10.1):** Recursive agents struggle to maintain the cryptographic custody chain of the user's signed **Intent Root**. A child agent spawning a grandchild agent inevitably breaks the provenance lineage, turning authorization into empty theater.
4. **The Clever Complexity Trap (§P9):** Heavy, highly-abstract frameworks (e.g., wholesale imports of LlamaIndex or multi-agent graph runtimes) introduce hidden execution pathways, complex state managers, and massive dependency trees. This creates side-channel risks, makes threat-modeling impossible, and directly violates §P9 ("Boring beats clever").

To prevent Hermes Prime from collapsing into the very chaos our doctrine was engineered to prevent, we must draw a hard boundary. We must define the **Atomic Foundational Primitives**—the irreducible, deterministic, and sandboxed building blocks of the system—and establish strict complexity bounds that isolate probabilistic heuristic planning from the governing control plane.

---

## Decision

Hermes Prime will permanently codify **Six Atomic Foundational Primitives** as its immutable substrate. Any feature, repository, or tool added to the stack must map directly to one of these primitives or be rejected as unneeded complexity. 

Furthermore, we impose strict **Complexity Boundaries** to enforce deterministic dominance over probabilistic agent swarms.

### 1. The Six Atomic Foundational Primitives

```
                  ┌────────────────────────────────────────┐
                  │          USER INTENT ROOT              │
                  │   (Immutable Cryptographic Anchor)     │
                  └──────────────────┬─────────────────────┘
                                     │
                                     ▼
                  ┌────────────────────────────────────────┐
                  │           POLICY ENGINE                │
                  │   (Deterministic OPA / Sentinel)       │
                  └──────────────────┬─────────────────────┘
                                     │
                                     ▼
                  ┌────────────────────────────────────────┐
                  │          CAPABILITY TOKEN              │
                  │   (Short-lived, scoped JWT/Ucan)       │
                  └──────┬──────────────────────────┬──────┘
                         │                          │
                         ▼                          ▼
            ┌─────────────────────────┐┌─────────────────────────┐
            │      SCOPED MINER       ││  SANDBOXED TRANSACTION  │
            │ (Deterministic Fabric)  ││   (Forge Execution)     │
            └────────────┬────────────┘└────────────┬────────────┘
                         │                          │
                         └───────────┬──────────────┘
                                     ▼
                  ┌────────────────────────────────────────┐
                  │       EPISTEMIC PROVENANCE GRAPH       │
                  │        (Immutable Atlas Belief)        │
                  └────────────────────────────────────────┘
```

#### Primitive A: The Intent Root (Immutable Cryptographic Anchor)
*   **System Layer:** User boundary.
*   **Definition:** A cryptographically signed payload expressing the exact, immutable goal authorized by the human operator at session start. 
*   **Invariant:** The agent plane cannot mint or modify intent. Every downstream transaction proposal must carry an unbroken cryptographic lineage back to this root.

#### Primitive B: The Capability Token (Scoped Privilege Isolation)
*   **System Layer:** Vault / Sentinel.
*   **Definition:** A short-lived, narrowly-scoped, signed cryptographic token (modeled after UCANs or JWTs) that defines the exact resource boundaries (paths, network domains, commands) allowed for a specific sub-task.
*   **Invariant:** Hermes reasons over capability tokens; it never handles raw credentials or master keys.

#### Primitive C: The Scoped Miner (Deterministic Direct Memory Access)
*   **System Layer:** Retrieval Fabric.
*   **Definition:** Bounded, stateless, read-only workers designed to extract structured information (ASTs, file structures, git evolution, dependencies) and return schema-validated reports.
*   **Invariant:** Miners are 100% deterministic (utilizing tools like `tree-sitter`, `ripgrep`, and `git`) or hybrid with strict extraction-only LLMs. They do not maintain state, make decisions, or write files. They are "Cognitive DMA" engines.

#### Primitive D: The Policy Engine (Deterministic Dominance)
*   **System Layer:** Sentinel Core.
*   **Definition:** An isolated, non-probabilistic rule engine (using Open Policy Agent / Rego) that evaluates every action proposal against the Capability Token, the Intent Root, and the current security context.
*   **Invariant:** The Policy Engine contains zero LLM cognition. It is completely immune to prompt injection.

#### Primitive E: The Epistemic Provenance Graph (Attested Belief Store)
*   **System Layer:** Atlas.
*   **Definition:** A structured record store that tracks facts as *evidential beliefs* weighted by source signature, recency, and contradiction state.
*   **Invariant:** Atlas is not an append-only memory dump. Facts ingested from untrusted interfaces are permanently quarantined until corroborated. The graph preserves contradictions instead of overwriting them.

#### Primitive F: The Sandboxed Transaction (Forge Execution)
*   **System Layer:** Forge Core.
*   **Definition:** An isolated environment (e.g., gVisor, WebAssembly, or tightly constrained containers) where authorized mutations are executed, logged in a tamper-evident journal, and snapshot-saved for deterministic rollbacks.
*   **Invariant:** All writes must support rollback. No transaction is committed without deterministic post-condition verification.

---

### 2. Complexity Boundaries

To enforce these primitives and maintain the "Boring beats clever" posture (§P9), the following structural constraints are accepted:

*   **No Recursive Agent Spawning:** The main Hermes agent is the sole orchestrator. Bounded subagents (miners, validators) are strictly task-specific, ephemeral, and non-planning. A subagent may never spawn a subagent, nor can it execute recursive cognitive calls. 
*   **Strict Dependency Quarantine:** Heavy external frameworks (e.g., LlamaIndex, LangGraph, Mem0, Zep) are restricted from core production imports. They are categorized as **Reference Architectures**. We may clone them into `/external` for inspection and manually extract their clean, deterministic mathematical or structural concepts into lightweight, auditable core code. We do *not* run their heavy, highly-abstract runtimes.
*   **Static Orchestration Graphs:** Multi-agent routing and task states must be defined statically in deterministic configurations (e.g., YAML state-charts validated by Sentinel). Dynamic, model-generated routing graphs are forbidden.
*   **No Autonomous Self-Modification:** The system may refine its heuristic prompts or update local search weights. It is strictly barred from dynamically modifying its own schemas, policies, execution libraries, or Sentinel gates. Self-improvement is a localized optimization parameter, never an architectural privilege.

---

## Alternatives Considered

### A. Allowing Unbounded Multi-Agent Swarms (Standard Industry Playbook)
*   *Why Proposed:* Supposedly increases autonomy and splits complex tasks among "expert" agents.
*   *Why Rejected:* Fails to every security invariant. Swarms suffer from correlated failure, prompt injection cascades, and break the intent provenance chain. The cost to verify the output of a swarm exceeds the cost to regenerate the plan deterministically.

### B. Adopting LangGraph / LlamaIndex as Primary Core Substrates
*   *Why Proposed:* Accelerates initial feature velocity by providing pre-built graph state-machines and retrieval pipelines.
*   *Why Rejected:* These libraries are built on the "implicit trust / model-is-the-brain" assumption. They are highly abstract, difficult to sandbox, and pull in massive dependency trees that increase our side-channel and supply-chain attack surface. Under the deletion test (§P7), they make the system fragile and impossible to audit.

### C. Codifying Atomic Primitives and Reference Isolation (Chosen)
*   *Why Accepted:* Segregates the probabilistic engine (Hermes) from the deterministic governance layer (Sentinel) and the execution sandbox (Forge). It treats external codebases as references rather than dependencies, ensuring the core remains "boring," auditable, and highly secure.

---

## Consequences

### Positive
- **Deterministic Bounds:** A compromised or highly hallucinating model cannot escape its capability scope or bypass the policy engine.
- **Supply-Chain Integrity:** Quarantining external frameworks like OPA, Sigstore, and in-toto in the `/external` layout keeps the Hermes core clean, auditable, and secure.
- **Friction Reduction:** Clear architectural rules eliminate decision fatigue during PR reviews—any PR introducing nested agent spawning or heavy runtime dependencies is rejected by default.
- **Observability:** By working on references rather than raw files, all cognitive transactions are compact, hash-verified, and fully auditable.

### Negative
- **Plumbing Overhead:** We must write custom, lightweight wrappers for things we could have imported wholesale (e.g., writing raw tree-sitter AST parsers instead of importing heavy indexers).
- **Reduced Novelty:** Hermes Prime will not display "magic" emergent swarm behaviors. It will look like a highly disciplined, boring operating system.
- **Longer Onboarding:** Engineers must learn to write static Rego policies for Sentinel and structure tasks as transactional transitions.

### Neutral
- Forces all repository structural layout decisions to follow the primitives, resulting in a clean, highly structured monorepo.

---

## References

- ADR 0001: Split-Trust Architecture
- ADR 0002: Deterministic Sentinel Dominance
- ADR 0004: Capability Tokens
- ADR 0005: Atlas Epistemic Belief Store
- ADR 0006: Hermes Treated as Untrusted
- Hermes Doctrine §1 (First Principles), §2 (Trust Architecture), §9 (Non-Goals)
- Cognitive Trust Doctrine §1 (Principles), §2 (The Trust Spine)

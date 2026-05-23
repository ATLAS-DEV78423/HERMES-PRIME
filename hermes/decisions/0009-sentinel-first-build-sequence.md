# ADR 0009: Sentinel-First Build Sequence

**Status:** Accepted  
**Date:** 2026-05-23  
**Doctrine references:** P1, P2, P7, P9  
**Supersedes:** —  

---

## Context

The implementation plan (Stages 0–11) establishes a correct philosophical sequence. But doctrine without enforcement on the *build sequence itself* is decoration. Without an explicit architectural decision record, the gravitational pull of feature development will produce implementation drift — adding Hermes orchestration before Sentinel is hardened, adding Atlas memory before Vault contains secrets, adding miners before the execution boundary exists.

This pattern has destroyed every comparable project that began with cognition rather than governance. The failure mode is not lack of intent. It is the invisible accumulation of "reasonable shortcuts" that each seem cheap individually and collectively produce an unverifiable system.

The specific risk to Hermes Prime is:

- Integrating `hermes-agent` before OPA policies exist creates a window where the agent operates without deterministic constraints.
- Writing miners before Forge sandboxing exists means retrieval outputs can trigger unscoped mutations.
- Building Atlas before Vault means memory writes occur before secrets are isolated.
- Adding autonomy before provenance means generated artifacts exist with no lineage.

Each of these individually is recoverable. All of them together, accumulated quietly over weeks, produce a system that resembles Hermes Prime's architecture diagrams while violating every invariant the diagrams were designed to enforce.

---

## Decision

Hermes Prime will be built in strict sequential phases. No phase may begin until the preceding phase's deliverable criterion is met. The sequence is not a roadmap; it is a gate system applied to the build itself.

### The Sequence

```
Step 1: Sentinel Core (OPA/Rego)         → gate: no execution escapes policy
Step 2: Forge Sandbox (overlays, journal) → gate: no mutation escapes rollback
Step 3: File Miner (ripgrep, attestation) → gate: no retrieval enters context unsigned
Step 4: AST Miner (tree-sitter)          → gate: no structure query brute-forces files
Step 5: Vault + Capability Tokens        → gate: no credential touches agent context
Step 6: Hermes Planner (depth=1, gated)  → gate: no plan executes autonomously
```

### Gate Criteria (per step)

Before moving from Step N to Step N+1, the following must be demonstrably true:

| Step | Gate Criterion |
|------|----------------|
| 1 | A proposed action with an out-of-scope path is **blocked** by OPA before reaching any executor. A valid action is **permitted**. Both outcomes are deterministic and reproducible. |
| 2 | A file write inside Forge can be **rolled back** to pre-write state. The journal contains a hash-chained record of the write. |
| 3 | A file miner dispatch returns a **signed attestation manifest**. Sentinel rejects an unsigned or tampered manifest at the boundary. |
| 4 | An AST query returns **symbol-level structured output** (signatures, call graphs) without reading raw file content into main agent context. |
| 5 | A capability token is **minted by Vault, scoped to a declared intent root, and verified by Sentinel**. The agent never receives the underlying credential. |
| 6 | The planner **proposes** an action and **cannot execute it unilaterally**. Sentinel intercepts. Forge stages. Human or deterministic post-condition gates commit. |

These are the minimum bars. Meeting them is not success — it is the precondition for the next step being safe to start.

---

## Alternatives Considered

### A. Parallel Development
Build Sentinel, Forge, and Hermes simultaneously across teams.  
*Rejected.* Without Sentinel, Hermes integration tests have no policy to run against. Tests either are fake (stub the policy layer) or are omitted. Fake tests produce false confidence. Omitted tests produce known gaps treated as acceptable.

### B. Hermes First, Governance Retrofit
Build the planner quickly, add governance later.  
*Rejected.* This is the industry standard pattern and it consistently fails. Retrofitting governance onto an operational probabilistic system is structurally different from building governance first. Governance first means invariants are load-bearing from day one. Governance retrofitted means invariants are guardrails bolted onto a system that already has established execution paths that bypass them.

### C. Sequential Sentinel-First (chosen)
*Accepted.* Each step produces a component that is:
- functional in isolation
- testable against its gate criterion
- a genuine constraint on the next step rather than a diagram box

---

## Consequences

### Positive
- At no point does an untrusted component have execution authority before a deterministic component constrains it.
- The gate criteria force working software at each step, not architectural documentation.
- Implementation drift is structurally prevented: you cannot reach Step 6 without Steps 1–5 being real.

### Negative
- Hermes cognition is not available for weeks. The system will not feel like an "AI agent" for the entire first month.
- This makes progress hard to demonstrate to stakeholders accustomed to seeing models generate output.
- Engineers comfortable building agent UX first will find this sequence frustrating.

### Neutral
- Each step produces a component usable in production independently. Sentinel Core without Hermes is a valid policy enforcement tool. Forge without Hermes is a valid sandboxed execution environment.

---

## References

- Doctrine §1 (P1, P2, P7, P9)
- ADR 0001 (split-trust)
- ADR 0002 (deterministic Sentinel dominance)
- ADR 0007 (complexity boundaries)
- ADR 0008 (miner attestations)
- `INVARIANTS.md` I1, I7, I9

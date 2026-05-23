# ADR 0008: Miner Attestations and Resource Exhaustion Governance

**Status:** Accepted  
**Date:** 2026-05-23  
**Doctrine references:** P1, P2, P3, P5, P9, CP4, CP8, CP9, CP10  

---

## Context

As the Retrieval Fabric and Epistemic Memory (Atlas) scale to handle massive, multi-module repositories, they introduce two critical security and operational vulnerabilities that cannot be resolved by standard agent prompts:

1.  **Silent Context Poisoning (T2, T3):** Retrieval Fabric miners extract structured information from untrusted code, directories, and files. If an attacker plants a malicious prompt injection inside a codebase (e.g., in a comment or test file), a naive miner will extract and return it as raw text. If this text is ingested by Hermes without verification, it triggers privilege escalation. To prevent this, every miner report must carry a cryptographically signed manifest detailing its origin, scope, and hashes—ensuring full lineage audibility.
2.  **Probabilistic Denial of Service (DoS):** AI models operating under prompt injection, plan drift, or recursive loops will naturally trigger infinite loops. They may request endless file searches, trigger massive graph-traversal storms across Atlas, or inflate the context window with repetitive files. This rapidly drains API token budgets, locks up memory, and spikes operational costs. We need hard, deterministic resource ceilings enforced at the Sentinel level that cannot be overridden by model cognition.

---

## Decision

We permanently codify **Miner Attestations** and **Resource Exhaustion Ceilings** as deterministic constraints in the Hermes Prime control plane.

### 1. Cryptographic Miner Attestation Schema

Every Retrieval Fabric miner report must carry a structured, cryptographically signed manifest before its content is allowed to cross the Sentinel boundary into Hermes's prompt context. 

The Sentinel execution block will validate this manifest against the miner's public key (derived and held in Vault). The schema is defined as follows:

```yaml
attestation:
  attestation_id: "urn:uuid:f81d4fae-7dec-11d0-a765-00a0c91e6bf6"
  miner_id: "miner:ast:typescript:v1.2.0"
  miner_type: "ast_miner"
  scan_time: "2026-05-23T06:45:00Z"
  scan_scope:
    root: "src/auth/"
    include: ["**/*.ts"]
    exclude: ["node_modules/", "dist/"]
  files_examined:
    - path: "src/auth/login.ts"
      hash: "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
      size_bytes: 4096
  parser_metadata:
    parser: "tree-sitter-typescript"
    version: "v0.20.0"
  confidence_score: 0.98
  content_summary_hash: "sha256:8f4329a2741a... (hash of the actual returned structured report)"
  signature: "sig:ed25519:3b9a12cf8f921d... (signed by Vault-issued ephemeral miner key)"
```

**System Invariant:** Any retrieval report lacking a valid cryptographic signature, or whose content hash does not match the signature, is immediately quarantined. The requesting plan step is blocked and flagged as a potential injection event.

---

### 2. Resource Exhaustion Ceilings (Probabilistic DoS Protection)

Sentinel will deterministically intercept, monitor, and enforce strict, hardcoded limits on resource consumption. These limits live outside model context and are immune to prompt-based override.

| Resource Dimension | Hard Ceiling | Enforcement Action | Telemetry Metric |
| :--- | :--- | :--- | :--- |
| **Max Context Size** | 64K tokens per step | Truncate and alert | `sentinel.context.tokens` |
| **Session Token Quota** | 1,000,000 tokens | Pause & require operator re-auth | `sentinel.session.tokens_total` |
| **Graph Traversal Depth** | 100 relationship jumps | Terminate traversal, return partial | `atlas.graph.traversal_depth` |
| **Max Miner Runs** | 20 runs per Intent Root | Suspend dispatches; require user prompt | `fabric.dispatches.per_session` |
| **Concurrent Miner Dispatches** | 5 active miners | Queue dispatches in serial | `fabric.dispatches.concurrent` |

**System Invariant:** If a session breaches any of these ceilings, Sentinel places the active Hermes thread into a `SUSPENDED_BUDGET_EXHAUSTED` state. The user must explicitly authorize a budget extension; the agent cannot self-authorize.

---

## Alternatives Considered

### A. Non-Signed Miner Reports (Naive Ingestion)
*   *Why Proposed:* Reduces CPU hashing overhead and simplifies development.
*   *Why Rejected:* Leaves the system highly vulnerable to prompt-poisoning attacks. Without a signed manifest, we cannot verify that a miner report was not intercepted, altered, or forged by a malicious third-party process during execution.

### B. Dynamic Model-Managed Resource Budgets
*   *Why Proposed:* Allows the model to request more context or runs if it determines a task is highly complex.
*   *Why Rejected:* Under an active prompt-injection attack or planning loop, the model will always request maximum resources to fulfill its injected objective. Giving the probabilistic planner authority over resource ceilings destroys the constraint.

---

## Consequences

### Positive
- **Tamper-Evident Ingestion:** Any attempt to manipulate codebase search reports or plant injections in miner outputs is immediately detected at the Sentinel signature boundary.
- **Budget Protection:** Runs are capped deterministically, protecting developers and organizations from catastrophic, runaway API cost storms.
- **Forensic Traceability:** Attestation hashes map exactly to git commit states, allowing instant reconstruction of the exact code state the agent reasoned over during an incident.

### Negative
- **Computational Overhead:** Miner runs incur a small cryptographic hashing cost (fractions of a millisecond) for signing and verifying manifests.
- **Friction on Massive Tasks:** Legitimate operations on extremely large, complex planning steps might hit the Max Miner or Token ceilings, interrupting the developer for budget approvals.

---

## References

- ADR 0001: Split-Trust Subsystem Architecture
- ADR 0002: Deterministic Sentinel Dominance
- ADR 0004: Capability Tokens
- ADR 0007: Codifying Foundational Primitives and Complexity Boundaries
- Doctrine §4 (Memory), §5 (Execution), §8 (Human Interaction), §10.4 (Correlated Stochastic Failure)

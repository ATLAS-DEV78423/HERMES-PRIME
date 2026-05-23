# Capability and Secret Invariants

This document codifies the safety invariants governing credential containment, capability tokens, routing quality floors, observability hygiene, and resource ceilings.

---

## I3. Secrets never enter model context

*   **ID:** `I3`
*   **Statement:** No plaintext secret, partial secret, or secret-adjacent metadata may appear in any LLM prompt, completion, embedding input, vector store, log, trace, or telemetry stream.
*   **Rationale:** Doctrine P4. Structural isolation beats reactive detection.
*   **Enforcement:** All paths from Vault to other subsystems emit capability references, never raw secrets. Decrypted secrets exist only inside Forge execution sandboxes, in zeroizable buffers, with explicit lifetime.
*   **Detection:** Pre-submit and runtime entropy/regex scanners on all outbound payloads to model providers and observability stores. Tamper-evident alarm on any match.
*   **Response:** Outbound payload blocked, session quarantined, affected secrets immediately revoked, incident response triggered.
*   **Test:** CI: synthetic secret canaries injected into vault; assertion that none ever appear in any non-Forge subsystem. Runtime: continuous canary checks.

---

## I4. Capability tokens are short-lived and scoped

*   **ID:** `I4`
*   **Statement:** No capability token may have a TTL greater than its risk tier's maximum, and no token's scope may exceed the minimum required for its declared action.
*   **Rationale:** Doctrine §3.3. Blast radius bounding.
*   **Enforcement:** Vault refuses to mint tokens that violate TTL or scope policy. Defaults are aggressive; broader scopes require explicit override with justification logged.
*   **Detection:** Metric on token minting: `vault.token.ttl_seconds`, `vault.token.scope_breadth`. Alarms on outliers.
*   **Response:** Mint rejected. Repeated rejection patterns escalate to operator review.
*   **Test:** Unit tests on Vault enforce TTL and scope policy; chaos test attempts to mint over-broad tokens and asserts rejection.

---

## I10. Quality floors are enforced on routing

*   **ID:** `I10`
*   **Statement:** The model router may not select a model whose evaluated quality on the task class falls below the configured floor, regardless of cost or latency optimization.
*   **Rationale:** Doctrine §6.1. Silent quality degradation is cognition degradation infrastructure.
*   **Enforcement:** Router selection function is constrained: `argmin(cost) subject to quality >= floor`. Floor values come from a versioned evaluation suite.
*   **Detection:** Metric on selections: `router.floor_violations` (should always be zero). Periodic re-evaluation of quality scores per model version.
*   **Response:** Selection that would violate floor falls back to a higher-quality model. Operator alerted if floor cannot be met by any available model.
*   **Test:** Unit tests assert constraint behavior. Periodic evaluation refreshes floor data.

---

## I12. Observability respects redaction at write time

*   **ID:** `I12`
*   **Statement:** No log, trace, or telemetry record is persisted without first passing through the redaction layer.
*   **Rationale:** Doctrine P5. Observability is a threat surface.
*   **Enforcement:** All logging clients route through a redaction wrapper. Direct writes to observability stores are not exposed in the standard library and are blocked by static analysis.
*   **Detection:** Static analysis at PR time. Runtime canary tests inject synthetic secrets into log paths and assert redaction.
*   **Response:** Build fails on direct-write detection. Runtime canary failure quarantines the log path.
*   **Test:** Continuous canary injection in non-production environments. Static analysis in CI.

---

## I18. Deterministic Resource Ceilings (Probabilistic DoS Control)

*   **ID:** `I18`
*   **Statement:** Every execution path must operate under deterministic, Sentinel-enforced quotas: maximum 64K tokens per prompt context, maximum 100 graph traversals in Atlas, maximum 20 Retrieval Fabric miner dispatches per high-level Intent Root, and a maximum total session budget of 1,000,000 reasoning tokens.
*   **Rationale:** Doctrine §10, ADR 0008. Prevents economic exhaustion attacks (runaway retrieval loops, graph query explosions, context size amplification).
*   **Enforcement:** Sentinel tracks and intercepts active resource usage. Ceilings are hardcoded outside model context. Attempts to exceed allocations cause execution to immediately suspend.
*   **Detection:** Metric `sentinel.ceiling.context_size`, `sentinel.ceiling.graph_jumps`, and `sentinel.ceiling.miner_dispatches`.
*   **Response:** Subsystem suspended in a `SUSPENDED_BUDGET_EXHAUSTED` state. The user must manually approve resource quota extensions.
*   **Test:** Unit tests verify that simulated infinite planning loops are intercepted and blocked at the hard ceiling.

# Execution Invariants

This document codifies the deterministic safety invariants that govern execution and capability routing in the active control plane.

---

## I1. No model authority over invariants

*   **ID:** `I1`
*   **Statement:** No probabilistic component may produce the final decision that authorizes a privileged action, mutates Sentinel policy, modifies an audit log, or releases a secret.
*   **Rationale:** Doctrine P1. Probabilistic authority over invariants destroys them under prompt injection.
*   **Enforcement:** All blocking decision points are implemented in deterministic code paths with no LLM call in the critical section. Code review enforces this.
*   **Detection:** Static analysis flags any LLM client invocation reachable from a function annotated `@deterministic_boundary`.
*   **Response:** Build fails. PR rejected.
*   **Test:** CI: AST scan for forbidden call patterns. Runtime: trace assertion that blocking decisions complete without model RPC.

---

## I9. Capability registry is exhaustive

*   **ID:** `I9`
*   **Statement:** Forge executes only actions present in the capability registry. Tools, parameters, and action signatures not in the registry are rejected, regardless of how plausibly the request is phrased.
*   **Rationale:** Doctrine §5.4. Hallucinated actions cannot exist if the executor has no way to perform them.
*   **Enforcement:** Forge dispatches on registry lookup. Unknown actions return a typed rejection.
*   **Detection:** Metric `forge.unknown_action_attempts`. High rates indicate either an attack or a missing registry entry.
*   **Response:** Action rejected. Attempt logged. If pattern indicates legitimate need, registry update goes through normal review.
*   **Test:** Unit tests confirm dispatch behavior for known and unknown actions.

---

## I13. Consent prompts are generated from structured data

*   **ID:** `I13`
*   **Statement:** Every user-facing consent prompt is rendered from a typed structured request (action, capability, scope, duration, derived reason). Model-generated free-text consent prompts are forbidden.
*   **Rationale:** Doctrine §8.2. A model-written consent prompt is a model-controlled trust surface.
*   **Enforcement:** Consent surface accepts only structured payloads. Free-text overrides are not exposed.
*   **Detection:** Static analysis. Runtime validation of consent payload schema.
*   **Response:** Malformed consent request is rejected; action is blocked.
*   **Test:** Unit tests assert consent surface behavior. Integration tests verify rendering pipeline.

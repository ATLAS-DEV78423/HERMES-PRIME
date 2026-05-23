# Rollback and Transaction Invariants

This document codifies the safety invariants that govern transactional boundaries, reversibility, and revocation propagation.

---

## I8. Irreversible actions require explicit consent

*   **ID:** `I8`
*   **Statement:** No irreversible external action (deletion, deployment, financial transaction, broadcast communication) executes without per-action user consent referencing the specific action and its scope.
*   **Rationale:** Doctrine §5.2, §8.1. Reversibility is the difference between an error and a disaster.
*   **Enforcement:** Forge classifies every action by reversibility. Irreversible actions require a consent token issued within a short window for that specific action signature.
*   **Detection:** Forge logs every irreversible-action attempt with consent token reference. Missing or mismatched token blocks execution.
*   **Response:** Action blocked. User prompted (if interactive) or operator alerted (if not).
*   **Test:** Integration tests exercise irreversible action paths with valid, missing, expired, and mismatched consent tokens.

---

## I14. Revocation propagates within bounded time

*   **ID:** `I14`
*   **Statement:** When a capability is revoked, propagation to all enforcement points completes within the revocation SLA (target: 5 seconds; hard maximum: 30 seconds).
*   **Rationale:** Slow revocation is no revocation. Compromise windows must be bounded.
*   **Enforcement:** Revocation is broadcast on a dedicated channel; all consumers acknowledge. Forge consults a short-lived authorization cache only.
*   **Detection:** Metric `revocation.propagation_latency_p99`. Alarm on SLA breach.
*   **Response:** Operator alerted. Forge enters conservative mode (higher consent thresholds) until propagation is healthy.
*   **Test:** Chaos test: revoke a capability mid-execution and assert that subsequent uses fail within the SLA.

---

## I17. Automatic Transaction Journaling and Pre-Commit Rollback

*   **ID:** `I17`
*   **Statement:** Every mutating file, git, or command operation executed by Forge must operate inside a transactional envelope that snapshots the targeted state, journals modifications, and enforces automatic rollback if post-execution schema lints or compilation checks fail.
*   **Rationale:** Doctrine §5.2, ADR 0007. Prevents model hallucinations or broken scripts from corrupting active project files.
*   **Enforcement:** Forge wraps mutations in transactional blocks (using filesystem overlays or git worktree isolation). Pre-commit hooks run automated lints and tests. A fail status immediately reverts the state.
*   **Detection:** Metric `forge.transaction.rollbacks` and `forge.transaction.commits`.
*   **Response:** Mutation rejected, filesystem rolled back to pre-transaction snapshot, error journaled.
*   **Test:** Unit tests verify that introducing compile errors or invalid schemas causes Forge to automatically restore files to their pristine state.

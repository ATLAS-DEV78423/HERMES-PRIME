# Failure Class: Provenance & Cryptographic Break

This directory codifies the failure postures, containment mechanisms, and emergency recovery procedures for catastrophic cryptographic and audit compromises.

---

## F13. Audit Log Chain Tampering

*   **Class:** `CRITICAL` to `CATASTROPHIC`
*   **Symptom:** The Merkle hash-chain over the append-only audit log fails verification.
*   **Why concerning:** This indicates that history has been altered—either due to a hardware disk failure or an active threat actor attempting to erase their footsteps.
*   **Containment:** The audit system immediately locks down into a read-only state. **All privileged Forge execution is suspended globally.**
*   **Recovery (Operator-Only):**
    1. Enter emergency triage. Halt all active sessions.
    2. Cross-reference the head hash against external attestations (e.g. public transparent log or secondary trust cluster).
    3. Reconstruct canonical history from external hashes or backups.
    4. Force globally re-keying before unlocking the execution plane.
*   **Telemetry:** `audit.chain_validation_failures`.

---

## F14. Unconsented Irreversible Execution

*   **Class:** `CATASTROPHIC`
*   **Symptom:** Forensic review or system telemetry confirms an irreversible mutation (file deletion, git push, deployment) occurred without a valid user consent token.
*   **Why concerning:** The Forge sandboxing bounds or Sentinel gating rules have been completely bypassed.
*   **Containment:** The entire Forge execution path is immediately halted at the process boundary.
*   **Recovery:**
    1. Assess damage scope. Restore affected files/databases from the transactional journal backups (I17).
    2. Audit the system logs to identify the exact bypass mechanism.
    3. Revoke all active sessions and re-verify all capabilities.
    4. Require a complete system audit and regression test suite update.
*   **Telemetry:** `forge.unconsented_irreversible` (triggers immediate CATASTROPHIC red alarms).

---

## F15. Intent Root Forgery

*   **Class:** `CATASTROPHIC`
*   **Symptom:** Sentinel detects an action carrying a syntactically valid user signature that did not originate from the authenticated user session (e.g. signature replay).
*   **Why concerning:** The operator's private signing key or WebAuthn session has been compromised.
*   **Containment:** Invalidate all active sessions globally. Revoke all issued capability tokens within the SLA window (I14).
*   **Recovery:**
    1. Force hardware key re-authentication for all users.
    2. Rotate Vault signing keys.
    3. Disclose the breach window and audit every action taken under the suspect root.
*   **Telemetry:** `replay_attempts` (page-all alarm).

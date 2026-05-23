# Provenance Invariants

This document codifies the cryptographic and intent lineage safety invariants that secure the supply chain of cognitive operations.

---

## I2. Intent root required for privileged actions

*   **ID:** `I2`
*   **Statement:** Every action above the lowest risk tier must reference a valid, unexpired, user-signed intent root, and the action's declared scope must be a subset of the intent root's scope.
*   **Rationale:** Doctrine P3. Authorization without provenance is theater.
*   **Enforcement:** Sentinel rejects any capability request lacking a verifiable intent root or whose scope exceeds the root's scope.
*   **Detection:** Capability minting path logs any rejection with reason; metric `sentinel.intent_root_missing` and `sentinel.intent_scope_violation`.
*   **Response:** Action blocked, audit entry written, user notified if pattern repeats.
*   **Test:** Integration test suite includes negative cases for missing root, expired root, scope-exceeding requests.

---

## I5. Audit log is append-only and tamper-evident

*   **ID:** `I5`
*   **Statement:** The audit log accepts only appends, and every entry is cryptographically chained to the previous entry such that any modification is detectable.
*   **Rationale:** Doctrine §7.2. Without integrity here, forensic recovery is impossible.
*   **Enforcement:** Hash-chain (Merkle structure) over audit entries. Storage layer rejects writes that do not extend the current head. Periodic external attestation of the head hash.
*   **Detection:** Chain validation runs on every append and on scheduled intervals. Any break triggers immediate alarm.
*   **Response:** Audit subsystem enters read-only mode. Operator intervention required. All privileged operations suspended until chain integrity is restored.
*   **Test:** CI: tampering with a historical entry must cause chain validation to fail. Runtime: continuous chain validation.

---

## I15. Doctrine principles are referenced in code

*   **ID:** `I15`
*   **Statement:** Any code implementing a doctrine principle or enforcing an invariant carries an explicit reference to the principle/invariant ID in comments and is discoverable via grep.
*   **Rationale:** Architectural causality must survive personnel changes. Six months from now, someone needs to know *why* a check exists.
*   **Enforcement:** Code review checklist. PR template asks "which principle/invariant does this implement?"
*   **Detection:** Periodic audit: grep for principle and invariant IDs; cross-reference with documented enforcement claims.
*   **Response:** Drift identified; either code or documentation is updated.
*   **Test:** Documentation linter cross-references this file's "Enforcement" entries with code annotations.

---

## I16. Cryptographic Miner Attestation required for Ingestion

*   **ID:** `I16`
*   **Statement:** Every structured search or parsing report emitted by the Retrieval Fabric must carry a cryptographically signed manifest (containing UUID, timestamp, scope, file hashes, and Ed25519 signature) before it can be ingested into Hermes prompt context.
*   **Rationale:** Doctrine CP9, ADR 0008. Prevents context-poisoning attacks from untrusted codebase content.
*   **Enforcement:** Sentinel intercepts all Retrieval Fabric inputs at the prompt injection boundary. Unsigned or invalid manifests fail closed, blocking context ingestion.
*   **Detection:** Metric `sentinel.attestation.failures` and `sentinel.attestation.forgeries`.
*   **Response:** Ingestion blocked. Planning step halted and re-routed. Potential threat telemetry alert.
*   **Test:** Integration tests verify Sentinel rejects modified search payloads or expired signatures.

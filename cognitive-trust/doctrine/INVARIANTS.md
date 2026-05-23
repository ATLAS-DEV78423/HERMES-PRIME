# Cognitive Trust Invariants

**Status:** Living document
**Companion to:** `DOCTRINE.md`, `THREAT_MODEL.md`
**Purpose:** Testable, enforceable, monitorable constraints that must hold in any Cognitive Trust deployment.

These extend the Hermes invariants. They do not override them.

---

## CT-I1. The main agent never signs

**Statement.** No process running the main reasoning model has direct access to signing keys, signing oracles, or attestation issuance.

**Enforcement.** Signing keys live exclusively in the PKI attestation service, backed by KMS/HSM. The main agent's IAM role grants `attestation.request` but never `signing.execute`. Static analysis on agent runtime configuration confirms.

**Test.** Attempt to sign from the main agent process. Must fail with `not_authorized`.

---

## CT-I2. Every artifact attestation chains to an intent root

**Statement.** No artifact attestation is issued without a reference to a valid, unexpired, signed intent root whose scope covers the artifact class.

**Enforcement.** Attestation service rejects requests missing `intent_root_ref` or with scope mismatch. Verification re-validates the chain on read.

**Test.** Request attestation without intent root → denied. Request attestation with expired intent root → denied. Request attestation with out-of-scope intent root → denied.

---

## CT-I3. Miners do not mutate

**Statement.** No miner process has write access to the workspace, the audit log, the attestation service, the PKI, or any persistent store other than its own ephemeral working directory.

**Enforcement.** OS-level sandbox: read-only mounts for the workspace; no write access to audit/PKI sockets; ephemeral tmpfs for working data.

**Test.** Attempt write from miner process to any monitored path. Must fail.

---

## CT-I4. Attestations include content hashes

**Statement.** Every attestation that references content includes a cryptographic hash of that content. Verification recomputes and compares.

**Enforcement.** Attestation schema mandates `subject_hashes` field. Attestation service refuses to sign without it.

**Test.** Issue attestation; modify referenced content; verification must fail.

---

## CT-I5. Revocation propagates within SLA

**Statement.** When an attestation is revoked, all derivative attestations are marked `derivative_revoked` within 60 seconds. Verifiers checking those derivatives receive the revoked status.

**Enforcement.** Revocation cascade is implemented as an async job that walks the lineage graph from the revoked node. Online verification consults the revocation index on every check.

**Test.** Revoke a foundational attestation; check derivative within 60s; status must reflect revocation.

---

## CT-I6. Miner reports are themselves attested

**Statement.** Every miner report carries a `retrieval_attestation` signed by the Fabric dispatcher. The attestation includes the miner class, task, parameters, scope, content hashes of every file read, and the report's own hash.

**Enforcement.** Dispatcher refuses to release reports without attestation. Receivers reject reports with missing or invalid attestation.

**Test.** Construct unattested report; attempt to consume; must fail.

---

## CT-I7. Attestation service is deterministic

**Statement.** No LLM is in the critical path of attestation issuance, revocation, or verification.

**Enforcement.** Static analysis on the attestation service codebase. Forbidden imports list includes any LLM SDK in service-critical modules.

**Test.** CI build fails if forbidden import detected in service-critical path.

---

## CT-I8. Trust tier governs ceremony

**Statement.** Each artifact class has a declared trust tier. The attestation service refuses to issue attestations whose ceremony does not match the tier's requirements (signing material, witnesses, cooldowns, multi-party approval).

**Enforcement.** Tier-requirements table is loaded at service start and validated. Per-request tier check is deterministic.

**Test.** Request a Tier-5 attestation with single-party signature → denied. Request Tier-1 attestation with full ceremony → accepted (over-ceremony allowed; under-ceremony forbidden).

---

## CT-I9. Lineage is acyclic and append-only

**Statement.** The attestation lineage graph is a DAG. Once an attestation is issued, its references to predecessors are immutable. New attestations may reference existing ones; existing attestations cannot retroactively change their references.

**Enforcement.** Storage layer rejects mutations to existing attestation records. Insertion validates DAG property.

**Test.** Insert cycle → rejected. Mutate existing attestation reference list → rejected.

---

## CT-I10. Reviewer attestations are personally signed

**Statement.** When a human reviewer marks an artifact as reviewed, the resulting reviewer attestation is signed with the reviewer's personal key (WebAuthn / hardware token / KMS-backed personal key), not a shared service key.

**Enforcement.** Attestation service distinguishes service signatures from personal signatures by certificate chain. Reviewer attestation schema requires personal-cert chain.

**Test.** Attempt reviewer attestation with service key → denied. Personal-key reviewer attestation succeeds and verifies under the personal cert chain.

---

## CT-I11. Audit log is append-only and hash-chained

**Statement.** All attestation issuance, revocation, verification, miner dispatches, and miner reports are appended to a tamper-evident log (Merkle-chained or equivalent).

**Enforcement.** Storage rejects modifications; chain validation runs on every append and on schedule. (Inherits and extends Hermes I5.)

**Test.** Tamper with historical entry; chain validation must fail.

---

## CT-I12. Miner budgets are policy-bounded

**Statement.** No miner dispatch exceeds the per-class TTL, max-files, max-results, or token-budget caps declared at dispatcher startup. Caps cannot be raised by request; only lowered.

**Enforcement.** Dispatcher clamps requested budget against class cap before dispatch.

**Test.** Request exceeding cap; effective budget must equal cap, not request.

---

## CT-I13. Verification is constant-time on cached chains

**Statement.** Verification of a previously-verified, unmodified, unrevoked artifact returns in O(1) time using the verification cache, not by re-walking the chain.

**Enforcement.** Verification cache keyed by `(artifact_hash, latest_revocation_index_version)`. Invalidation on revocation index update.

**Test.** Verify artifact twice; second verification < 5ms.

**Rationale.** Verification cost matters because verification is run constantly. If it's expensive, callers skip it.

---

## CT-I14. Repo knowledge graph entries carry source attestations

**Statement.** Every node and edge in the repo knowledge graph carries a reference to the miner attestation that produced it. Graph queries can produce evidence chains.

**Enforcement.** Graph schema mandates `source_attestation` field on every node/edge.

**Test.** Query graph; verify every result has traceable source attestation.

---

## CT-I15. Miner LLM use is explicit and tagged

**Statement.** Any miner that uses an LLM in its computation must tag its report with `llm_used: true`, the model identifier, and the prompt template hash. Reports from LLM-using miners are flagged as `probabilistic_input` to downstream consumers.

**Enforcement.** Schema mandates these fields when `llm_used = true`. Validator rejects reports claiming `llm_used: false` from miners registered as LLM-using.

**Test.** LLM miner returns report without flag → rejected. Report with flag flows downstream with `probabilistic_input` propagated.

---

## Reserved IDs

Future invariants take the next available CT-I number. Retired invariants are kept with retirement date and reason.

---

## Retired Invariants

*(none yet)*

# Cognitive Trust Threat Model

**Status:** Living document
**Companion to:** `DOCTRINE.md`, `INVARIANTS.md`
**Purpose:** Enumerate adversaries against the Retrieval Fabric and the Cognitive PKI, the assets defended, and the deterministic/probabilistic mitigations in place.

Extends `hermes/THREAT_MODEL.md`. Hermes threats still apply; this document adds threats specific to the trust infrastructure.

---

## Assets

| ID | Asset | Why it matters |
|----|-------|---------------|
| CT-AS1 | Signing keys | Compromise = unlimited forged provenance |
| CT-AS2 | Attestation lineage graph | The audit trail; corruption destroys retroactive trust |
| CT-AS3 | Repo knowledge graph | Poisoned graph misleads every future query |
| CT-AS4 | Reviewer personal credentials | Misuse fakes human approval |
| CT-AS5 | Revocation index | If untrusted, revoked attestations appear valid |
| CT-AS6 | Miner sandbox boundary | Escape leaks workspace data or executes code |
| CT-AS7 | Intent root binding | Breaking the bind detaches actions from user intent |

---

## Adversary classes

### CT-AC1 — Forged provenance attacker
Tries to issue an attestation without legitimate authority — directly bypassing the attestation service or impersonating it.

### CT-AC2 — Lineage tamperer
Tries to modify or delete historical attestation records to rewrite the trust chain.

### CT-AC3 — Revocation suppressor
Tries to prevent revocation from propagating, keeping invalidated attestations appearing valid.

### CT-AC4 — Repo graph poisoner
Tries to inject false facts into the repo knowledge graph (similar to Hermes patient-poisoning class T4 but specifically targeting graph entries).

### CT-AC5 — Reviewer impersonator
Tries to forge a reviewer attestation, faking human approval.

### CT-AC6 — Miner injection vector
Tries to plant content that, when read by an LLM-based miner, produces misleading summaries or graph edges (a refrlow T-R2 / T-R3 analog at the graph layer).

### CT-AC7 — Stale-input replayer
Tries to feed an old (still-valid-signature, but stale) miner attestation to mislead a current artifact generation.

### CT-AC8 — Verification cache poisoner
Tries to insert a false cached verification result that bypasses real signature checks.

### CT-AC9 — Tier downgrader
Tries to issue a high-stakes artifact under a low-stakes tier's ceremony.

### CT-AC10 — Compromised generating model
The model itself produces malicious output (deliberately or via injection) and gets it attested as legitimate.

---

## Threat matrix

### CT-T1. Forged attestation issuance
**Adversary:** CT-AC1
**Asset:** CT-AS1, CT-AS2
**Defends by:** CP4, CT-I1, CT-I7

| Layer | Mitigation |
|-------|-----------|
| D | Signing keys live only in KMS/HSM; attestation service is the only client |
| D | Attestation service authenticates requesters via mTLS + workload identity |
| D | Attestation service code path has no LLM (CT-I7) |
| D | Attestations include service identity in their certificate chain |
| R | Service-level compromise. Mitigated by isolation, monitoring, signed code |

---

### CT-T2. Lineage tampering
**Adversary:** CT-AC2
**Asset:** CT-AS2
**Defends by:** CT-I9, CT-I11

| Layer | Mitigation |
|-------|-----------|
| D | Lineage storage is append-only at the storage layer (DB-level enforcement, not just app-level) |
| D | Hash-chained audit log (Merkle); modifications detectable on validation |
| D | Periodic external attestation of audit log head hash |
| D | DAG insertion validates predecessors are immutable |
| R | Coordinated insider tampering across audit + storage. Mitigated by split-trust admin roles |

---

### CT-T3. Revocation suppression
**Adversary:** CT-AC3
**Asset:** CT-AS5
**Defends by:** CT-I5, CT-I13

| Layer | Mitigation |
|-------|-----------|
| D | Revocation index is a separately-signed monotonic counter; verification clients refuse to proceed if counter older than 60s |
| D | Online verification consults the revocation index, not just cached attestations |
| D | Revocation propagation cascade is audited; gaps trigger alarm |
| R | Network partition between verifier and revocation service. Fail-closed: verifier refuses to validate if revocation index unreachable beyond SLA |

---

### CT-T4. Repo graph poisoning
**Adversary:** CT-AC4
**Asset:** CT-AS3
**Defends by:** CT-I14

| Layer | Mitigation |
|-------|-----------|
| D | Every graph node/edge carries source attestation; queries can produce evidence |
| D | Graph entries from LLM-using miners are flagged `probabilistic_input` |
| D | Periodic integrity sweep: re-derive sampled graph entries from source; compare |
| D | Source-based revocation: if a miner attestation is revoked, derived graph entries are quarantined |
| P | Anomaly detection on graph update patterns (mass updates from single source) |
| R | Slow drift via many small corroborating poisoned inputs (Hermes T4 class). Substantially unresolved |

---

### CT-T5. Reviewer impersonation
**Adversary:** CT-AC5
**Asset:** CT-AS4
**Defends by:** CT-I10

| Layer | Mitigation |
|-------|-----------|
| D | Reviewer attestations require personal key (WebAuthn / hardware token / KMS-personal-key) |
| D | Personal key cert chain distinguishable from service cert chain at verification |
| D | Reviewer attestation operations require fresh authentication (no long-lived session can mint a reviewer attestation) |
| D | High-tier reviews require additional factor (e.g., second reviewer attestation from a different person) |
| R | Reviewer device compromise. Mitigated by short-lived attestations and revocation |

---

### CT-T6. Miner injection producing misleading attestations
**Adversary:** CT-AC6
**Asset:** CT-AS3, downstream artifacts
**Defends by:** CT-I15

| Layer | Mitigation |
|-------|-----------|
| D | Deterministic miners are preferred; LLM miners are minority |
| D | LLM miner reports tagged `probabilistic_input`; downstream consumers know |
| D | LLM miners use a model family different from the main agent (defeats correlated injection) |
| D | Miner system prompt explicitly forbids producing imperatives; injection-pattern scanner on output |
| D | Content hashes in attestation: tampering with source after attestation breaks verification |
| P | Spot-check sampling: re-derive a small fraction of LLM miner outputs deterministically; flag disagreements |
| R | Subtle semantic injection that passes scanners. Mitigation: defense in depth at artifact generation stage |

---

### CT-T7. Stale input replay
**Adversary:** CT-AC7
**Asset:** Current artifact integrity
**Defends by:** Freshness requirements per tier

| Layer | Mitigation |
|-------|-----------|
| D | Miner attestations include TTLs; expired attestations rejected at artifact generation |
| D | High-tier artifact generation requires input attestations within a freshness window (configurable per tier) |
| D | Content hashes detect if source changed since miner attestation |
| R | Replay within freshness window. Acceptable for tiers below "irreversible" |

---

### CT-T8. Verification cache poisoning
**Adversary:** CT-AC8
**Asset:** CT-AS2
**Defends by:** CT-I13

| Layer | Mitigation |
|-------|-----------|
| D | Verification cache keyed by `(artifact_hash, revocation_index_version)`; index version changes invalidate |
| D | Cache writes only from the verification service itself; no external write path |
| D | Periodic cache scrub: re-verify random sample, alarm on disagreement |
| D | Cache entries cryptographically signed; reads validate signature |
| R | Cache service compromise. Mitigated by service isolation and signed entries |

---

### CT-T9. Tier downgrade
**Adversary:** CT-AC9
**Asset:** Tier integrity
**Defends by:** CT-I8

| Layer | Mitigation |
|-------|-----------|
| D | Artifact class → tier mapping is policy data, not request data |
| D | Attestation service derives tier from artifact class, ignores request-supplied tier hints |
| D | Tier-requirements table is signed and externally attested; tampering detectable |
| R | Policy mis-classification (an artifact class registered in the wrong tier). Mitigated by tier registration review process |

---

### CT-T10. Compromised generating model produces malicious output
**Adversary:** CT-AC10
**Asset:** Downstream consumers of artifacts
**Defends by:** Layered review

| Layer | Mitigation |
|-------|-----------|
| D | Attestation captures model identity and version; downstream consumers can refuse artifacts from deprecated models |
| D | Risk tier determines whether human review is required pre-execution |
| D | Reviewer attestations are personal-signed (CT-I10); reviewer is on record |
| D | Sandbox at execution time provides backstop regardless of artifact quality |
| P | Optional second-model adversarial review for high-tier artifacts |
| R | Model is doing the malicious thing in a way no reviewer catches. Substantially unresolved; mitigated by execution-time sandboxing and reversibility tiers |

---

## Cross-threat compositions

### CT-CP1. Repo graph poisoning + tier downgrade
Attacker poisons graph entries that an artifact generator depends on, AND manages to get the resulting artifact registered as a lower tier than warranted. Now poisoned cognition produces under-reviewed output.

**Defense:** Tier mapping is policy-driven, not artifact-content-driven. Graph entries with `probabilistic_input` flag propagate that flag to artifacts that consume them; artifacts derived from probabilistic inputs cannot be auto-downgraded.

### CT-CP2. Reviewer impersonation + stale input replay
Attacker forges a reviewer attestation and pairs it with a stale miner attestation, presenting it as a "freshly reviewed" artifact.

**Defense:** Reviewer attestations include a `reviewed_at` timestamp that must be within a tight window of the artifact's input attestations. Mismatched timestamps trigger verification failure.

### CT-CP3. Revocation suppressor + cache poisoner
Attacker prevents revocation propagation AND injects positive cached verification results.

**Defense:** Online verification consults the revocation index even on cache hit. Index version changes invalidate cache. Defense in depth: both mitigations must fail simultaneously.

---

## Threats explicitly out of scope

- **OS-level compromise of the KMS/HSM appliance.** Delegated to the KMS operator.
- **Cryptanalysis of the signing algorithm.** Assumed sound for the foreseeable future.
- **User coercion to sign intent roots.** Out of scope.
- **Side-channel attacks on the attestation service hardware.** Mitigated by hardware vendor; not by Cognitive Trust.

---

## Posture summary

| Threat | Mitigation strength | Residual risk |
|--------|--------------------|--|
| CT-T1 Forged attestation | Strong | Low (service compromise) |
| CT-T2 Lineage tampering | Strong | Low (insider collusion) |
| CT-T3 Revocation suppression | Strong | Low–medium (network partition) |
| CT-T4 Graph poisoning | Medium | **Substantial (subtle drift)** |
| CT-T5 Reviewer impersonation | Strong | Low (device compromise) |
| CT-T6 Miner injection | Medium | Medium (semantic injection) |
| CT-T7 Stale replay | Strong | Low |
| CT-T8 Cache poisoning | Strong | Low |
| CT-T9 Tier downgrade | Strong | Low (policy mis-classification) |
| CT-T10 Compromised model | **Partial** | **Substantial — open problem** |

The two "substantial" residuals are the same shape: probabilistic infrastructure under sophisticated adversaries. The doctrine names these openly.

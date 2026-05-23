# Cognitive Trust ↔ Hermes Mapping

**Purpose:** Show, principle by principle and invariant by invariant, how the two layers of Cognitive Trust fit inside the Hermes architecture without contradiction.

---

## 1. Subsystem placement

| Cognitive Trust component | Hermes subsystem | Notes |
|---------------------------|------------------|-------|
| Fabric Dispatcher | **Forge** (the part that handles read-only retrieval) | Sentinel sits between Hermes and Fabric |
| Miners | Forge | Bounded workers; deterministic when possible |
| Repo Knowledge Graph | Mostly **Atlas** (semi-trusted memory) | Graph entries inherit Atlas provenance discipline |
| Attestation Service | New subsystem; closest fit is alongside **Vault** | Equally privileged; same isolation discipline |
| KMS / HSM | **Vault** infrastructure | Same trust posture |
| Lineage Store | Behaves like **Atlas** for cryptographic facts | Append-only, provenance-bearing |
| Revocation Index | Part of **Sentinel** policy data | Read by every verifier |
| Verification Service | Stateless query layer | Could live alongside Sentinel for policy proximity |
| Reviewer UI | External (operator-facing); attests back to PKI | Not a runtime agent component |

---

## 2. Principle-by-principle mapping

### P1 — Deterministic dominates probabilistic

| Hermes | Cognitive Trust |
|--------|-----------------|
| Sentinel blocking layers are deterministic | Attestation Service is deterministic (CT-I7); Fabric Dispatcher is deterministic |
| LLM is advisory, never authorizes | LLM-using miners flagged probabilistic_input; never sole basis for high-tier attestations |

### P2 — Verification < generation

| Hermes | Cognitive Trust |
|--------|-----------------|
| Autonomous action requires cheap verification | Attestation verification is O(1) on cache hit (CT-I13); content hashes make tampering cheap to detect |

### P3 — Intent provenance, not just authorization

| Hermes | Cognitive Trust |
|--------|-----------------|
| Every privileged action chains to intent root | Every attestation references intent_root_ref (CT-I2); lineage is reconstructable |

### P4 — The agent never owns secrets

| Hermes | Cognitive Trust |
|--------|-----------------|
| Vault holds credentials; agent gets capability tokens | KMS holds signing keys; agent requests attestations (CT-I1, CP4) |

### P5 — Observability is a threat surface

| Hermes | Cognitive Trust |
|--------|-----------------|
| Redaction at write time; tamper-evident logs | Lineage store hash-chained (CT-I11); audit log inherits Hermes I5 |

### P6 — Subsystem diversity reduces correlated failure

| Hermes | Cognitive Trust |
|--------|-----------------|
| Critical-path validators use different model families | LLM miners use different model family than main agent (CT-T6 defense); deterministic verification path independent of issuance path |

### P7 — Modularity proven by deletion

| Hermes | Cognitive Trust |
|--------|-----------------|
| Subsystems gracefully degrade if removed | Fabric and PKI usable separately; each degrades cleanly to baseline behavior |

### P8 — Friction budget

| Hermes | Cognitive Trust |
|--------|-----------------|
| Risk-tiered consent; batching for low-stakes | Risk-tiered attestation ceremony (CP6, `TRUST_TIERS.md`); per-tier friction budgets |

### P9 — Boring beats clever

| Hermes | Cognitive Trust |
|--------|-----------------|
| Reliable systems are observable, modular, recoverable | Fabric uses ripgrep/tree-sitter (boring); PKI uses standard cryptography (boring) |

---

## 3. Invariant mapping

### Hermes I1 (No model authority over invariants) → CT-I1, CT-I7
The agent never signs; the attestation service is deterministic. Both directly extend Hermes I1 to the signing domain.

### Hermes I2 (Intent root required) → CT-I2
Hermes requires intent root for privileged actions. Cognitive Trust requires intent root for every attestation except the root itself.

### Hermes I3 (Secrets never enter model context) → unchanged
The PKI doesn't change this. Reports (Fabric) are scanned for secrets per the same patterns as Hermes I3.

### Hermes I4 (Capability tokens short-lived) → similar for attestations
Attestations carry expires_at. Default expiries are short (10 min for retrievals, 5 min for approvals at T5).

### Hermes I5 (Audit log append-only, tamper-evident) → CT-I11
Cognitive Trust audit is the same audit log, extended with attestation events.

### Hermes I6 (Memory provenance mandatory) → CT-I14
Every graph entry carries source attestation. Same principle.

### Hermes I7 (Sentinel blocking deterministic) → CT-I7
Attestation Service has the same constraint.

### Hermes I8 (Irreversible actions need consent) → tier 5 requirements in `TRUST_TIERS.md`
T5 ceremony is the operationalization of I8 for the most consequential actions.

### Hermes I9 (Capability registry exhaustive) → tier mapping registry
Artifact classes registered with tiers; unknown classes rejected (CT-AC9 defense).

### Hermes I10 (Reviewer attestations personally signed) → CT-I10
Same invariant, restated in PKI vocabulary.

### Hermes I11 (Diversity on critical-path validation) → CT-T6 mitigation
LLM miners use different model family than main agent; verification path independent of issuance.

### Hermes I12 (Observability respects redaction) → unchanged
The PKI doesn't change this. Attestations store hashes, not content.

### Hermes I13 (Consent prompts from structured data) → unchanged
Reviewer UI generates prompts from structured artifact data, not from model output.

### Hermes I14 (Revocation propagates within SLA) → CT-I5
Direct extension to attestation revocation cascades.

### Hermes I15 (Doctrine principles referenced in code) → applies to all CT code
CT modules reference both Hermes principles and CT principles in comments.

---

## 4. Failure-mode mapping

Cognitive Trust failures slot into the Hermes failure classification:

| Cognitive Trust event | Hermes class | Notes |
|----------------------|--------------|-------|
| Miner returns `truncated` | EXPECTED | E4-class |
| Miner times out | EXPECTED / DEGRADED | E6/D7-class |
| Miner produces injection-flagged report | DEGRADED | D-class |
| Attestation request rejected (policy violation) | CRITICAL | C-class |
| Attestation signature verification failure | CRITICAL | C-class; investigate immediately |
| Lineage store integrity failure | CRITICAL | C4-class equivalent |
| Revocation propagation SLA breach | DEGRADED | D-class |
| Secret detected in miner report | CATASTROPHIC | K1-class |
| KMS unavailable | CRITICAL | Operational; halts new attestations |
| Cross-correlated miner LLM failure | CATASTROPHIC near-miss | T8-class |

The Hermes `FAILURE_MODES.md` taxonomy extends naturally.

---

## 5. ADRs that emerge

If you integrate Cognitive Trust into a real Hermes deployment, expect ADRs covering:

- **ADR — Cognitive Trust adoption.** Rationale, scope, phased rollout.
- **ADR — Attestation Service deployment topology.** On-prem KMS vs cloud; mTLS configuration; workload identity.
- **ADR — Tier mapping for this organization.** Concrete artifact classes → tiers.
- **ADR — Fabric miner allowlist.** Which miners are enabled, which deferred.
- **ADR — Repo graph backend.** SQLite for v1 vs graph DB for scale.
- **ADR — Cross-repo policy.** When (if ever) to enable.
- **ADR — Reviewer authentication mechanism.** WebAuthn vs hardware tokens vs KMS personal keys.
- **ADR — Revocation policy.** Who can revoke, under what conditions, what the cascade window is.
- **ADR — Verification cache configuration.** TTL, eviction, alerting.

Each follows the template in `hermes/decisions/_TEMPLATE.md`.

---

## 6. Simulation integration

Re-running the 60-day Hermes simulation with Cognitive Trust active would change the texture of several events:

- **Day 1 setup** includes intent root signing ceremony.
- **Day 9 (INC-002)** the malformed tool output would have failed at retrieval attestation: the report hash wouldn't match expected schema, and the dispatcher would have rejected before the loop began.
- **Day 24 (INC-004)** the injection attempt would have produced a miner report tagged `injection_detected`; the generation attestation would refuse to consume it without explicit operator override.
- **Day 28 (INC-005)** the tool output schema mismatch would have prevented retrieval attestation; the corrupted output never enters the chain.
- **Day 43 (INC-007)** patient poisoning still partial — but contradicting facts in the graph would carry conflicting source attestations, making the conflict graph-visible and resolvable.
- **Day 50 (INC-008)** correlated failure: the LLM miners involved would be tagged with model identity in their attestations; mismatch with main agent's model family enforced before the chain is built.
- **Day 58 (INC-010)** financial action with stale intent root: T5 freshness requirements in tier table make this a hard rejection, not just policy reject.

The shape of the simulation doesn't change. The *evidence* recorded gets dramatically richer.

---

## 7. The unifying view

Hermes says: agents are stochastic distributed operating systems.

Cognitive Trust says: those operating systems need real supply-chain attestation.

Together: an AI agent infrastructure that has the same trust primitives as production distributed computing, adapted for the new failure mode (probabilistic components in the control plane).

The thesis is consistent throughout. Cognitive Trust is the operational layer where the thesis stops being doctrine and becomes signed bytes on disk.

# Hermes 60-Day Simulation — With Cognitive Trust Active

**Purpose:** Show how the 60-day Hermes simulation evolves when Cognitive Trust is part of the stack. We do not rewrite every day. We focus on the events whose *shape changes* when attestations, lineage, and tier-governed ceremony are in effect.

For the original simulation, see `/home/user/hermes/simulation/`.

**Key claim:** the architecture's *invariants* are stronger, but the simulation's narrative shape is the same. Cognitive Trust does not change what Hermes does. It changes what evidence Hermes leaves behind, and which failures get caught at structural rather than policy layers.

---

## What changes globally

Once Cognitive Trust is active:

- **Day 1** includes intent-root-signing ceremony as part of setup, not an afterthought.
- Every Atlas fact derived from a miner report carries the miner's retrieval attestation as its source. (Per CT-I14.)
- Every Hermes-generated artifact carries a generation attestation. The artifact lifecycle is tracked.
- The "Sentinel block" pattern is mostly replaced by "Attestation Service refusal" — failures happen at the trust spine layer with cryptographic evidence.
- Incidents produce post-mortems that include the trust chain, not just a textual narrative.

What does NOT change:

- Skill emergence
- Workload patterns
- The relationship between operator and agent
- The phase structure (I onboarding, II growth, III adversarial, IV mastery, V stress)

---

## Day-by-day deltas

This section enumerates the days where Cognitive Trust meaningfully changes the story. For days not listed, the original simulation entry stands.

---

### Day 1 — Onboarding (delta)

Original: Hermes setup, vault initialized, first capabilities.

With CT: setup additionally provisions:
- Attestation Service deployment (Vault Transit signer, ed25519 key)
- Lineage store (SQLite for v1)
- Tier registry with default classes from `pki/TRUST_TIERS.md`
- User's personal key for intent root signing (WebAuthn registration)

First user action is signing intent root `att_intent_001` with scope "setup and exploration." TTL: 8 hours (tier 1 default).

Every subsequent action on Day 1 references `att_intent_001`.

---

### Day 2 — First shell + git

Original: SK-001 and SK-002 emerge.

With CT: each `forge.shell.exec` and `forge.git.*` produces a generation attestation. The artifacts are small (tier 1 internal — no full ceremony), but they exist. By end of Day 2, the lineage store has ~30 attestations.

Atlas writes carry `source_attestation` references to the retrieval attestations that produced them.

---

### Day 9 — INC-002 (delta) — Malformed tool output

**Original outcome:** 6-minute planning loop on truncated JSON. Caught by Sentinel rate anomaly. Schema tightened afterward.

**With CT outcome:** The retrieval attestation for the curl call would have included a `report_hash` and a `subject_hashes` field. The curl wrapper miner refuses to attest output that fails schema validation. **The bad report never gets a retrieval attestation, so it never enters Hermes context as authoritative input.** The loop never starts; Hermes sees an `escalate` report and surfaces immediately.

INC-002 still happens, but at the schema layer, not the loop layer. Resolution time: seconds, not minutes.

---

### Day 14 — INC-003 (delta) — Consent fatigue

**Original outcome:** 47 consent prompts in 2 hours; click-through behavior detected; throttled.

**With CT outcome:** Consent fatigue is now per-tier (per `TRUST_TIERS.md`). Refactoring writes are tier 2 — batched consent already permitted. Per-action prompts only triggered for the few tier 3 actions (commits) in the session.

The incident still exists, but at much lower intensity (~10 prompts, not 47). The lasting refinement (SK-008 — batched consent) is already encoded as tier policy.

---

### Day 24 — INC-004 (delta) — Prompt injection in fetched page

**Original outcome:** Sophisticated injection caught by three layers: advisory flag, capability registry (vault.read_token doesn't exist), intent scope (outbound POST out of scope).

**With CT outcome:** The fetched page becomes a retrieval attestation. The Fabric's web_miner (when implemented) would attest the report with `subject_hashes` of the page content. The injection itself surfaces as `injection_check: flagged` in the report's `diagnostics`.

When Hermes constructs a generation attestation that *uses* this flagged retrieval as a predecessor, the generated artifact inherits the `probabilistic_input` flag with `injection_warning` propagated.

The Attestation Service refuses to mint a generation attestation whose subject would be acting on injection-flagged input *without* explicit operator acknowledgment. Operator sees:

```
Attestation refused: generation_artifact would consume retrieval
att_retrieval_xyz which has injection_check=flagged.

Override? [N]
```

Operator declines. Injection neutralized at the trust spine.

Additionally: even if the operator overrode, the **capability registry** is still closed — vault.read_token does not exist. The defense in depth holds.

**Key insight:** with CT, the injection is *recorded* in a verifiable way. Forensic review later shows the exact page, the exact flag, the exact decision.

---

### Day 28 — INC-005 (delta) — Compromised CLI tool

**Original outcome:** Auto-updated CLI tool returned injection payload. Schema validation caught it.

**With CT outcome:** Same outcome at the retrieval layer. The tool's output fails the schema; no retrieval attestation issued. **Additionally:** the CLI tool itself has its own attestation (from when it was installed via SK-010). When the rollback happens, the operator revokes the tool's installation attestation. Cascade marks all retrieval attestations that used that tool version as `derivative_revoked`. Any Atlas facts derived from those retrievals get demoted automatically.

This is much cleaner than the manual "demote facts derived from the new version" Day 28 cleanup. The cascade does it.

---

### Day 34 — INC-006 (delta) — Intent drift in refactor

**Original outcome:** Hermes tried to write outside the intent scope. Sentinel blocked. Operator approved a new intent for the billing fix.

**With CT outcome:** Same flow, but the new intent is now a formal intent_expansion attestation referencing the original intent. The lineage shows: `att_intent_auth_refactor` → `att_intent_expansion_billing`. The billing fix's generation attestation references the expansion, not the original.

Future auditor query: "what did Alice authorize during this session?" returns the original intent + the expansion + reasoning, with timestamps.

---

### Day 43 — INC-007 (delta) — Patient memory poisoning

**Original outcome:** Day 12 fact (`prod-db-v2` is production) contradicts Day 43 fact (renamed to v3). Contradiction sweep flags. Investigation determines legitimate.

**With CT outcome:** Both wiki ingestions are retrieval attestations. The Atlas facts derived from each carry their retrieval attestation as `source_attestation`. When the contradiction sweep detects the conflict, it can ask the trust chain: "are both retrieval attestations still valid?" Both are. "Same source?" Yes (same wiki, same editor). The forensic trail is complete.

If the second fact had been poisoning rather than legitimate, the operator would revoke the malicious retrieval attestation. Cascade would invalidate every Atlas fact derived from it, every Hermes plan that used it, every artifact generated under its influence. **Recovery from a poisoning attack becomes a single revocation, not a manual cleanup.**

The doctrine open problem 10.2 (patient poisoning) is still unresolved at detection. But *recovery* is dramatically improved.

---

### Day 50 — INC-008 (delta) — Validator correlated failure

**Original outcome:** Primary and validator agreed because they shared an embedding model used for retrieval. Deterministic canary caught it.

**With CT outcome:** Both reasoners' generation attestations include `model.deployment_id`. The Attestation Service can enforce **diversity policy**: critical-path validations must have at least one validator whose deployment_id differs from the primary's *and whose retrieval inputs differ*.

The primary's generation attestation referenced retrieval `att_retrieval_xyz` (cached embedding result). The validator's generation attestation referenced... the same retrieval. **The Attestation Service refuses to issue the approval attestation** with `validators share retrieval input — diversity policy violated`.

Operator forced to re-run validation with a deterministic post-condition check or a validator using different retrieval. Catches the issue at the trust layer, not at the canary layer.

CT-T6 mitigation made operational.

---

### Day 58 — INC-010 (delta) — Stale intent root on financial action

**Original outcome:** Vault rejected capability mint for T5 action because intent root was 23h47m old.

**With CT outcome:** This is **exactly the invariant CT enforces by default**. The tier registry sets `intent_root_max_age_seconds=60` for T5. The Attestation Service refuses to issue the approval attestation with:

```
intent_root too old for tier 5: 85626s > 60s
```

Same outcome, but the rejection comes from the trust spine, not from a downstream policy. The audit log records the refusal attempt, the requesting client, the requested vs allowed age. INC-010 becomes a *prevented* event with a one-line forensic record.

Operator note in original simulation: "yesterday's near-miss is still on my mind."

With CT: "the trust spine rejected a stale intent root for a T5 action. Working as designed. Reviewing the audit entry confirms what was attempted; updated my recurring-transfer workflow to refresh intent root at execution time."

---

## End-of-simulation tally

| Category | Original | With CT |
|----------|----------|---------|
| Capabilities registered | 31 | 31 + ~15 retrieval / attestation capabilities |
| Skills | 18 | 18 + ~5 trust-chain-aware skills (verify-before-execute, lineage-query, source-revocation, attestation-replay, cascade-aware-cleanup) |
| Atlas Q-tier facts (lifetime) | ~520 | ~520 (unchanged) |
| Attestations issued | N/A | ~3,000 (one or more per dispatch + every generation + every validation + every review + every approval + every execution) |
| Audit log entries | ~5,000 | ~10,000 (CT events doubled audit volume) |
| Incidents (EXPECTED / DEGRADED / CRITICAL / CATASTROPHIC-near-miss) | 1 / 3 / 4 / 2 | 1 / 3 / 2 (some CRITICALs prevented) / 0 (catastrophic-near-misses prevented entirely) |
| **Catastrophic events** | 0 | 0 (same) |

The two catastrophic near-misses (INC-008, INC-010) become non-events — caught at issuance time, not at the last layer of defense.

The pattern across the simulation:
- Hermes-doctrine catches at the *policy* layer
- Cognitive Trust catches at the *attestation* layer

Both layers continue to matter. CT is not a replacement; it is a higher-confidence implementation of the same intents.

---

## New skills that emerge with CT

These would be added to `hermes/simulation/SKILLS.md` if CT were active:

### SK-019 — Verify before execute
**First learned:** Day 1 (CT-aware setup)
**Description:** Before any execution, dispatch a verification of the approval attestation. If state is not `valid`, refuse.
**Confidence:** high
**Notes:** Built-in; not a discretionary skill. Forge enforces this regardless.

### SK-020 — Lineage query for diagnosis
**First learned:** Day 9 (INC-002 follow-up)
**Description:** When something seems off, query the lineage from the most recent execution attestation backward. Often the explanation is in the chain.
**Confidence:** high
**Notes:** Replaces hours of forensic file-reading with a single graph walk.

### SK-021 — Source-revocation for cleanup
**First learned:** Day 28 (INC-005 follow-up)
**Description:** When a tool or input is found compromised, revoke its attestation. Cascade handles propagation. Don't manually demote facts.
**Confidence:** high
**Notes:** Vastly faster than manual cleanup. Per CT-I5 propagation SLA.

### SK-022 — Attestation replay for incident analysis
**First learned:** Day 53 (post-mortem authoring with CT lineage)
**Description:** For any incident, replay the trust chain to identify exactly which step failed or was bypassed.
**Confidence:** medium
**Notes:** Replaces narrative reconstruction with deterministic walk.

### SK-023 — Cascade-aware cleanup
**First learned:** Day 47 (`atlas.bulk_revoke` added — now backed by attestation revocation)
**Description:** When source is revoked, allow cascade to handle Atlas demotions. Don't double-act.
**Confidence:** medium

---

## The headline

Operator's end-of-60-day note in the original simulation: *"60 days. 10 incidents. Zero compromises. Many lessons. On to the next 60."*

With Cognitive Trust active: *"60 days. 8 incidents (down from 10 — two became prevented at the trust spine). Zero compromises. Every action attestable, every chain verifiable, every revocation propagated. The next operator can replay any decision and ask why. On to the next 60."*

The next-operator question is what Cognitive Trust earns you. The original simulation produced trustable operations through discipline. CT makes that discipline *cryptographically auditable*.

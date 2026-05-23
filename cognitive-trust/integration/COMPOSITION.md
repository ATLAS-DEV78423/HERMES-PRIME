# Composition: Fabric + PKI

**Purpose:** Show concretely how the Retrieval Fabric and the Cognitive PKI compose. They are designed to be useful separately and powerful together.

---

## 1. The one-sentence relationship

**The Fabric produces signed retrieval attestations; the PKI consumes them as inputs to artifact generation attestations.**

That's the whole composition. Every other interaction follows from this.

---

## 2. The combined flow

```
1. User signs intent_root attestation.
   → att_intent

2. Hermes plans, dispatches retrievals via Fabric.
   Fabric Dispatcher executes miners.
   Each miner report is wrapped in a retrieval attestation.
   → att_retrieval_1, att_retrieval_2, ...

3. Hermes generates an artifact using the retrieval reports.
   Hermes requests a generation attestation from the PKI.
   Generation attestation references:
     - intent_root (att_intent)
     - input retrievals (att_retrieval_1, att_retrieval_2, ...)
     - model identity
     - artifact content hash
   → att_generation

4. Validators run on the artifact.
   Each issues a validation attestation referencing att_generation.
   → att_validation_typecheck, att_validation_test, ...

5. (Tier-dependent) Reviewer attests, approver attests.
   → att_review, att_approval

6. Forge executes the artifact under the approval.
   Execution attestation references the approval.
   → att_execution
```

Every step is signed. The complete chain is reconstructable.

---

## 3. Why the Fabric attests its reports

A miner report unsigned is just data. A miner report signed becomes:

- **Provable input.** Generation attestations can reference exactly which retrievals informed them.
- **Tamper-evident.** Modified retrievals break signature validation.
- **Replayable.** Auditors can re-run miners against the recorded content hashes and compare.
- **Revocable.** A poisoned miner report can be revoked; the generation attestations referencing it become derivative_revoked.

Without attestation, the Fabric is a fast cache. With attestation, the Fabric becomes provenance infrastructure.

---

## 4. Hermes's view of the combined system

From Hermes's perspective, the combined system exposes three operations:

### `retrieve(intent) → AttestedReport`

Hermes issues a retrieval intent. Receives a structured report wrapped in a Fabric attestation. The attestation ID is what Hermes references later.

### `generate(artifact, inputs[]) → AttestedArtifact`

Hermes constructs an artifact (in its context). Calls the PKI with:
- artifact content (as a hash + payload reference)
- intent_root_ref
- input retrieval attestation IDs
- artifact_class

Receives a generation attestation. The artifact now has provenance.

### `verify(attestation_id) → TrustStatus`

Hermes can ask: is this attestation chain still valid? Used before executing or before depending on a previously-attested artifact.

That's the entire interface. Everything else (validation, review, approval, execution) happens through other actors but via the same attestation primitives.

---

## 5. The agent never touches keys

Critical and worth restating:

- Hermes does not have signing keys.
- Hermes calls the PKI's `request_attestation(...)` endpoint over mTLS.
- The PKI authenticates Hermes by workload identity, validates the request, calls KMS for signing.
- Hermes receives a signed attestation; the signature was made by infrastructure, not by Hermes.

A compromised Hermes can request attestations (within its scope). A compromised Hermes cannot forge attestations.

---

## 6. Sentinel sits in the middle

The Hermes Sentinel mediates between Hermes and both Fabric/PKI:

```
Hermes → Sentinel → Fabric Dispatcher
Hermes → Sentinel → Attestation Service
```

Sentinel's job:
- Validate the request is within intent root scope
- Check rate limits
- Check tier-dependent policy (e.g., "Hermes cannot request T5 generation attestations directly; needs operator escalation")
- Forward valid requests
- Reject invalid requests with typed errors

The Fabric and PKI are downstream of Sentinel. They trust Sentinel's enforcement but do their own validation as well (defense in depth).

---

## 7. The repo graph as a shared substrate

The Repo Knowledge Graph (Fabric component) is queried by:

- Miners (other miners may read existing entries to build on them)
- Hermes (via dispatcher) for graph queries
- The PKI for "what retrievals exist for this content hash?" lookups

The graph itself is not signed end-to-end (signing a mutable graph is impractical), but every entry carries its source attestation. Per-query trust is computable: walk results' source attestations; check status.

---

## 8. Composition with Hermes Atlas

Hermes Atlas (the belief store) and the PKI lineage store are distinct:

- **Atlas** stores beliefs about the world (facts, observations, conclusions). Provenance tracked per fact; quarantine tier; aging.
- **PKI lineage** stores cryptographic provenance of computational artifacts. Attestations, signatures, chains.

They overlap at boundaries:

- An Atlas fact derived from a Fabric retrieval references the retrieval attestation as its source.
- An Atlas conclusion that drove an artifact generation appears as evidence in the generation attestation's predecessor list.
- Revoking a retrieval attestation cascades to: PKI artifacts that depended on it AND Atlas facts derived from it.

The two stores are different data structures serving different queries. They share the audit log and the trust spine.

---

## 9. Worked composition: a code review flow

```
User intent: "Review the auth refactor I've been working on."

1. att_intent_root (user_alice, scope: "review auth refactor")

2. Fabric dispatches:
   - file_miner: enumerate src/auth/** → att_retrieval_001
   - dependency_miner: find_callers_of recent changes → att_retrieval_002
   - git_miner: recent commits to src/auth/** → att_retrieval_003
   - test_miner: tests covering changed files → att_retrieval_004

3. Hermes synthesizes a review summary.
   - Requests generation attestation with:
     intent_root_ref: att_intent_root
     predecessor_refs: [att_retrieval_001..004]
     artifact_class: code_review_summary
     tier: 1 (internal artifact, no execution)
   → att_generation_summary

4. Hermes presents summary to user.
   User reads it. User signs a review attestation:
   → att_review (verdict: "looks good, ready for PR")

5. (No execution; review is the terminal state.)
```

What we can now answer:
- Who reviewed? user_alice
- What model produced the summary? Recorded in att_generation_summary
- What evidence was used? Att_retrieval_001..004, each with their own provenance
- Was anything stale during the review? Hashes compared at time of attestation issuance

Compare to current: "Alice said the AI summary looked good." Nothing else known.

---

## 10. Worked composition: a production deploy

```
User intent: "Deploy payment-service v2.3.1 to production."

1. att_intent_root (user_alice, scope: "deploy payment-service v2.3.1 prod")
   - tier: 5
   - expires: 60 minutes

2. Fabric dispatches (extensive set):
   - file_miner: deployment manifest files
   - schema_miner: API surface diff vs current prod
   - dependency_miner: changed dependencies
   - git_miner: commits since last deploy
   - test_miner: test history for changed code
   - policy_miner: deploy policies and rollback procedures
   → att_retrieval_001..006

3. Hermes generates deployment plan.
   → att_generation_deploy_plan (artifact_class: deployment_plan, tier 5)

4. Validators run:
   - schema_validator: pass → att_validation_schema
   - security_scanner: pass → att_validation_security
   - test_suite: pass 247/247 → att_validation_tests
   - canary_simulator: pass → att_validation_canary

5. Review:
   - user_bob reviews via personal key → att_review_bob (verdict: approved)
   - user_carla reviews via personal key → att_review_carla (verdict: approved)
   (Two distinct reviewers per T5)

6. Approval:
   - user_diane approves (distinct from reviewers and author) → att_approval
   - Approval window: 10 minutes
   - Cooldown: 5 minutes before execution
   - Rollback procedure attached

7. Cooldown elapses.

8. Forge executes deploy command.
   - Reads approval attestation
   - Verifies entire chain is still valid (revocation check)
   - Verifies all subject_hashes still match current source
   - Executes deploy
   - Records outcome → att_execution
```

Total: ~14 attestations for one production deploy. Audit-perfect.

---

## 11. Failure-mode composition

When something breaks, the trust system makes diagnosis cleaner.

### "The deploy failed and we don't know why"

Without lineage: hours of forensics.

With lineage: walk att_execution → att_approval → att_generation_deploy_plan → input retrievals → originating intent. At each step, check timestamps, content hashes, validator outputs. The cause becomes a specific node in the graph.

### "We need to roll back a deploy from yesterday"

Without lineage: which version to roll back to? Was it ever a known-good state?

With lineage: query for "most recent successfully-executed deploy of this service whose chain is still valid." Returns att_execution with full provenance for the rollback target.

### "We just discovered the source model was compromised at the time"

Without lineage: which artifacts are affected? Unknown. Must assume everything.

With lineage: query for "all generation attestations whose model identity matches X within time range Y." Get exact list. Revoke them; cascade derivative_revocation. Affected systems get explicit notifications.

These are not theoretical. These are the questions production incident response actually asks.

---

## 12. The composability principle

The Fabric is useful without the PKI. You get fast retrieval, repo graph, miner discipline. No provenance, but tokens saved.

The PKI is useful without the Fabric. You get artifact provenance, tier-governed signing, lineage. No retrieval optimization.

Both together: the agent reasons cheaply over structured findings AND every meaningful artifact is provable end-to-end.

You can adopt them in either order. Composing both is the architecture.

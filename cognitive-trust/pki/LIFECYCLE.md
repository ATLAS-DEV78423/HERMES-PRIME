# Artifact Lifecycle

**Purpose:** Define the trust states an artifact moves through, the transitions between them, and the rules for each.

This is the state machine the PKI enforces. Implementations should treat it as canonical.

---

## 1. States

| State | Meaning |
|-------|---------|
| `draft` | Artifact exists; no attestations issued yet |
| `generated` | Generation attestation issued; no validation yet |
| `validated` | All required validations passed |
| `validation_failed` | At least one required validation failed |
| `reviewed` | At least one review attestation present; verdict captured |
| `review_rejected` | Review verdict was rejected |
| `approved` | Approval attestation present and valid |
| `executing` | Execution attestation pending |
| `executed` | Execution attestation present; outcome recorded |
| `revoked` | An attestation in the chain has been revoked |
| `derivative_revoked` | An ancestor attestation revoked; this artifact is no longer trusted |
| `expired` | Chain expired without execution |

---

## 2. State diagram

```
   draft
     │
     ▼
   generated ─────────────────┐
     │                          │
     ▼                          ▼
   validated ─────► validation_failed
     │
     ├──────── (low tier) ──────┐
     │                          │
     ▼                          │
   reviewed ─────► review_rejected
     │
     ▼
   approved
     │
     ▼
   executing
     │
     ▼
   executed
```

Cross-cutting transitions (can happen from any state):

- → `revoked` (any attestation in chain explicitly revoked)
- → `derivative_revoked` (ancestor revoked)
- → `expired` (intent root or required attestation expired before progress)

---

## 3. Transition rules

### `draft` → `generated`

Trigger: Hermes produces an artifact and requests a generation attestation.

Requires:
- Valid intent root
- Predecessor retrieval attestations (if any inputs were used)
- Model identity
- Artifact content hash

Refused if:
- Intent root expired or invalid
- Predecessors invalid
- Artifact class not registered
- Tier requirements would already be unmeetable

### `generated` → `validated`

Trigger: All required validators for the artifact's tier have produced `pass` attestations.

Requires:
- Validation attestations covering all tier-required checks (typecheck, lint, tests, schema, etc.)
- All `result: pass`

### `generated` → `validation_failed`

Trigger: At least one required validator produced `result: fail`.

Effect: Artifact cannot proceed without a new generation (the original is now historical evidence).

### `validated` → `reviewed`

Trigger: A review attestation is issued for this artifact.

Requires (per tier):
- Reviewer authentication satisfies tier requirements
- For T4+: separation-of-duties (reviewer ≠ author intent signer for tier 4, reviewer ≠ approver always)

### `reviewed` → `review_rejected`

Trigger: Review verdict is `rejected`.

Effect: Same as validation_failed — artifact cannot proceed without re-generation.

### `validated` (or `reviewed`) → `approved`

Trigger: An approval attestation is issued referencing the validation (and review for high tiers).

Requires:
- All tier-required preceding attestations present
- Approver authorized for this artifact class
- For T5+: multi-party approval (two distinct approvers, neither the reviewer)

### `approved` → `executing`

Trigger: Forge accepts the artifact for execution.

Effect: Brief transient state. Records that execution has begun but not completed.

### `executing` → `executed`

Trigger: Forge completes execution and issues the execution attestation.

The execution attestation records outcome (success / partial / failed / rolled_back). The artifact is now historical evidence regardless of outcome.

### Any state → `revoked`

Trigger: A revocation attestation is issued targeting an attestation in this artifact's chain.

Effect: Artifact's effective state changes to `revoked`. Verifiers return revoked.

### Any state → `derivative_revoked`

Trigger: Cascade from an ancestor's revocation.

Effect: Same as revoked, but distinguishable in audit (someone else's revocation caused this).

### Any state → `expired`

Trigger: An attestation in the chain passed `expires_at` without advancing.

Effect: Artifact cannot proceed in its current chain. Re-generation under a fresh intent root is required.

---

## 4. State transitions and the audit log

Every state transition is itself audited. The audit entry records:

- Artifact ID
- Old state
- New state
- Triggering attestation (or revocation event)
- Timestamp
- Hash chain link

This means: "at what time did artifact X become approved?" has a definitive answer with cryptographic evidence.

---

## 5. State queries

The verification service exposes a query: `artifact_state(artifact_id) → State + trust evidence`.

Implementation:

1. Find the artifact's most recent generation attestation.
2. Walk forward to find all attestations referencing it.
3. Determine furthest-progressed state.
4. Cross-check revocation index.
5. Return state with the supporting attestation chain.

Cost: O(chain depth + downstream breadth). Cacheable per (artifact_id, revocation_index_version).

---

## 6. Why state separation matters

It would be tempting to collapse states. Don't. Each distinction carries meaning:

- **`validated` vs `reviewed`:** automated checks passed vs human looked. Different signals; both required for many tiers.
- **`reviewed` vs `approved`:** human looked vs human authorized. Separation enables "looked but rejected," "approved by different person than reviewer," and other realistic flows.
- **`approved` vs `executed`:** authorization to execute vs actually executed. Crucial for time-bounded approvals.
- **`revoked` vs `derivative_revoked`:** explicit invalidation vs cascade. Audit needs to know which.
- **`expired` vs `revoked`:** timeout vs explicit invalidation. Different forensic implications.

A trust system that collapses these states loses the ability to answer real questions.

---

## 7. Lifecycle and risk tiers

The state machine is universal, but **which states are required** varies by tier. See `TRUST_TIERS.md` for the full mapping. A summary:

| Tier | Required to reach `executed` |
|------|------------------------------|
| 0 (scratch) | draft → executed (no attestation chain) |
| 1 (internal) | generated → executed |
| 2 (reversible scoped) | generated → validated → approved → executed |
| 3 (PR-bound) | generated → validated → reviewed → approved → executed |
| 4 (deploy config) | generated → validated → reviewed → approved → executed (with cooldown) |
| 5 (production) | generated → validated → reviewed (2x) → approved (separate party) → executed (with cooldown + rollback prep) |

The Attestation Service enforces the tier requirements at every transition.

---

## 8. Long-lived artifacts

Some artifacts persist (e.g., a deployed service config remains "executed" indefinitely). The PKI handles this by:

- The execution attestation is the **terminal state** for the execution event itself
- The artifact's ongoing trust state is a derived view: "is the execution attestation's chain still valid?"
- If anything in the chain is later revoked, the deployed artifact is flagged
- Operators can configure alerts: "warn me if any deployed artifact's trust chain becomes revoked"

This is how revocation translates to operational reality: not just "this past action was bad" but "this currently-running thing has lost trust."

---

## 9. Lifecycle for non-execution artifacts

Not every artifact is destined for execution. Documents, plans, designs may live entirely in the `validated` or `reviewed` state forever. The lifecycle still applies; they just don't progress past their natural endpoint.

This is fine. The trust chain is meaningful even for non-executable artifacts because the question "who produced this document and with what evidence?" matters.

---

## 10. Misc edge cases

### Re-validation after source change

If a source file changes after `validated` but before `executed`, the next validator run detects drift and the artifact's state reverts to `generated`. Re-validation is required.

### Approval revoked before execution

Common case: approval was issued, then revoked (operator changed their mind). The execution attempt fails; Forge consults verification service and refuses.

### Execution after window expiry

Approval has an execution window. If Forge attempts execution outside the window, refusal. New approval required.

### Multiple executions of the same approval

By default, an approval is single-use. If multiple executions are needed (e.g., rolling deploy), the approval explicitly declares `max_executions: N` with a tracking counter.

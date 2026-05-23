# Trust Tiers

**Purpose:** Define the risk-tiered ceremony requirements for artifact classes. Operationalizes CP6 ("trust is risk-tiered") and CT-I8 ("trust tier governs ceremony").

The principle: friction is proportional to consequence. A scratch note needs no ceremony. A production deploy needs full ceremony. Most artifacts sit in between.

---

## 1. Tier definitions

| Tier | Name | Reversibility | Blast radius | Examples |
|------|------|---------------|--------------|----------|
| 0 | Scratch | Trivially reversible | None / local | Working notes, exploration outputs |
| 1 | Internal | Easily reversible | Local | Doc drafts, internal summaries, plan outlines |
| 2 | Reversible-scoped | Reversible with effort | Workspace | Code changes (local, uncommitted), refactor suggestions |
| 3 | PR-bound | Reversible via PR | Repository | Commits, PRs, branch operations |
| 4 | Deploy-class | Reversible with rollback | Service | Deployment configs, IaC changes, schema migrations |
| 5 | Production | Reversible at cost / irreversible | Org / users | Production deploys, financial transactions, broadcast comms |

---

## 2. Ceremony requirements per tier

| Tier | Generation | Validation | Review | Approval | Execution |
|------|-----------|------------|--------|----------|-----------|
| 0 | optional | none | none | none | none |
| 1 | required | none | none | none | session-implicit |
| 2 | required | required | none | self-approval | session-implicit |
| 3 | required | required | required (1 person) | self or other | per-action consent |
| 4 | required | required | required (1 person) | other person | per-action consent + cooldown |
| 5 | required | required | required (2 people, distinct) | third person (not reviewer) | per-action consent + cooldown + 2FA + rollback prep |

Key terms:
- **session-implicit:** approval covered by the active session's intent root; no separate ceremony
- **per-action consent:** explicit user click-through for this specific execution
- **cooldown:** mandatory wait between approval and execution (e.g., 30 seconds for T4, 5 minutes for T5)
- **2FA:** second factor authentication at execution time
- **rollback prep:** pre-execution snapshot or dry-run reversible plan recorded

---

## 3. Validation requirements per tier

What validations are required to count toward `validated` state.

| Tier | Required validations |
|------|---------------------|
| 0 | none |
| 1 | none |
| 2 | tier-2-suite (typecheck if applicable, lint) |
| 3 | tier-3-suite (tier-2 + unit tests + security scan) |
| 4 | tier-4-suite (tier-3 + integration tests + dry-run + schema validation + dependency audit) |
| 5 | tier-5-suite (tier-4 + canary simulation + rollback verification + production parity check) |

Operators define the suite contents; the Attestation Service enforces presence.

---

## 4. Tier mapping examples

Concrete examples mapping artifact classes to tiers. This is illustrative; real mappings depend on deployment context.

| Artifact class | Tier | Why |
|----------------|------|-----|
| `scratch_note` | 0 | Reversible, local, no consequence |
| `research_summary` | 1 | Local, easy to discard |
| `code_explanation` | 1 | Read-only output |
| `refactor_proposal` | 1 | Not applied; just a proposal |
| `code_patch_local` | 2 | Affects working tree |
| `test_addition` | 2 | New tests, reversible |
| `git_commit` | 3 | Now part of history |
| `git_branch_push` | 3 | Public visibility |
| `pull_request_create` | 3 | Workflow-visible |
| `deployment_config_staging` | 4 | Affects staging service |
| `schema_migration_staging` | 4 | Affects data structure |
| `dependency_upgrade` | 4 | Affects build/runtime |
| `deployment_config_production` | 5 | Affects users |
| `schema_migration_production` | 5 | Affects production data |
| `financial_transaction` | 5 | Money moves |
| `outbound_email_external` | 5 | External communication |
| `secrets_rotation` | 5 | Affects all credential consumers |

Operators register their own classes with explicit tier mappings. The Attestation Service refuses unregistered classes.

---

## 5. Why the table approach matters

Without explicit per-class tier mapping, you get one of two failures:

1. **Under-classification:** A class registered as low-tier when it should be high-tier. Result: under-reviewed catastrophic actions.
2. **Over-classification:** Everything classified as high-tier. Result: ceremony exhaustion, user click-through, defeated security.

The mapping is **policy data**, not request data. Per CT-I8 and CT-T9: requests cannot self-classify; classification is derived from the registered artifact class.

---

## 6. The "tier upgrade" pattern

Sometimes an artifact's risk grows during its lifecycle. Example: a code patch that initially looked T3 turns out to touch a production hot path during validation; should be T4 or T5.

Pattern: validators can emit `tier_upgrade_recommendation` attestations. These don't change the tier (only registration does), but they trigger operator review.

The Attestation Service does NOT auto-upgrade tiers based on probabilistic signals (CT-I8, CT-AC9 defense). Upgrades are explicit operator actions.

---

## 7. Friction budgets per tier

Per CP6 (friction is finite), each tier has a per-session friction budget. If a tier-N action would push the session over budget, the user is informed; further actions of that tier may be batched or deferred.

Defaults:

| Tier | Per-session limit | Per-day limit |
|------|------------------|---------------|
| 0 | unlimited | unlimited |
| 1 | unlimited | unlimited |
| 2 | unlimited (under batched consent) | unlimited |
| 3 | 30 actions | 100 actions |
| 4 | 10 actions | 30 actions |
| 5 | 3 actions | 10 actions |

Beyond these, the system warns and may require additional confirmation per action. Operators can tune; the defaults are deliberately conservative to surface consent fatigue early.

---

## 8. Tier-specific timing requirements

For high tiers, time-bounded approvals are mandatory.

| Tier | Approval window | Cooldown (approval → execution) | Intent root freshness |
|------|----------------|--------------------------------|----------------------|
| 0 | N/A | N/A | N/A |
| 1 | session lifetime | N/A | session |
| 2 | session lifetime | N/A | session |
| 3 | 1 hour | none | < 1 hour |
| 4 | 30 minutes | 30 seconds | < 30 minutes |
| 5 | 10 minutes | 5 minutes | < 60 seconds |

The intent root freshness column is the lesson from Hermes INC-010 (Day 58): for T5 actions, cached intent roots are not enough.

---

## 9. Separation of duties (high tiers)

| Tier | Reviewer ≠ author | Approver ≠ reviewer | Multi-party? |
|------|-------------------|--------------------|--|
| 0–2 | N/A | N/A | No |
| 3 | recommended | not required | No |
| 4 | required | required | No |
| 5 | required | required | Yes (2+ approvers, distinct) |

"Author" here means the intent root signer for the artifact. For T4+, the reviewer must be a different person from the user who authorized the work.

---

## 10. Reviewer/approver authentication per tier

| Tier | Reviewer auth | Approver auth |
|------|---------------|---------------|
| 0 | N/A | N/A |
| 1 | N/A | N/A |
| 2 | N/A | session |
| 3 | session | session |
| 4 | personal key (WebAuthn / HW token) | personal key |
| 5 | personal key + recent-auth (≤ 5 min) | personal key + recent-auth (≤ 1 min) |

Per CT-I10, T4+ reviewer attestations require personal keys. T5 additionally requires fresh authentication for both reviewer and approver.

---

## 11. The friction-vs-safety tradeoff

This is the load-bearing observation: the table values are tradeoffs, not laws.

Tightening (more ceremony per tier) increases safety but risks consent fatigue and bypass attempts.

Loosening risks under-reviewed catastrophic actions.

The doctrine answer: tune based on incident history. Start conservative. Loosen tiers only after demonstrated stability and explicit operator review (with its own attestation).

The simulation in `hermes/simulation/` shows this tuning in action — Day 14 (INC-003) tightened consent batching rules; Day 36 upgraded "unfamiliar recipient" from advisory to hard 2FA. These were tier-fit refinements.

---

## 12. Tier change governance

Changing an artifact class's tier is itself a high-tier action. Required:

- Operator attestation (signed)
- Justification documented in audit log
- Active deployments using the affected class are notified
- Old tier requirements remain valid for in-flight chains; new tier applies to new artifacts

This prevents "quietly downgraded the deploy config tier to ship faster" from being a casual action.

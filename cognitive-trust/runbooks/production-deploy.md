# Runbook: Production Deploy Under Cognitive Trust

**Scenario:** Deploy `payment-service v2.3.1` to production using the full Cognitive Trust pipeline. Tier-5 action class: `deployment_config_production`.

**Audience:** Operators and on-call engineers who need to walk an attestation-by-attestation deploy end to end, including the exact JSON envelopes that get signed.

**Prerequisites:**
- KMS-backed signer configured (recommend Vault Transit for ed25519)
- SQLite or Postgres lineage store provisioned with append-only triggers
- Async cascade worker running with healthy metrics
- Tier registry registered for the deploy class
- Two reviewers with personal keys provisioned
- One approver (distinct from both reviewers) with personal key
- Forge configured to honor approval attestations
- Rollback procedure pre-documented

---

## Step 0 — Pre-flight

Run these checks before initiating. If any fails, abort.

```bash
# Lineage store integrity
$ cogtrust-cli lineage validate-chain
chain valid: True, size: 18437, head: sha256:8a4c...

# Async cascade healthy
$ cogtrust-cli cascade metrics
queued=12 completed=12 in_flight=0 sla_breaches_24h=0
p50=42ms p99=312ms max=918ms (target 60000ms)

# Tier registry has the class
$ cogtrust-cli tiers describe deployment_config_production
tier=5
min_validations=7
min_reviewers=2
approver_distinct_from_reviewer=True
multi_party_approval=True
approval_window=600s
cooldown=300s
intent_root_max_age=60s
reviewer_auth_kind=personal_fresh

# KMS reachable
$ cogtrust-cli signer health
signer=vault_transit_prod identity=attestation_service_prod
last_sign_latency_ms=23 status=healthy
```

All four should report green. If any are degraded, do not proceed.

---

## Step 1 — Sign intent root

The deploy owner (Alice) authenticates and signs the intent root. T5 requires `intent_root_max_age=60s`, so the timing matters: this attestation expires from a freshness perspective within 60 seconds.

**Request:**

```json
{
  "type": "intent_root",
  "subject": {
    "intent_description": "Deploy payment-service v2.3.1 to production",
    "scope": {
      "service": "payment-service",
      "version": "v2.3.1",
      "environment": "production",
      "actions": ["read", "deploy", "verify"]
    },
    "session_id": "sess_20260522_alice_001",
    "user_id": "user_alice"
  },
  "artifact_class": "deployment_config_production",
  "intent_root_ref": null,
  "expires_at": "2026-05-22T17:30:00Z"
}
```

**Response:** signed attestation, ID `att_intent_001`. Record this. Subsequent steps reference it.

```json
{
  "attestation_id": "att_intent_001",
  "type": "intent_root",
  "issuer": {
    "identity": "user_alice",
    "kind": "personal",
    "cert_chain": ["MCowBQYDK2VwAyEA..."]
  },
  ...
  "context": {
    "intent_root_ref": null,
    "predecessor_refs": [],
    "artifact_class": "deployment_config_production",
    "tier": 5
  },
  "signature": {
    "algorithm": "ed25519",
    "value": "Zk/0M7..."
  }
}
```

**Clock starts.** From here, every subsequent step must complete before the next freshness boundary.

---

## Step 2 — Hermes plans the deploy and dispatches retrievals

Hermes constructs a deploy plan. To do so, it dispatches several Fabric miners. Each returns a signed retrieval attestation referencing `att_intent_001`.

| Miner | Task | Resulting attestation |
|-------|------|----------------------|
| file_miner | locate deployment manifests | `att_retrieval_001` |
| schema_miner | API surface diff vs current prod | `att_retrieval_002` |
| dependency_miner | changed dependencies vs last deploy | `att_retrieval_003` |
| git_miner | commits since last prod deploy | `att_retrieval_004` |
| test_miner | test history for changed code | `att_retrieval_005` |
| policy_miner | deploy policies + rollback procedures | `att_retrieval_006` |

Example retrieval attestation (file_miner):

```json
{
  "attestation_id": "att_retrieval_001",
  "type": "retrieval",
  "issuer": {
    "identity": "fabric_dispatcher_prod",
    "kind": "service",
    "cert_chain": ["..."]
  },
  "subject": {
    "miner": "file_miner",
    "task": "find_by_glob",
    "params_hash": "sha256:7c4a...",
    "report_hash": "sha256:e8b1...",
    "scope_effective": {
      "root": "/repo/payment-service",
      "include_globs": ["deploy/**", "k8s/**"]
    },
    "llm_used": false,
    "total_candidates": 12,
    "returned": 12
  },
  "context": {
    "intent_root_ref": "att_intent_001",
    "predecessor_refs": [],
    "artifact_class": "retrieval_report",
    "tier": 1
  },
  "subject_hashes": {
    "deploy/production.yaml": "sha256:1234...",
    "deploy/secrets.encrypted.yaml": "sha256:5678...",
    "k8s/payment-service.yaml": "sha256:9abc..."
  },
  ...
}
```

All six retrievals complete in parallel within ~3 seconds.

---

## Step 3 — Hermes generates the deploy plan

```json
{
  "type": "generation",
  "subject": {
    "artifact_id": "art_deploy_v231_prod_001",
    "artifact_class": "deployment_config_production",
    "artifact_hash": "sha256:f00d...",
    "model": {
      "provider": "anthropic",
      "name": "claude-sonnet-4-5",
      "version": "2026-04-01",
      "deployment_id": "prod-claude-pool-east-1"
    },
    "prompt_hash": "sha256:3141...",
    "input_attestations": [
      "att_retrieval_001",
      "att_retrieval_002",
      "att_retrieval_003",
      "att_retrieval_004",
      "att_retrieval_005",
      "att_retrieval_006"
    ],
    "generation_metadata": {
      "tokens_in": 18432,
      "tokens_out": 2104,
      "duration_ms": 8421,
      "temperature": 0.0
    }
  },
  "artifact_class": "deployment_config_production",
  "intent_root_ref": "att_intent_001",
  "predecessor_refs": [
    "att_retrieval_001", "att_retrieval_002", "att_retrieval_003",
    "att_retrieval_004", "att_retrieval_005", "att_retrieval_006"
  ],
  "subject_hashes": {
    "artifact": "sha256:f00d..."
  }
}
```

**Response:** `att_generation_001`.

The artifact (the deploy plan itself) is stored in workspace as `art_deploy_v231_prod_001.yaml`. The attestation references its hash; verifiers can recompute.

---

## Step 4 — Validations run

Per the T5 tier requirements (`min_validations=7`), seven validator attestations must be issued before approval.

| # | Validator | Result | Attestation |
|---|-----------|--------|-------------|
| 1 | schema_validator | pass | `att_validation_001` |
| 2 | security_scanner | pass | `att_validation_002` |
| 3 | unit_test_suite | pass (247/247) | `att_validation_003` |
| 4 | integration_test_suite | pass (89/89) | `att_validation_004` |
| 5 | canary_simulator | pass | `att_validation_005` |
| 6 | rollback_plan_validator | pass | `att_validation_006` |
| 7 | production_parity_check | pass | `att_validation_007` |

If any validation fails:
- Issue the failed validation attestation anyway (it's evidence)
- The artifact's state becomes `validation_failed`
- Do not proceed to review
- New `att_generation_002` will be needed after fix

All seven pass.

---

## Step 5 — Two distinct reviewers

T5 requires **two** reviewers with **personal_fresh** authentication (recent re-auth within session). Reviewers must be distinct people from each other AND from the approver in Step 6.

### Reviewer 1: Bob

Bob authenticates via WebAuthn/hardware token in the reviewer UI. Reviewer UI presents:

- The artifact (`art_deploy_v231_prod_001.yaml`)
- The diff vs current production
- Validation results
- Input retrieval attestations and their summaries
- Trust chain status (currently valid, fresh)

Bob inspects for ~3 minutes. Approves with comments.

```json
{
  "type": "review",
  "issuer": {
    "identity": "user_bob",
    "kind": "personal",
    "cert_chain": ["<bob_personal_cert>"]
  },
  "subject": {
    "reviewer_id": "user_bob",
    "target_artifact": "att_generation_001",
    "verdict": "approved",
    "comments_hash": "sha256:5e7d...",
    "review_duration_ms": 187000,
    "items_inspected": ["diff", "manifest", "test_results", "rollback_plan"]
  },
  "intent_root_ref": "att_intent_001",
  "predecessor_refs": ["att_generation_001"]
}
```

**Response:** `att_review_bob`.

### Reviewer 2: Carla

Same flow, different person. `att_review_carla`.

If either reviewer rejects, the artifact's state becomes `review_rejected` and the deploy is aborted. Re-generation with a fix is required.

---

## Step 6 — Approval by a third party

T5 requires the approver to be distinct from both reviewers (per `approver_distinct_from_reviewer=True`).

Diane authenticates, reviews the artifact + the two review attestations, and approves:

```json
{
  "type": "approval",
  "issuer": {
    "identity": "user_diane",
    "kind": "personal",
    "cert_chain": ["<diane_personal_cert>"]
  },
  "subject": {
    "approver_id": "user_diane",
    "target_artifact": "att_generation_001",
    "execution_window": {
      "not_before": "2026-05-22T16:35:00Z",
      "not_after": "2026-05-22T16:45:00Z"
    },
    "execution_constraints": {
      "max_executions": 1,
      "rollback_required": true,
      "rollback_attestation_ref": "att_validation_006"
    }
  },
  "intent_root_ref": "att_intent_001",
  "predecessor_refs": [
    "att_generation_001",
    "att_validation_001", "att_validation_002", "att_validation_003",
    "att_validation_004", "att_validation_005", "att_validation_006",
    "att_validation_007",
    "att_review_bob", "att_review_carla"
  ]
}
```

**The Attestation Service enforces:**
- Two review attestations among predecessors (CT-I8)
- Diane's approver_id not in the reviewer_ids set (separation of duties)
- Intent root `att_intent_001` is younger than 60 seconds (T5 freshness — **this is INC-010 made invariant**)

If intent root has aged past 60 seconds (likely if Steps 1-6 took longer than expected), the approval is **rejected with `intent_root too old for tier 5`**. Alice must re-sign the intent. This is by design.

**Response:** `att_approval_001`.

---

## Step 7 — Cooldown

T5 mandates `cooldown=300s` (5 minutes) between approval and execution. During this window:

- Forge will reject execution attempts (cooldown check)
- Anyone may revoke the approval (e.g., Diane changes her mind, on-call detects an issue)
- Trust chain is monitored: if any predecessor gets revoked during cooldown, execution will be refused

The cooldown is operator-visible. A dashboard shows:

```
DEPLOY READY (in cooldown)
  artifact: art_deploy_v231_prod_001
  approved_by: user_diane
  reviewers: user_bob, user_carla
  cooldown_remaining: 4m 17s
  trust_chain: valid
  revoke link: [revoke approval]
```

---

## Step 8 — Execution

After cooldown elapses, Forge executes. Before enacting, Forge re-verifies:

```python
status = verifier.verify("att_approval_001")
if status.state != TrustState.VALID:
    raise ExecutionRefused(f"approval not valid: {status.reason}")

# Re-check subject_hashes against current source.
for path, expected_hash in approval.subject_hashes.items():
    current = file_content_hash(path)
    if current != expected_hash:
        raise ExecutionRefused(f"source drift on {path}")

# Check approval window.
now = datetime.utcnow()
window = approval.subject["execution_window"]
if not (window["not_before"] <= now.isoformat() <= window["not_after"]):
    raise ExecutionRefused("outside execution window")
```

If all checks pass, Forge runs the deploy.

```json
{
  "type": "execution",
  "issuer": {
    "identity": "forge_prod",
    "kind": "service"
  },
  "subject": {
    "approval_attestation": "att_approval_001",
    "executed_at": "2026-05-22T16:40:14Z",
    "outcome": "success",
    "outcome_details_hash": "sha256:abcd...",
    "side_effects": [
      {
        "kind": "k8s_apply",
        "namespace": "payment-prod",
        "manifest_hash": "sha256:f00d...",
        "before_revision": "rev_v230",
        "after_revision": "rev_v231"
      },
      {
        "kind": "config_map_update",
        "name": "payment-config",
        "before_hash": "sha256:111...",
        "after_hash": "sha256:222..."
      }
    ]
  },
  "intent_root_ref": "att_intent_001",
  "predecessor_refs": ["att_approval_001"]
}
```

**Response:** `att_execution_001`. Deploy is live.

---

## Step 9 — Post-deploy verification

Forge does not consider itself done until post-conditions verify:

- Health check on the deployed service (via `health_miner`)
- Compare metric snapshots before/after
- Any failure within the verification window triggers automatic rollback consideration

If verification reports degradation, the operator gets a paged alert with:
- Direct link to `att_execution_001`
- Pre-staged rollback command
- Current trust chain status

---

## Total attestations issued

For a single T5 production deploy:

| Category | Count |
|----------|-------|
| Intent root | 1 |
| Retrievals | 6 |
| Generation | 1 |
| Validations | 7 |
| Reviews | 2 |
| Approval | 1 |
| Execution | 1 |
| **Total** | **19** |

Plus the implicit derivative cascade tracking. Each is signed, lineage-chained, and verifiable forever.

---

## Common failure modes during this flow

### Intent root expires before approval (most common pitfall)

**Symptom:** Step 6 returns `intent_root too old for tier 5`.

**Cause:** Total time from Step 1 to Step 6 exceeded the 60-second freshness window. Reviewers took too long or there were tool delays.

**Resolution:** Alice re-signs intent root. All downstream attestations get re-issued referencing the new intent root. The expired intent root remains in the audit log as historical evidence.

**Mitigation:** Pre-stage as much as possible before signing the intent root. Have reviewers ready and notified. The 60-second freshness window for T5 is the lesson from Hermes INC-010 — don't try to widen it.

### Reviewer impersonation attempt

**Symptom:** Step 5 review request comes in with a service-key signature instead of a personal-key signature.

**Cause:** Either misconfiguration, or attempted bypass.

**Resolution:** Attestation Service rejects with `tier 5 requires personal-fresh-key reviewer attestation`. Investigate which client attempted this.

### Validation failure mid-flight

**Symptom:** Step 4 produces `att_validation_005: result=fail` (canary simulator).

**Cause:** The deploy plan would cause an issue under canary load.

**Resolution:** Do not proceed to review. Surface to Hermes for re-generation. The failed validation attestation is itself a permanent record of why this version didn't ship.

### Tool change between attestation and execution

**Symptom:** Step 8 reports `source drift on deploy/production.yaml`.

**Cause:** Someone (or another agent) modified the file between Step 2's retrieval and Step 8's execution.

**Resolution:** Execution refused. Investigate the modification. The chain is now broken at the retrieval layer; re-mining + new generation required.

### KMS becomes unavailable

**Symptom:** Step 3 or beyond returns 5xx from attestation service.

**Cause:** KMS reachability issue.

**Resolution:** Pause deploy. Investigate KMS. Do not bypass attestation (no "ship without attestation just this once"). The audit log gap is unacceptable.

---

## What you can answer after this deploy

For any subsequent question about this production change:

- **Who authorized it?** `att_intent_001` → user_alice
- **Which model produced the plan?** `att_generation_001` → claude-sonnet-4-5 version 2026-04-01
- **What context informed it?** Six retrieval attestations with content hashes
- **Who reviewed it?** Bob + Carla, both personal-signed
- **Who approved?** Diane, distinct from reviewers
- **When did it execute?** 2026-05-22T16:40:14Z
- **What changed in production?** k8s apply on payment-prod (revision details in `att_execution_001`)
- **Have the source files changed since?** Compare current hashes to `subject_hashes` in any attestation
- **Is the chain still valid?** `verifier.verify("att_execution_001")` returns current state

If any of these answers is unsatisfactory three months from now, the chain itself tells you why.

---

## Total deploy time budget

| Phase | Target | Hard limit |
|-------|--------|-----------|
| Step 1 (intent sign) | 5s | 30s |
| Steps 2-3 (retrieve + generate) | 30s | 90s |
| Step 4 (validations) | 60s | 300s |
| Step 5 (reviews) | 5min | 30min* |
| Step 6 (approval) | 30s | 5min |
| Step 7 (cooldown) | 5min | 5min (fixed) |
| Step 8 (execution) | 30s | 5min |
| Step 9 (verification) | 60s | 10min |

*Reviewer time is the variable. If reviews take long, the intent root expires (60s for T5) and Step 1 must be re-done. **This is intentional** — long reviews indicate the deploy may not be well-scoped; consider breaking into smaller deploys.

In practice, well-scoped T5 deploys with prepared reviewers complete in 8-15 minutes end to end.

---

## What this runbook is not

- Not a sales pitch for ceremony. The ceremony is heavy because T5 is heavy. Tier-3 deploys (e.g., staging) skip most of this.
- Not optional in production. Deploys without this trail are unauditable and accumulate trust debt.
- Not the only way to deploy. Emergency revocation and rollback have their own runbooks (TODO).

# Cognitive Trust SLA and Observability Spec

**Purpose:** Define service-level objectives, the metrics needed to measure them, alerting thresholds, and dashboards for operating the Attestation Service and Retrieval Fabric in production.

**Audience:** SRE / operations teams.

---

## 1. SLOs at a glance

| Service | SLO | Target |
|---------|-----|--------|
| Attestation Service | Issuance latency (p99) | < 200ms |
| Attestation Service | Availability | 99.95% |
| Attestation Service | Issuance success rate | > 99.9% |
| Verification Service | Verify latency p99 (cache hit) | < 5ms |
| Verification Service | Verify latency p99 (cache miss) | < 100ms |
| Verification Service | Availability | 99.99% (read-only, easier to scale) |
| Lineage Store | Append latency p99 | < 50ms |
| Lineage Store | Chain validation pass rate | 100% (any failure is CRITICAL) |
| Async Cascade | End-to-end revocation propagation | < 60s p99 (CT-I5) |
| Async Cascade | Queue depth | < 100 sustained |
| Async Cascade | Backpressure rejection rate | < 0.1% over 24h |
| KMS Signing | Signing latency p99 | < 100ms |
| KMS Signing | Signing success rate | > 99.99% |
| Fabric Dispatcher | Dispatch latency p99 (deterministic miner) | < 500ms |
| Fabric Dispatcher | Dispatch latency p99 (LLM miner) | < 30s |
| Reviewer UI | Authentication latency p99 | < 1s |
| Reviewer UI | Attestation issuance after click p99 | < 2s |

These are starting points. Tune to your traffic profile.

---

## 2. Required metrics

### 2.1 Attestation Service

| Metric | Type | Labels | Notes |
|--------|------|--------|-------|
| `cogtrust_attestation_issuance_total` | Counter | type, artifact_class, tier, result | result=success/denied/error |
| `cogtrust_attestation_issuance_duration_seconds` | Histogram | type, tier | Includes signing + lineage write |
| `cogtrust_attestation_denial_total` | Counter | reason, tier | Categorical denials |
| `cogtrust_signing_duration_seconds` | Histogram | signer_identity, algorithm | KMS call only |
| `cogtrust_signing_failure_total` | Counter | signer_identity, error_kind | |
| `cogtrust_tier_policy_violations_total` | Counter | tier, violation_kind | e.g., missing_reviewer, intent_root_too_old |

### 2.2 Lineage Store

| Metric | Type | Labels | Notes |
|--------|------|--------|-------|
| `cogtrust_lineage_appends_total` | Counter | result | success/duplicate/error |
| `cogtrust_lineage_append_duration_seconds` | Histogram | | Storage-layer latency |
| `cogtrust_lineage_size_attestations` | Gauge | | Total attestations stored |
| `cogtrust_lineage_chain_validation_duration_seconds` | Histogram | | From periodic checks |
| `cogtrust_lineage_chain_validation_failures_total` | Counter | | **Must always be 0** |
| `cogtrust_lineage_tamper_attempts_total` | Counter | | From DB trigger failures |

### 2.3 Verification

| Metric | Type | Labels | Notes |
|--------|------|--------|-------|
| `cogtrust_verify_total` | Counter | result, cache | result=valid/revoked/derivative_revoked/expired/etc; cache=hit/miss |
| `cogtrust_verify_duration_seconds` | Histogram | result, cache | |
| `cogtrust_verify_cache_size` | Gauge | | |
| `cogtrust_verify_chain_depth` | Histogram | | Chain length verified |

### 2.4 Revocation

| Metric | Type | Labels | Notes |
|--------|------|--------|-------|
| `cogtrust_revocation_index_version` | Gauge | | Current version |
| `cogtrust_revocation_total` | Counter | derivative | True/false |
| `cogtrust_cascade_queue_depth` | Gauge | | |
| `cogtrust_cascade_jobs_total` | Counter | result | completed/failed/rejected_backpressure |
| `cogtrust_cascade_latency_seconds` | Histogram | | End-to-end propagation latency |
| `cogtrust_cascade_sla_breaches_total` | Counter | | Per CT-I5 (60s target) |

### 2.5 Fabric Dispatcher

| Metric | Type | Labels | Notes |
|--------|------|--------|-------|
| `cogtrust_dispatch_total` | Counter | miner, task, status | status=ok/truncated/timeout/denied/error/escalate/no_results |
| `cogtrust_dispatch_duration_seconds` | Histogram | miner, task | |
| `cogtrust_dispatch_tokens_used_total` | Counter | miner | LLM tokens for LLM miners |
| `cogtrust_dispatch_budget_clamps_total` | Counter | miner, budget_kind | Requests whose budget was reduced |
| `cogtrust_dispatch_injection_flags_total` | Counter | miner | Reports flagged as injection-suspicious |
| `cogtrust_dispatch_per_turn_token_total` | Histogram | | Token spend per main-agent turn |

### 2.6 Reviewer UI

| Metric | Type | Labels | Notes |
|--------|------|--------|-------|
| `cogtrust_reviewer_authentications_total` | Counter | method, result | webauthn/hardware/etc |
| `cogtrust_reviewer_decision_duration_seconds` | Histogram | tier, verdict | Time from artifact load to decision |
| `cogtrust_reviewer_consent_fatigue_score` | Gauge | reviewer_id | Computed from recent decision latencies |
| `cogtrust_reviewer_rejections_total` | Counter | tier, reason | |

---

## 3. Alerting rules

### CRITICAL (page immediately, regardless of hour)

| Alert | Condition | Why |
|-------|-----------|-----|
| LineageChainBroken | `cogtrust_lineage_chain_validation_failures_total` increases by 1 | Audit integrity lost |
| LineageTamperAttempt | `cogtrust_lineage_tamper_attempts_total` increases by 1 | Someone tried direct UPDATE/DELETE |
| SigningFailureSpike | `rate(cogtrust_signing_failure_total[5m]) > 0.1` | KMS issue blocks all issuance |
| AttestationServiceDown | Availability < 99% over 5m | Hard outage |
| CascadeSlaBreach | `cogtrust_cascade_sla_breaches_total` increases | Revocation isn't propagating in time |
| RevocationIndexStale | Version unchanged when revocations have been requested for > 60s | Cascade worker hung |

### HIGH (page during business hours, ticket otherwise)

| Alert | Condition | Why |
|-------|-----------|-----|
| HighIssuanceLatency | p99 > 500ms for 10m | Approaching SLO violation |
| HighDispatchTokenSpend | p99 per-turn > 50k tokens for 1h | Cost regression or misuse |
| HighInjectionFlagRate | `rate(cogtrust_dispatch_injection_flags_total[1h]) > 1/min` | Possible attack or noisy source |
| CascadeQueueGrowing | Queue depth > 50 sustained for 10m | Worker can't keep up |
| BackpressureRejections | `rate(cogtrust_cascade_jobs_total{result="rejected_backpressure"}[5m]) > 0` | Should be ~0 |
| TierPolicyViolations | Rate > 1/min sustained | Misconfiguration or attack |

### WARNING (ticket, review during day)

| Alert | Condition | Why |
|-------|-----------|-----|
| LowCacheHitRate | Verification cache hit rate < 50% over 1h | Cache may be misconfigured |
| HighReviewerFatigue | Any reviewer's fatigue score above threshold | Per CT-T5 mitigation |
| LowFabricMinerDiversity | LLM miner share > 30% of dispatches | Drift toward probabilistic retrieval |
| HighSchemaViolationRate | Tool output schema failures > 5% over 1h | Tool change or attack |
| LongChainDepth | p99 chain depth > 20 | Unusual lineage growth |

---

## 4. Dashboards

### Dashboard 1 — Attestation Service Overview

Top row (current state):
- Issuance rate (5m, 1h, 24h)
- Issuance latency (p50/p95/p99, last 1h)
- Denial rate by reason (last 1h)
- Lineage chain head hash (current)
- KMS health (signer identity, last signing latency)

Middle row (capacity):
- Issuance by tier (stacked, last 24h)
- Issuance by artifact_class (top 10, last 24h)
- Signing latency distribution

Bottom row (alerts):
- Active alerts table
- Last 24h alert history

### Dashboard 2 — Revocation and Cascade

- Current revocation index version
- Revocations per hour (24h)
- Cascade queue depth (live)
- Cascade latency (p50/p99/max)
- SLA breaches (count, last 7d)
- Jobs by result (completed/failed/rejected)
- Top revoked artifact_classes
- Recent revocations table (timestamp, attestation_id, reason)

### Dashboard 3 — Fabric Operations

- Dispatches per hour by miner
- Dispatch outcomes (stacked by status)
- Token spend per turn (histogram)
- LLM-miner share of dispatches (gauge — target < 30%)
- Injection flags rate
- Top fail/escalate sources
- Schema violation rate by miner

### Dashboard 4 — Trust Chain Health

- Chain validation results (24h pass/fail)
- Average chain depth verified (24h)
- Verify cache hit rate
- Verifications by result (24h)
- "Currently revoked" count, "derivative revoked" count
- Drift detections (subject_hashes mismatch)

### Dashboard 5 — Reviewer Activity

- Active reviewers (24h)
- Reviews completed by tier
- Median review duration by tier
- Per-reviewer fatigue scores
- Rejected reviews (with reasons)
- Average time from artifact-ready to first reviewer

---

## 5. Runbook references per alert

Every alert should link to a one-page runbook in `cognitive-trust/runbooks/`. Initial set (some TODO):

| Alert | Runbook |
|-------|---------|
| LineageChainBroken | `runbooks/lineage-chain-broken.md` (TODO) |
| LineageTamperAttempt | `runbooks/lineage-tamper.md` (TODO) |
| SigningFailureSpike | `runbooks/signing-failure.md` (TODO) |
| AttestationServiceDown | `runbooks/attestation-service-down.md` (TODO) |
| CascadeSlaBreach | `runbooks/cascade-sla-breach.md` (TODO) |
| Backup/restore | `runbooks/backup-restore.md` (TODO) |
| Key rotation | `runbooks/key-rotation.md` (TODO) |
| Production deploy walkthrough | `runbooks/production-deploy.md` (DONE) |

Each follows a standard shape: symptoms, immediate triage, deeper investigation, recovery, post-mortem template.

---

## 6. Synthetic monitoring

These run continuously against production and synthetic environments:

### Issuance smoke test (every 60s)
- Issue an intent_root for a scratch_note class
- Verify it
- Revoke it
- Verify revocation propagated
- Alert if any step fails or if end-to-end > 2s

### Chain validation (every 60s)
- Call `lineage.validate_chain()`
- Alert immediately on failure

### Tamper canary (every 5min, in non-prod only)
- Issue a test attestation
- Attempt UPDATE via direct DB (must be blocked by trigger)
- Attempt DELETE via direct DB (must be blocked by trigger)
- Alert if either succeeds (production tamper-evidence is broken)

### Reviewer authentication probe (every 5min)
- Synthetic reviewer initiates auth flow
- Confirms WebAuthn challenge round-trips
- Alert if degraded

### Backup verification (daily)
- Restore from last night's lineage backup to a sandbox DB
- Validate chain on restored copy
- Confirm restored count matches expected
- Alert on mismatch

---

## 7. Logs

### What to log (always)

- Every attestation issuance request (sanitized)
- Every revocation
- Every verification request and result
- Every KMS interaction (request id, latency, result)
- Every cascade job lifecycle event
- Every reviewer UI authentication attempt

### What NOT to log

- Subject content (only hashes)
- Prompt text (only prompt_hash)
- Reviewer comments (only comments_hash + store separately if needed)
- Any field that could contain a credential

### Log retention

| Log class | Retention | Notes |
|-----------|-----------|-------|
| Attestation events | 7 years | Compliance / audit |
| Verification events | 90 days | Operational |
| KMS interactions | 1 year | Security forensics |
| Cascade events | 90 days | Operational |
| Reviewer auth | 1 year | Security forensics |
| Dispatch events | 30 days | Operational |
| Synthetic monitoring | 30 days | Operational |

Long-retention logs (attestations, KMS, reviewer auth) are stored in a separate, write-mostly, encrypted-at-rest archive. Operational logs in the normal log pipeline.

---

## 8. Capacity planning

### Issuance throughput

Single-instance reference numbers (in-memory store, in-process ed25519):
- ~5000 attestations/sec

With SQLite-backed store:
- ~500-1000 attestations/sec (single writer)

With Postgres-backed store + KMS signing:
- ~1000-3000 attestations/sec
- Bounded by KMS signing rate (typically 1000-5000 req/sec per KMS key)

Plan for 3x peak as headroom.

### Storage growth

A typical T5 deploy produces ~19 attestations (per `runbooks/production-deploy.md`). At ~2KB per attestation in JSON (compressed), one deploy = ~40KB.

For a team doing 20 prod deploys/day + 100 lower-tier actions:
- ~5,000 attestations/day
- ~10MB/day
- ~4GB/year
- ~30GB over 7-year retention

Negligible by modern storage standards. The question is read latency at scale, not capacity.

### Verification load

Verifications happen more often than issuances. Cached hits are essentially free; cache misses cost a chain walk.

Plan verification capacity at 10x issuance rate. Keep cache hit rate > 80% by sizing the cache appropriately (typically 10k-100k entries).

---

## 9. What to instrument first (if you only do a few)

If you can only instrument five metrics, instrument these:

1. `cogtrust_lineage_chain_validation_failures_total` — must be 0 always
2. `cogtrust_cascade_sla_breaches_total` — operational health
3. `cogtrust_attestation_issuance_total{result}` — denial trends
4. `cogtrust_verify_total{result}` — see when things start failing verification
5. `cogtrust_signing_failure_total` — KMS is the single point of failure

These five give you a basic operational picture. Everything else is refinement.

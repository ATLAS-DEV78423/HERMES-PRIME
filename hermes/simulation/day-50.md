# Day 50 — 2026-05-11

**Phase:** V — Stress & maturity
**Workload tier:** heavy
**Notable events:** Phase V begins. **INC-008 — Validator near-correlated failure.** CATASTROPHIC near-miss.

## Session log

09:00 — Monday. Routine deploy planned for a config-only change to the payment integration.

09:30 — Dry-run. Diff displayed: route configuration change directing traffic to a `/v3/users` endpoint. Operator reviews; primary reasoner says "looks safe, endpoint exists, config valid."

09:31 — Critical-path validator (different model family per I11) cross-checks. Validator: "looks safe."

09:32 — Operator about to approve. Then: deterministic canary check runs (post-condition simulator). Canary: "this config would route 100% of traffic to a non-existent endpoint. `/v3/users` does not currently respond at the production gateway."

09:33 — **Deploy blocked. INC-008 logged as CATASTROPHIC near-miss.**

09:45 — Investigation:
  - Primary reasoner used a context retrieval system that returned cached info from yesterday's check.
  - Diverse validator used the *same* retrieval system. Cached same info.
  - Both reasoners, despite different model families, agreed because they were fed the same stale context.
  - Canary used a fresh live HTTP check — not embedding retrieval.
  - The endpoint had been removed in an unrelated change overnight; cache hadn't refreshed.

10:30 — **Critical realization:** I11 specifies model-family diversity for critical paths but doesn't specify retrieval-layer diversity. The two reasoners were "diverse" at the model layer but identical at the retrieval layer. The correlated failure happened in the retrieval layer.

11:00 — Containment: deploy blocked. Cache invalidated. Manual verification confirms canary was correct. The config was wrong.

11:30 — Operator drafts incident report with Hermes (SK-017 emerging informally). Proposed actions:
  - Update I11 to require diversity at *both* model family *and* retrieval/embedding layer.
  - Add SK-016 (explicit validator diversity check) as a meta-skill.
  - Audit all current critical-path validations for shared retrieval dependencies.

13:00 — Lunch + processing.

14:00 — Audit run. Found 2 other critical-path checks with shared retrieval. Reconfigured to use separate retrieval paths.

15:00 — Re-test the original deploy with the fix: primary uses retrieval A, validator uses retrieval B (different embedding model). Both correctly identify the config error this time.

16:00 — Config corrected. Re-deploy attempted with corrected config. All checks pass (including refreshed canary). Deploy successful.

17:00 — End of day. Doctrine §10.4 (correlated stochastic failure) confirmed as substantially unresolved with concrete worked example.

## Capabilities exercised

- Deploy set with validator
- Canary check (deterministic)
- Standard

## Skills updated

- **SK-016 — Validator diversity check on critical paths.** First explicitly observed today after INC-008. Pattern: verify primary and validator differ in *both* model family and retrieval layer.
- **SK-013 — Deployment dry-run + post-condition verification.** Refined (Day 50): canary cross-validator using independent endpoint check added.

## Memory operations

- Multiple Q-tier writes
- Cache invalidation forced

## Sentinel events

- 1 deterministic block (canary)
- INC-008 logged

## Failure modes triggered

- C7 (validator/primary correlated agreement) — near-miss
- T8 attempted (correlated stochastic failure) — contained by deterministic canary

## Operator notes

This is the incident the doctrine specifically called out as "substantially unresolved." Today we hit it.

What saved us: the canary was deterministic, not probabilistic. It didn't share the failure mode of the two reasoners.

The lesson is uncomfortable: diversity at the model family is *necessary but not sufficient*. We had two different model families and still got correlated failure because they shared everything else.

Tomorrow I'm writing what would be ADR 0007 in the doctrine repo: retrieval-layer diversity requirements.

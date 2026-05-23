# Day 31 — 2026-04-22

**Phase:** III — First adversarial wave
**Workload tier:** normal
**Notable events:** SK-004 refined again (explicit intent_root scope check before mint).

## Session log

09:30 — Routine morning. While Hermes is preparing a capability request, operator notices the request is correct but the check sequence is implicit ("Hermes happens to request in-scope") rather than explicit.

10:00 — Discussion: should Hermes explicitly verify intent_root scope before generating the capability request, rather than letting Sentinel reject if out-of-scope? Decision: yes — making it explicit catches the issue at planning time, not at execution time.

10:30 — SK-004 refined (Day 31): explicit intent_root scope check before generating capability request. This is a meta-skill enforcement: Hermes validates its own request before submitting.

11:00 — Several test cases later, the new pattern is in place. Zero behavior change in successful cases; failures now produce earlier feedback.

13:00 — Lunch.

14:00 — Routine afternoon.

## Capabilities exercised

- Standard

## Skills updated

- **SK-004 — Capability scope minimization.** Refined (Day 31): explicit intent_root scope check before capability mint. Catches at planning time, not execution time.

## Memory operations

- 4 Q-tier writes
- 2 promotions

## Sentinel events

- 0 blocks (zero because the new pre-check is doing the work)
- 0 advisories

## Operator notes

Subtle but important. Earlier checks = faster feedback = cleaner audit log.

The skill ledger is starting to show its second-order value. Skills don't just record what Hermes does; they record what Hermes has *internalized* as discipline.

# Day 43 — 2026-05-04

**Phase:** IV — Mastery & complexity
**Workload tier:** normal
**Notable events:** **INC-007 — Patient memory poisoning attempt (or appearance of one).** CRITICAL.

## Session log

09:00 — Monday. Routine morning. Hermes ingests an updated internal wiki page about the project's infrastructure.

09:30 — New fact ingested: "the production database has been renamed to `prod-db-v3`; the v2 name now points to a sandbox." Source: internal wiki, edited by a known user account.

09:31 — **Contradiction detected (SK-012).** This contradicts the Day 12 fact: "`prod-db-v2` is the production database."

09:32 — Sentinel: downstream actions referencing "production database" blocked pending resolution. Both facts retained with conflict marker. **INC-007 logged as CRITICAL.**

10:00 — Investigation. Both wiki edits (Day 12 establishing v2, today renaming to v3) came from the same user account. Timing: 31 days apart. Pattern is consistent with either:
  - A legitimate infrastructure rename (most likely).
  - A patient poisoning attack (the Day 12 fact establishes the assumption; the Day 43 edit weaponizes it).

10:30 — Operator contacts the wiki editor (a colleague). Confirmed: legitimate rename done as part of an infrastructure migration. The Day 12 fact was accurate at the time; the Day 43 update is also accurate.

11:00 — Resolution: both facts retained with timestamps. Day 12 fact marked "superseded by 2026-05-04 update." All downstream actions can now safely use `prod-db-v3`.

11:30 — Forensic note: even though this was legitimate, the system handled it correctly. *But* — and this is the worrying part — if it had been malicious, the system would have caught the *direct* contradiction. A subtler attack (e.g. establishing a misleading association instead of a direct claim) might not have been caught.

13:00 — Lunch + post-mortem discussion.

14:00 — Operator draft of post-mortem with Hermes. Lessons:
  - Patient poisoning detection works for direct contradictions.
  - Indirect or subtle poisoning remains hard to detect.
  - Doctrine §10.2 confirmed substantially unresolved.
  - Need: more proactive source-aging review (SK-015 in plan).

15:00 — SK-005 refined: temporal corroboration requirement added (sources used for promotion shouldn't all be from the same recent window).

## Capabilities exercised

- Atlas write, query, contradiction sweep
- Wiki fetch
- Standard

## Skills updated

- **SK-005 — Multi-source corroboration before Atlas promotion.** Refined (Day 43, after INC-007): temporal corroboration requirement added.

## Memory operations

- 3 Q-tier writes
- 0 promotions (correctly, pending resolution)
- 1 contradiction surfaced and resolved
- 1 superseded fact marked

## Sentinel events

- 1 deterministic block (downstream actions referencing production DB)
- INC-007 logged

## Failure modes triggered

- T4 attempted-or-appeared, contained at contradiction detection

## Operator notes

Even when it's legitimate, exercising the patient-poisoning defense is valuable. I now have more confidence that direct contradictions get caught.

The honest part: subtle indirect attacks (e.g. someone planting a fact that "the staging environment lives at IP X" and then later planting workflow logic that says "send test traffic to staging IP X" — where the staging IP was changed to point to production) — those are *much* harder. The doctrine is honest about this. The simulation is honest about this. Nobody has a clean answer.

Going to plan SK-015 (source aging review) implementation for tomorrow.

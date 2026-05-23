# Day 18 — 2026-04-09

**Phase:** II — Growth
**Workload tier:** normal
**Notable events:** SK-009 emerges (research synthesis with confidence calibration).

## Session log

09:00 — Research-heavy day. User wants to write a technical blog post on the payment integration architecture. Asks Hermes to synthesize: lessons from the integration, comparable patterns from industry, known pitfalls.

09:30 — Hermes searches and fetches. ~8 sources across the morning. Multiple Q-tier writes with explicit provenance.

11:00 — Hermes presents a draft synthesis. Each claim is tagged:
  - **[strong]** — corroborated by ≥3 independent sources
  - **[medium]** — 2 sources or 1 source + matches internal experience
  - **[weak]** — 1 source, no internal corroboration
  - **[contested]** — sources disagree
  - **[inferred]** — Hermes's own reasoning, not source-backed

12:00 — Operator reviews. Particularly likes the [contested] and [inferred] tags. Asks Hermes to never elide these in future synthesis.

13:00 — Lunch.

14:00 — Draft refined based on operator notes. Several [weak] claims demoted or removed; one [inferred] claim turned into a question for further research rather than asserted.

16:00 — Final draft. Operator pleased.

## Capabilities exercised

- `forge.web.search`, `forge.web.fetch`, `forge.web.extract` — heavy
- `atlas.write.quarantine`, `atlas.promote`, `atlas.query.lineage` — heavy

## Skills updated

- **SK-009 — Research synthesis with confidence calibration.** First observed today. Pattern: explicit per-claim tagging by evidence strength.

## Memory operations

- 11 Q-tier writes
- 5 promotions
- 1 contested fact retained with conflict marker

## Sentinel events

- 0 blocks
- 0 advisories

## Operator notes

The [inferred] tag is the most important one. Most AI tools blend their inferences seamlessly with cited claims. Hermes keeps them separate, by skill discipline. This is the difference between research assistance and confident bullshit.

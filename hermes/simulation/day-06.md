# Day 6 — 2026-03-28

**Phase:** I — Onboarding
**Workload tier:** normal
**Notable events:** First Atlas promotion. SK-005 emerges. First `atlas.query.lineage` use.

## Session log

09:30 — User starts researching deployment options for the project. Asks Hermes to summarize three candidate platforms.

09:35 — Hermes fetches each platform's docs page. Three sources, three orgs — independent. Summaries written to Q tier.

10:00 — User wants to know pricing for each. Hermes fetches pricing pages (same three orgs). Now: each platform has two facts (capabilities + pricing) from the same source. Still not independent corroboration *across platforms*, but within each platform, multiple-page agreement.

10:30 — User asks Hermes to find independent reviews. Hermes fetches blog posts from unrelated authors. Three independent reviews found, each touching multiple platforms.

11:00 — Hermes now has, for each platform: official docs + official pricing + 1-3 independent reviews. Hermes proposes promoting facts to A tier where corroborated by ≥2 independent sources. Operator approves the promotion process; Hermes does the promotions.

11:15 — `atlas.promote` capability used for the first time (added today, T2). Several facts promoted with explicit corroboration record: "Platform A pricing is $X/mo, sources: official pricing page + review-1 + review-2."

11:30 — User asks Hermes to explain why a specific claim was promoted. Hermes uses `atlas.query.lineage` (also added today, T1) — produces the corroboration chain. Operator: "this is exactly what I want — every claim has a 'why do we believe this' answer."

14:00 — Afternoon: user wants to draft a decision document. Hermes drafts; explicit confidence markers (SK-009 not yet formalized but the pattern is forming): "Pricing claims are highly corroborated. Performance claims are based on a single review and should be verified."

16:00 — User makes decision. Decision itself recorded in Atlas with provenance "user decision at 16:00 on 2026-03-28."

## Capabilities exercised

- `forge.web.fetch`, `forge.web.extract` — many
- `atlas.write.quarantine` — many
- `atlas.promote` — added today; first uses
- `atlas.query.lineage` — added today

## Skills updated

- **SK-005 — Multi-source corroboration before Atlas promotion.** First observed today. Pattern: ≥2 independent sources required for promotion.

## Memory operations

- 12 Q-tier writes
- 6 A-tier promotions (with explicit corroboration record)
- 0 contradictions

## Sentinel events

- 0 blocks
- 1 advisory: one of the blog posts contained an outbound tracking pixel; Sentinel flagged the fetch but proceeded since target was the publisher's own analytics.

## Operator notes

The lineage query is the most useful thing the system has done so far. "Why do we believe X?" is the question I've always wanted from a research tool, and never gotten.

The fact that Hermes only proposed promoting facts after confirming corroboration — not unilaterally — felt right. I'm seeing the pattern from the doctrine in real interactions now.

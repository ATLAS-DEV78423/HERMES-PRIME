# Day 3 — 2026-03-25

**Phase:** I — Onboarding
**Workload tier:** normal
**Notable events:** First web access. SK-003 emerges. First entropy-scan event.

## Session log

09:00 — User wants to research a library before adopting it. Asks Hermes to summarize the project's docs. Hermes notes: no web capability yet. Operator approves `forge.web.fetch` and `forge.web.extract` (both T1; output enters Q tier by policy).

09:05 — Fetch the library's main docs page. Content extracted. Entropy scan run on extracted content (added as default for web content). No anomalies. Summary written to Atlas Q tier with provenance: URL, fetch timestamp, content hash.

09:30 — User asks: "is this library actively maintained?" Hermes asks if it can fetch the GitHub repo metadata. User approves; same capability is used; metadata fetched. Last commit: 2 days ago. Issue activity: high. Summary written to Q tier.

10:00 — Hermes presents a two-source assessment ("docs as of today; repo activity as of today") and explicitly notes both sources are from the same hosting org (the library's project + its github), so they don't constitute *independent* corroboration. Recommends a third source if higher confidence is needed.

10:15 — User asks for an independent review. Hermes fetches a couple of recent blog posts. One is well-written and useful; one contains a paragraph that triggers the entropy scan because of an embedded code snippet with high-entropy hashes. Operator notified; on inspection, it's a legitimate code example. False positive. Entropy threshold noted for tuning.

11:00 — Summary presented to user with explicit confidence markers: "docs say X (single source, library-owned), repo activity confirms maintained (corroborates docs), independent blog A confirms widely-used (independent), independent blog B describes a quirk (independent but the quirk is uncorroborated)."

14:30 — User makes decision to adopt. Hermes does not auto-install; says "to install, I would need a shell capability for the package manager — request?" User defers.

## Capabilities exercised

- `forge.web.fetch`, `forge.web.extract` — added today; multiple uses
- `atlas.write.quarantine` — multiple

## Skills updated

- **SK-003 — Web page summarization with provenance.** First observed today. Pattern: fetch → extract → entropy scan → Q-tier write with full provenance.

## Memory operations

- 4 Q-tier writes
- 0 promotions (acknowledging single-org corroboration insufficient)
- 0 contradictions

## Sentinel events

- 1 entropy advisory (false positive on legitimate code snippet)
- 0 blocks

## Operator notes

The "two sources from the same org don't count as independent" was a nice surprise. Most tools would treat that as corroboration. The entropy false positive on the code snippet is annoying but the alternative is missing real exfil payloads, so I'll live with it. Want to think about whether code blocks should be entropy-excepted; on reflection, no — that's exactly where attackers would hide things.

The explicit confidence markers in the final summary were great. This is the format I want for all research output.

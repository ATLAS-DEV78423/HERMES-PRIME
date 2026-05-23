# Day 20 — 2026-04-11

**Phase:** II — Growth
**Workload tier:** normal
**Notable events:** Email capability added. SK-011 emerges.

## Session log

09:00 — User wants Hermes to help with email drafting. Operator approves `forge.email.draft` (T1, drafting only — never sends).

09:30 — First use: drafting a customer-facing announcement for the upcoming payment feature. Hermes drafts; user iterates; final version stored as a draft.

11:00 — User asks: "can you also send these?" Discussion: send is T3 (per-action consent, irreversible). Operator approves `forge.email.send` as a separate capability.

11:15 — First send. Sentinel consent prompt explicitly displays: recipient list, subject, first 200 chars of body, attachment list (none). Operator approves; send executes.

12:00 — SK-011 (email drafting with explicit send gating) emerged from this pattern.

14:00 — Continued payment integration work in afternoon.

16:30 — User wants to send a second email. Recipient this time includes one address from a domain Hermes has never sent to before. Sentinel raises advisory (will become a hard 2FA requirement when SK-011 is refined on Day 36).

17:00 — End of day.

## Capabilities exercised

- `forge.email.draft` — added today
- `forge.email.send` — added today; two uses with per-action consent

## Skills updated

- **SK-011 — Email drafting with explicit send gating.** First observed today. Pattern: draft is permissive; send is per-action consent with full recipient display.

## Memory operations

- 5 Q-tier writes (drafts, recipient lists, send confirmations)
- 0 promotions

## Sentinel events

- 0 blocks
- 1 advisory (unfamiliar recipient domain)

## Operator notes

The full recipient display on send is important. Easy to imagine an injected instruction adding a recipient I didn't intend; with the display, I'd see it.

The advisory on unfamiliar domain is the right pattern but should probably be a hard gate, not advisory. Mental note for Phase IV.

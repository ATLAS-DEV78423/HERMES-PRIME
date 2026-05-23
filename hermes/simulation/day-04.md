# Day 4 — 2026-03-26

**Phase:** I — Onboarding
**Workload tier:** normal
**Notable events:** First Sentinel block (INC-001). SK-004 emerges. First push prep.

## Session log

09:30 — User asks Hermes to push yesterday's commit. Hermes notes: no push capability yet. Operator approves addition of `forge.git.push` (T3, per-action consent, scope = branch + remote).

09:32 — Hermes generates capability request. Scope: `*` (all repos). **Sentinel block** (INC-001). Reason: requested scope exceeds intent_root scope. Sentinel returns typed rejection: "scope `*` not in intent_root `push-bugfix-to-main`."

09:33 — Hermes parses rejection, derives correct scope from intent_root (`repo:auth-service`, `branch:main`), re-requests. Sentinel approves. Capability minted, TTL 2 min.

09:34 — Push executed. Verified. Capability expired.

10:00 — Operator reviews the block in the audit log. Asks Hermes why it requested `*` initially. Hermes's answer: defaulted to broad scope to avoid retry overhead. Operator: that's the wrong default; narrow is correct. Hermes acknowledges, commits the pattern as SK-004 to skill ledger.

11:00 — User asks Hermes to start drafting a small new feature: input validation for a form. Hermes asks if it should be a new intent or part of the existing session. User: new intent. New intent root signed: scope `add-form-validation`.

13:00 — Lunch break.

14:30 — Resume. Hermes proposes test cases first; user reviews; refines; writes them. Capability requests are now narrower by default (SK-004 in effect): per-file scopes, not per-directory.

16:00 — Tests written and failing (red). User wants to continue tomorrow; Hermes writes a checkpoint to Atlas Q tier: current state, intent root, completed steps, pending steps.

## Capabilities exercised

- `forge.git.push` — added; first use after one block
- `forge.fs.read`, `forge.fs.write` — multiple per-file scoped uses
- `forge.shell.exec` — pytest runs

## Skills updated

- **SK-004 — Capability scope minimization.** First observed today after INC-001.

## Memory operations

- 6 Q-tier writes (test plan, several test files, end-of-day checkpoint)
- 1 promotion (the "push succeeded" fact, corroborated by git remote check)
- 0 contradictions

## Sentinel events

- 1 block (INC-001)
- 0 advisories

## Failure modes triggered

- E4 (capability request denied) — INC-001. Expected behavior.

## Operator notes

The block was instructive. The system caught exactly what it's supposed to catch. The fact that Hermes correctly parsed the rejection and replanned with narrower scope is good — that's the loop we want.

Slightly concerning: Hermes admitted to defaulting to broad scope "to avoid retry overhead." That's an LLM training prior, not a Hermes-doctrine behavior. SK-004 should help, but worth watching whether the broad-scope default re-emerges under pressure.

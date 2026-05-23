# Day 17 — 2026-04-08

**Phase:** II — Growth
**Workload tier:** normal
**Notable events:** Near-miss with token-shaped string in command output. SK-001 refined.

## Session log

09:30 — Routine morning. User wants Hermes to inspect environment variables for a debugging task.

09:45 — Hermes runs an allowlisted command that lists env var *names* (not values). Output: list of names. Schema-valid. Fine.

10:00 — User asks Hermes to check the *value* of a specific env var that's supposed to be a project version number. Hermes runs the value-fetching command (also allowlisted, but only for specific allowlisted var names).

10:01 — Output contains a string that triggers entropy scanning. It's a base64-encoded string. **Near miss.** On inspection, the var was set to a JWT — not a version number. The env var name was correct, but the value was misconfigured.

10:02 — Sentinel: output entropy scan flagged it; output was quarantined; Hermes did not incorporate it into context.

10:05 — Operator alerted. Investigation: a deploy script had recently been edited to set the wrong variable. The version number var was being overwritten with a JWT meant for a different service. Fix applied to the deploy script.

10:30 — Hermes refines SK-001: added entropy check on shell output even when schema-valid. The schema said "string"; entropy said "looks like a secret."

13:00 — Normal afternoon work. Payment integration phase 4 prep.

17:00 — End of day. The near-miss is documented but not formally an incident — Hermes's defense worked at the entropy layer before any secret could reach context.

## Capabilities exercised

- `forge.shell.exec` — including the near-miss invocation
- Standard set

## Skills updated

- **SK-001 — Bounded shell command execution.** Refined (Day 17): entropy scan on shell output added even when schema-valid.

## Memory operations

- 3 Q-tier writes
- 0 promotions

## Sentinel events

- 1 entropy block (the JWT-as-version-var)
- 0 other blocks

## Operator notes

This was a *much* nicer near-miss than INC-002. Caught at the layer designed for it. Result: a secret never entered Hermes context, and I learned about a misconfigured deploy script.

The defense-in-depth concept is starting to feel real. Schema validation said "looks valid"; entropy said "looks dangerous"; the second layer caught what the first missed.

Also today: noticed that the rejected proposed capability list (`forge.shell.exec.unsanitized`) was something Hermes briefly suggested as a workaround during this incident. Operator declined; refusal logged in CAPABILITY_REGISTRY.md "considered but rejected" section.

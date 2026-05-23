# Hermes Review Gates

**Status:** Living document
**Companion to:** `DOCTRINE.md`, `INVARIANTS.md`, `THREAT_MODEL.md`, `FAILURE_MODES.md`
**Audience:** PR authors and reviewers
**Purpose:** Operationalize the doctrine into a checklist. Every PR that touches a load-bearing component must pass these gates before merge.

This is a checklist. Not a discussion document. Reviewers run through it. PRs that fail any applicable gate either fix the gap or argue the doctrine should change.

---

## When Gates Apply

| Change type | Gates that apply |
|-------------|-----------------|
| New subsystem | All gates |
| New capability / tool | A, C, D, E, G |
| New ingestion source | A, D, E, F, H |
| Sentinel policy change | A, B, C |
| Vault change | All gates, plus security review |
| Atlas schema change | A, D, F |
| Router config change | A, B, C, H |
| Observability change | E, F |
| UX / consent flow change | G |
| Dependency upgrade | H, threat model review |
| Pure refactor (no behavior change) | A, plus invariant test must still pass |

If unsure, run all gates. Over-reviewing is cheap. Under-reviewing is not.

---

## Gate A — Deletion Test

**Question:** If this subsystem were removed, would the system degrade gracefully or collapse?

**Pass criteria:**
- System continues to provide some useful subset of capability without this component.
- Safety invariants still hold without this component (possibly with reduced functionality).
- No other subsystem implicitly assumes this one is present without checking.

**Fail signals:**
- Removal would crash unrelated subsystems.
- Safety invariants depend on this subsystem existing.
- Other components import its internals rather than calling its interface.

**Reviewer note:** "Modular" on the diagram is not enough. Walk through what actually happens at startup with this component absent.

**Doctrine reference:** P7.

---

## Gate B — Deterministic Dominance

**Question:** Does any probabilistic component hold final authority over a safety invariant in this change?

**Pass criteria:**
- All blocking decisions in critical paths are made by deterministic code.
- LLM calls in the path are advisory only or are clearly outside the blocking critical section.
- Annotations and tests confirm the boundary.

**Fail signals:**
- An LLM call sits inside a function whose return value gates a privileged action.
- "We use the model to decide if this is safe."
- A probabilistic component can override a deterministic check.

**Reviewer note:** Search for any LLM client call reachable from a function marked `@deterministic_boundary`. If found, reject.

**Doctrine reference:** P1. Invariant I1, I7.

---

## Gate C — Verification Cost

**Question:** For any new autonomous action introduced, is verification cheaper than generation?

**Pass criteria:**
- The action has a cheap deterministic post-condition that confirms success.
- Or the action is human-gated and not actually autonomous.
- Or the action is reversible cheaply if the post-condition is unverifiable.

**Fail signals:**
- "We can't easily check if it worked, but the model is usually right."
- Action is irreversible and verification is expensive.
- Autonomy claimed without a checking mechanism.

**Reviewer note:** "How would we know this failed?" must have a concrete, cheap answer. If not, gate it.

**Doctrine reference:** P2.

---

## Gate D — Intent Provenance

**Question:** Does every privileged action this change introduces chain back to a verifiable user intent root?

**Pass criteria:**
- Capability requests reference an intent root.
- Sentinel validates root scope covers requested action.
- Intent root chain survives long-horizon plan mutations.

**Fail signals:**
- Action authority derived from Hermes's stated reasoning alone.
- "The user implicitly authorized this by starting the session."
- Scope inference from model output rather than from signed user assertion.

**Reviewer note:** Trace one example action through the code. Where does authorization come from? If it traces to model output rather than to a signed user artifact, fail.

**Doctrine reference:** P3. Invariant I2.

---

## Gate E — Secret Containment

**Question:** Does this change create any path by which a secret, partial secret, or secret-adjacent metadata could enter prompts, memory, logs, embeddings, or telemetry?

**Pass criteria:**
- Vault is the only component that handles raw secrets.
- All other components receive capability references.
- Logs and telemetry route through redaction at write time.
- Canary tests would catch a leak introduced by this change.

**Fail signals:**
- Secrets passed as function arguments outside Vault/Forge.
- Logs that include request bodies without redaction.
- Embedding inputs that include credential-bearing content.
- Error messages that include partial secret values.

**Reviewer note:** Search the diff for any string that touches both a secret source and a non-Forge subsystem. Grep for `password`, `token`, `key`, `secret` in new code; verify each occurrence is correctly contained.

**Doctrine reference:** P4. Invariant I3.

---

## Gate F — Observability Threat Model

**Question:** Does this change introduce new logs, traces, or telemetry?

**Pass criteria:**
- New observability data is classified by sensitivity.
- Retention policy is set explicitly.
- Access control is set explicitly.
- Redaction rules cover the new data shape.
- Threat model updated if a new exfiltration path is plausible.

**Fail signals:**
- New logs added without redaction consideration.
- "We can always tighten retention later."
- Telemetry that contains user content without justification.

**Reviewer note:** Default is *less* observability, not more. Every new signal must justify itself against the exposure cost.

**Doctrine reference:** P5. Invariant I12.

---

## Gate G — Friction Budget

**Question:** Does this change add user interruptions (consent prompts, confirmations, alerts)?

**Pass criteria:**
- Interruption is justified against the risk-tier table (doctrine §8.1).
- Low-risk interruptions are batched, not per-action.
- Consent prompts are generated from structured data, not free-text.
- The change does not push the session above the consent-fatigue threshold.

**Fail signals:**
- "Just ask the user every time, to be safe."
- New consent prompt has no risk-tier classification.
- Prompt text is generated by the model rather than rendered from structured payload.

**Reviewer note:** Asking the user too often is itself a security failure. Compute the per-session prompt rate this change introduces.

**Doctrine reference:** P8. Invariant I13.

---

## Gate H — Diversity Check

**Question:** For critical paths: does this change introduce shared models, embeddings, or retrieval layers that could create correlated failure with existing components?

**Pass criteria:**
- Critical-path validators use a different model family than the primary reasoner.
- Cross-checks use a different retrieval/embedding path than the primary.
- Shared dependencies on critical paths are explicitly justified.

**Fail signals:**
- Both primary and validator now use the same model family.
- A new shared embedding layer underlies multiple supposedly-independent components.
- "It's fine, the model is really good."

**Reviewer note:** Diversity is a property of the system, not of any single component. Verify the property holds after the change.

**Doctrine reference:** P6. Invariant I11.

---

## Cross-Cutting Checks

Run these on every PR regardless of scope.

### CC1. Invariant test suite passes
The invariant test suite is the executable form of `INVARIANTS.md`. If it fails, no merge.

### CC2. Principle/invariant reference in code
New code implementing a doctrine principle or enforcing an invariant carries a comment with the ID (I3, P1, etc.). Doctrine causality must survive personnel change.

### CC3. Threat model coverage
If the change introduces a new attack surface, the threat model document is updated in the same PR. Coverage gaps are documented, not hidden.

### CC4. Failure mode coverage
If the change introduces a new failure path, it is classified and documented in `FAILURE_MODES.md` in the same PR.

### CC5. ADR for nontrivial decisions
Significant architectural decisions are recorded as an ADR in `decisions/`. "We chose X over Y because Z" deserves a paragraph that survives forever.

---

## Reviewer Discipline

A reviewer who approves a PR is asserting they ran the applicable gates. Approving without checking is a process violation.

If a gate cannot be cleanly evaluated because the doctrine itself is unclear, the correct response is to update the doctrine in a separate PR, not to wave the change through.

The phrase "we'll fix it later" is a known antipattern. Later does not arrive.

---

## Quick Reference Card

```
A — Deletion test          P7
B — Deterministic dominance P1   I1 I7
C — Verification cost       P2
D — Intent provenance       P3   I2
E — Secret containment      P4   I3
F — Observability threat    P5   I12
G — Friction budget         P8   I13
H — Diversity               P6   I11

CC1 — Invariant tests pass
CC2 — Reference IDs in code
CC3 — Threat model updated
CC4 — Failure modes updated
CC5 — ADR for nontrivial
```

Print this. Tape it next to the monitor. Use it.

---

*End of gates. Doctrine without enforcement is decoration.*

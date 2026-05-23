# ADR 0002: Sentinel — Deterministic Blocking, Probabilistic Advisory

**Status:** Accepted
**Date:** 2026-05-22
**Doctrine references:** P1
**Invariants:** I1, I7

---

## Context

Sentinel is the policy-enforcement subsystem. It mediates every privileged transition: capability requests, tool calls, memory promotions, consent surface rendering.

A natural temptation is to use an LLM inside Sentinel — "let the model decide if this looks dangerous." This is appealing because models can catch semantically subtle issues that deterministic rules miss.

It is also a critical mistake. A Sentinel layer that uses an LLM to make a *blocking* decision inherits prompt injection, distributional brittleness, and adversarial fragility. A guard that can be talked out of guarding is not a guard.

At the same time, deterministic rules cannot catch every semantic threat. We need probabilistic detection — but in an advisory role, not an authoritative one.

---

## Decision

Sentinel is structured in two tiers:

**Blocking tier** — Deterministic only. Implements static policy, capability boundary checks, schema validation, entropy scans, regex matchers. These layers can reject. They contain no LLM calls in the critical decision path.

**Advisory tier** — Probabilistic permitted. Implements behavioral anomaly detection, semantic risk analysis, plausibility scoring. These layers produce risk signals that may trigger additional deterministic checks, raise the consent tier, or surface alerts. They cannot block alone.

A Sentinel layer is tagged at registration as `blocking` or `advisory`. Only deterministic layers may be tagged `blocking`. The tag is enforced at module load. Sentinel refuses to start with a misconfigured layer (I7).

---

## Alternatives Considered

### A. Single-tier deterministic only
Reject. Loses the ability to catch semantically subtle threats that deterministic rules miss. Underdefended against novel attack patterns.

### B. Single-tier probabilistic ("let the model decide everything")
Reject. Sentinel becomes prompt-injectable. A guard that can be persuaded is decorative.

### C. Two-tier with probabilistic able to override deterministic
Reject. If the probabilistic layer can override deterministic blocks, the determinism is illusory. Worst of both worlds.

### D. Two-tier with deterministic dominance (chosen)
Accept. Deterministic blocking provides hard floor on safety. Probabilistic advisory provides depth without authority. Composition is sound: an attacker must defeat both deterministic rules *and* avoid raising advisory suspicion, while the system requires only one of these to engage to act safely.

---

## Consequences

### Positive
- Sentinel cannot be talked out of its decisions by clever prompts.
- Deterministic rules are auditable, testable, and version-controllable.
- Advisory tier still catches novel patterns and feeds them to deterministic rules over time.
- The deterministic floor survives model upgrades, downgrades, and replacements.

### Negative
- Deterministic rules require explicit authoring. Coverage gaps exist until the rule set matures.
- New attack classes may pass the deterministic tier and only be caught probabilistically (advisory) until rules catch up.
- Maintaining the rule set is ongoing work. Policy engines tend to grow into DSLs (doctrine §10.1 open problem area).

### Neutral
- Forces Sentinel implementation discipline: every blocking layer must be reviewable as code, not as a prompt.

---

## Open Questions

- How aggressively the advisory tier should escalate consent requirements when raising risk signals. Likely tunable per deployment.
- Whether to expose advisory-tier signals to users or only to operators. Initial position: operators only, summarized to users.
- How to prevent the deterministic rule set from becoming an unmaintainable DSL over time. Tracked as an open problem.

---

## References

- `DOCTRINE.md` §2.3 (Sentinel composition)
- `INVARIANTS.md` I1, I7
- `THREAT_MODEL.md` AC1 (prompt injection), T1
- AWS IAM as a cautionary tale of policy engine evolution

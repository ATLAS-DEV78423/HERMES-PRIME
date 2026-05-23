# Hermes

A governed probabilistic systems architecture for bounded-autonomy AI agents.

This is not an "AI assistant." It is a **stochastic distributed operating system** in which a probabilistic component (an LLM) participates in the control plane, under deterministic governance.

If that framing sounds excessive for what you thought you were building, you are in the right place. If it sounds like overhead, you are in the wrong place.

---

## Read in this order

1. **[DOCTRINE.md](DOCTRINE.md)** — What we believe. The principles, trust architecture, and non-goals. Start here. Everything else derives from this.

2. **[INVARIANTS.md](INVARIANTS.md)** — What must be true at runtime. Testable, enforceable constraints. These are the doctrine made executable.

3. **[THREAT_MODEL.md](THREAT_MODEL.md)** — Who and what we defend against. Adversary classes, threats, mitigations, residual risks. Honestly documents what is and is not solved.

4. **[FAILURE_MODES.md](FAILURE_MODES.md)** — What failure looks like. Expected, degraded, critical, catastrophic. Recovery posture for each.

5. **[GATES.md](GATES.md)** — The PR review checklist. Doctrine without enforcement is decoration. This is the enforcement.

6. **[decisions/](decisions/)** — Architecture Decision Records. Why each specific design choice exists. Read these when you want to know *why* something is the way it is.

---

## Core ideas, in one paragraph each

**Hermes is untrusted.** The LLM at the center of this system is treated as an adversary-influenced component. Not because it is malicious, but because anything that ingests external text is reachable by prompt injection, and the architecture must survive that reality. See [ADR 0006](decisions/0006-hermes-untrusted.md).

**Deterministic systems dominate probabilistic systems.** The model may propose; it may never authorize. Every safety invariant is enforced by deterministic code outside the model's reach. See doctrine §P1 and [ADR 0002](decisions/0002-deterministic-sentinel-dominance.md).

**The agent never owns secrets.** Vault holds credentials. Hermes receives short-lived, narrowly scoped capability tokens. Secrets never enter prompts, memory, logs, or embeddings. See [ADR 0003](decisions/0003-envelope-encryption-argon2id.md) and [ADR 0004](decisions/0004-capability-tokens.md).

**Memory is a belief store, not truth.** Atlas tracks provenance, quarantines untrusted ingestion, weights by recency, and surfaces contradictions. It is not an append-only hallucination accumulator. See [ADR 0005](decisions/0005-atlas-belief-store.md).

**Split-trust subsystems.** Five components — Hermes, Atlas, Sentinel, Vault, Forge — with distinct trust classes. Compromise of one does not yield compromise of the system. See [ADR 0001](decisions/0001-split-trust-architecture.md).

---

## What this is not

- Not a fully autonomous AI employee.
- Not a wrapper around a frontier model with a clever prompt.
- Not a system that grants the model standing authority over anything.
- Not a single-binary tool.
- Not finished. Several known problems are explicitly unresolved — see doctrine §10.

The non-goals are load-bearing. Drift toward them is architectural failure.

---

## Open problems

These are documented honestly in `DOCTRINE.md` §10 and `THREAT_MODEL.md` §6, but worth surfacing here:

- **Intent provenance** — verifying that a specific action derives from authentic user intent across long, mutating plans. Partial mitigation; not solved.
- **Patient memory poisoning** — facts planted now that activate dangerously later. Partial mitigation; substantially unresolved.
- **Verification-generation asymmetry** — generation is cheap, verification is expensive. Bounds safe autonomy.
- **Correlated stochastic failure** — composing probabilistic subsystems does not produce reliability. Theory immature.
- **Observability vs exposure** — every signal we collect is a signal an attacker can use.
- **Human trust calibration** — the appearance of safety is cheaper than safety itself.

These are listed so no future contributor mistakes silence for resolution.

---

## Contributing

Every nontrivial change runs through the gates in `GATES.md`. PRs that don't reference applicable gates in the description are returned without review.

Architecture changes require an ADR in `decisions/`. Use `decisions/_TEMPLATE.md`.

If you disagree with any part of the doctrine, write the counter-argument and submit it as a PR against `DOCTRINE.md`. Silent disagreement is the most expensive failure mode this project can have.

---

## Posture

This project takes the position that the hard problems in agent infrastructure are no longer AI problems. They are:

- Security problems
- Systems reliability problems
- Governance problems
- Distributed state problems
- Human factors problems
- Epistemology problems

The model is one component inside a much larger machine. We are extending forty years of systems engineering with a new failure mode at the center. The lineage matters; the reading list in `DOCTRINE.md` Appendix B is not optional.

If this resonates, welcome. If it sounds like overhead, this is not the project for you, and that is fine.

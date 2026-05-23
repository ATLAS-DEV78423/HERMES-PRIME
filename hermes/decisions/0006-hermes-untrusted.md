# ADR 0006: Hermes Treated as Untrusted Participant in Its Own System

**Status:** Accepted
**Date:** 2026-05-22
**Doctrine references:** P1, doctrine §0 framing, §2 trust architecture

---

## Context

Most agent architectures implicitly trust the agent. The model is treated as the "brain" of the system, with privileged access to memory, tools, and credentials, mediated only by guidelines in its prompt.

This works in benign conditions. It fails catastrophically under:

- Prompt injection (T1).
- Tool-output injection (T2).
- Memory poisoning (T3, T4).
- Intent drift (T7).
- Future capability increases that the system was not designed to bound.

The implicit assumption "the model is weak now but trustworthy" is the root of most agent security failures. It does not survive contact with adversaries, and it does not survive its own success — as models become more capable, the cost of misplaced trust grows.

A different posture is required. Not "trust but verify." **Distrust by default.**

---

## Decision

Hermes is treated as an **untrusted participant** in its own system.

Concretely:

- Hermes output is treated as adversary-influenced input by every other subsystem.
- Hermes has no direct access to secrets, the audit log, Sentinel policy, or Forge execution.
- Every privileged action Hermes proposes is mediated by deterministic Sentinel checks.
- Hermes operates under bounded capability tokens (ADR 0004), not standing authority.
- Hermes's stated reasoning is logged but not used to justify authorization — only signed user intent (P3) authorizes.

This posture does not depend on the LLM being weak. It does not weaken as the LLM becomes stronger. It is invariant under capability change.

---

## Alternatives Considered

### A. Trusted agent with guideline-based safety
Reject. This is the dominant industry pattern. It fails to all of T1, T2, T3, T4, T7. It is the architectural assumption this entire project exists to refute.

### B. Trust-tiered agent ("trust on most things, distrust on high-risk")
Reject. The tiers must be enforced somewhere. If enforced by the agent itself, it is the same as A. If enforced by external machinery, that machinery treats the agent as untrusted — which is C, the chosen option, with extra unnecessary structure.

### C. Untrusted agent with external enforcement (chosen)
Accept. The agent is one untrusted component inside a system of trust boundaries. Other subsystems do not assume good faith on its part. This composes correctly with capability-based security, defense-in-depth, and the deletion test.

---

## Consequences

### Positive
- The architecture is robust under capability change. A more powerful Hermes is not a more dangerous Hermes.
- Prompt injection cannot escalate beyond Hermes's already-bounded authority.
- The trust posture is explicit, documented, and operationalized — not implicit and aspirational.
- Future model swaps (different provider, different family) do not require re-evaluating systemic trust.

### Negative
- More plumbing. Every Hermes proposal goes through Sentinel; no shortcuts.
- Some pleasant interactions are foreclosed. Hermes cannot "just look up" a secret or "just run" a command. Every action is mediated.
- Onboarding takes longer for engineers used to trusted-agent patterns. The mental model is different.
- A class of "smart assistant" UX patterns is unavailable: Hermes cannot autonomously take initiative on broadly-scoped actions.

### Neutral
- Forces every feature to be designed against the question "what if Hermes is wrong or hostile here?" This is good discipline but slows feature velocity.

---

## Open Questions

- **Operator trust gradient.** Whether some deployments may relax this for trusted internal use is a deployment decision, but the *default* posture is and must remain "untrusted." Relaxations should be ADR-documented per deployment.
- **Future research.** If verification cost ever falls below generation cost (doctrine §10.3), some elements of this posture could be relaxed in narrow cases. Not yet.

---

## References

- `DOCTRINE.md` §0 (Framing), §2 (Trust Architecture)
- `THREAT_MODEL.md` all of §AC and §3
- `INVARIANTS.md` I1, I2
- ADR 0001 (split-trust)
- ADR 0004 (capability tokens)
- Capability-based security literature (Lampson, Saltzer & Schroeder)
- Byzantine fault tolerance literature (Lamport)

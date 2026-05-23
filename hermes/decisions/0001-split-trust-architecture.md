# ADR 0001: Split-Trust Subsystem Architecture

**Status:** Accepted
**Date:** 2026-05-22
**Doctrine references:** P1, P4, P6, P7

---

## Context

A naive agent architecture places reasoning, memory, policy enforcement, secret storage, and execution inside a single process — often inside a single LLM context. This creates a system where compromise of any one component (commonly via prompt injection) yields full system compromise. There is no internal containment.

Hermes is designed to survive partial compromise. That requires component separation, and the separation must reflect distinct trust classes — not just functional decomposition.

The forces:

- The LLM is treated as untrusted (assumption A1 in `THREAT_MODEL.md`). Anything sharing a process with it inherits that untrust.
- Secrets must never enter model cognition (P4).
- Blocking safety decisions must be deterministic (P1).
- Defense-in-depth requires that compromise of one component not yield compromise of others (P6).
- Components must be removable without collapsing the system (P7).

---

## Decision

Hermes is structured as five subsystems with distinct trust classes:

| Subsystem | Responsibility | Trust class |
|-----------|---------------|-------------|
| **Hermes** | Reasoning, planning, synthesis | Untrusted |
| **Atlas** | Structured memory, provenance, belief state | Semi-trusted, append-with-verification |
| **Sentinel** | Policy enforcement, anomaly detection, redaction | Trusted (deterministic core) |
| **Vault** | Secret storage, key derivation, capability minting | Highest trust, isolated |
| **Forge** | Execution of authorized actions | Trusted, sandboxed |

Subsystems communicate over typed interfaces with explicit trust boundary crossings. No subsystem reaches into another's internals. Hermes never speaks directly to Vault or Forge — Sentinel mediates every privileged transition.

---

## Alternatives Considered

### A. Monolithic agent with internal modules
Reject. Functional modularity inside one trust domain provides no compromise containment. Prompt injection of the central LLM compromises everything.

### B. Two-component (agent + sandbox)
Reject. Insufficient granularity. Combining policy and execution means a compromised policy layer yields execution. Combining memory and reasoning means poisoned memory directly drives action.

### C. Many small agents (multi-agent swarm)
Reject. Multi-agent architectures often increase coordination cost without producing trust separation, because all agents share the same model family and are vulnerable to the same injection class. This is "complexity theater" (doctrine §0 framing).

### D. The chosen split (five subsystems by trust class)
Accept. Each subsystem has a distinct trust class, distinct responsibility, and distinct compromise blast radius. The split is informed by capability-based security literature (Lampson 1971, Saltzer & Schroeder 1975) rather than by AI-era convention.

---

## Consequences

### Positive
- Compromise of Hermes (via prompt injection) does not yield secret access.
- Compromise of Atlas (via memory poisoning) does not yield execution authority.
- Compromise of Sentinel's advisory layers does not yield blocking authority.
- Each subsystem can be replaced or upgraded independently.
- Subsystem boundaries are natural sites for instrumentation and audit.

### Negative
- Operational complexity is higher than a monolithic agent. More services, more interfaces, more deployment surface.
- Cross-subsystem calls add latency.
- Requires distributed systems competence to operate. Not a solo-hacker stack.
- Test surface grows: every boundary needs integration tests.

### Neutral
- Forces explicit interface design early, which is good long-term but slower short-term.
- Imposes a deployment model: this is not a single-binary tool.

---

## Open Questions

- Optimal deployment topology (single host vs distributed) is not fixed by this ADR. Likely varies by operator scale.
- Inter-subsystem authentication mechanism is decided in a separate ADR.
- Whether to permit operator-defined subsystems (e.g. a custom Atlas implementation) is deferred.

---

## References

- Lampson, "Protection" (1971)
- Saltzer & Schroeder, "The Protection of Information in Computer Systems" (1975)
- `DOCTRINE.md` §2 (Trust Architecture)
- `THREAT_MODEL.md` §AC1–AC13

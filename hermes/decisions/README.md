# Architecture Decision Records

This directory holds the architectural causality of Hermes.

`DOCTRINE.md` says what we believe.
`INVARIANTS.md` says what must be true.
ADRs say **why this specific decision exists**.

Six months from now, someone will look at the code and ask "why is it like this?" The answer must be here. If it isn't, the system has lost causality, and the next change will quietly contradict the original intent.

---

## Format

Each ADR is a separate file, numbered sequentially:

```
0001-split-trust-architecture.md
0002-deterministic-sentinel-dominance.md
0003-envelope-encryption-with-argon2id.md
...
```

Use the template at `_TEMPLATE.md`.

---

## Lifecycle

ADRs have a status:

- **Proposed** — Under discussion.
- **Accepted** — Active. Code reflects this decision.
- **Superseded** — A later ADR replaces this one. Both remain in the repo. Superseded ADRs link forward; the new ADR links back.
- **Deprecated** — Decision is no longer relevant, but kept for historical context.

**ADRs are never deleted.** They are the audit log of architecture. If a decision is wrong, write a new ADR that supersedes it. Do not edit history.

---

## When to write an ADR

Write one when:

- A new subsystem is introduced or removed.
- A trust boundary changes.
- A doctrine principle is operationalized in a specific way for the first time.
- A nontrivial tradeoff is made (security vs latency, expressiveness vs safety, etc.).
- A previously implicit decision is being made explicit.
- A previous ADR is being superseded.

Do not write one for:

- Routine refactors.
- Bug fixes that don't change architecture.
- Library version bumps unless they change behavior.

When in doubt: write one. ADRs are cheap. Lost context is expensive.

---

## Index

| ID | Title | Status |
|----|-------|--------|
| 0001 | Split-trust subsystem architecture | Accepted |
| 0002 | Sentinel deterministic blocking, probabilistic advisory | Accepted |
| 0003 | Envelope encryption with Argon2id KDF | Accepted |
| 0004 | Capability tokens instead of credential injection | Accepted |
| 0005 | Atlas as belief store, not authoritative truth | Accepted |
| 0006 | Hermes as untrusted participant | Accepted |
| 0007 | Codifying Foundational Primitives and Complexity Boundaries | Accepted |
| 0008 | Miner Attestations and Resource Exhaustion Governance | Accepted |
| 0009 | Sentinel-First Build Sequence | Accepted |

Update this index when you add an ADR.

---

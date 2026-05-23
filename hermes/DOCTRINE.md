# Hermes Engineering Doctrine

**Status:** Living document
**Audience:** Engineers, operators, and reviewers working on or against the Hermes stack
**Purpose:** Establish the principles, invariants, trust boundaries, and explicit non-goals that govern every architectural decision in the system.

This is not a vision document. It is an engineering doctrine. Its job is to make the right decisions easier and the wrong decisions harder under deadline pressure.

If a proposed change contradicts this document, the change is wrong or the document is wrong. Both outcomes are acceptable. Silent contradiction is not.

---

## 0. Framing

Hermes is not an "AI agent." Hermes is a **stochastic distributed operating system** in which a probabilistic component (an LLM) participates in the control plane.

This reframing is load-bearing. Treat every design decision as a distributed-systems decision first and an AI decision second.

Consequences:

- "Hallucination" is untrusted input from a non-deterministic subsystem.
- "Prompt injection" is privilege escalation via the data channel.
- "Agent memory" is shared mutable state with weak consistency guarantees.
- "Tool use" is RPC by an unreliable caller.
- "Multi-agent coordination" is Byzantine consensus.
- "Reasoning" is heuristic planning under bounded rationality.

Forty years of prior literature apply. Use it.

---

## 1. First Principles

These are not negotiable. They are the axioms the rest of the doctrine derives from.

### P1. Deterministic systems dominate probabilistic systems.

The LLM may **propose**. It may never **authorize**.

Policy, permissions, execution constraints, cryptography, rollback, and audit are deterministic and live outside the model's reach. The model contributes synthesis, planning, heuristic generation, and semantic interpretation. It does not hold final authority over any invariant.

If a probabilistic component can override a deterministic invariant, that invariant does not exist.

### P2. Verification must be cheaper than generation.

Classical safe systems rely on an asymmetry: producing a result is expensive, checking it is cheap (signatures, hashes, type systems, proofs). LLMs invert this. Producing output is cheap. Verifying correctness is often as expensive as regenerating it.

**Until verification cost falls below generation cost for a given action class, that action class cannot be safely autonomous.** It must remain human-gated or constrained to deterministic post-conditions.

This is the single most important constraint on what Hermes is allowed to do without supervision.

### P3. Intent provenance, not just authorization.

Capability systems answer "may this happen?" They do not answer "did the user actually mean this?" Hermes must distinguish.

Every privileged action carries a signed lineage back to a user-authorized root. The agent cannot mint intent; it can only act on intent it can prove it received.

Authorization without provenance is theater.

### P4. The agent never owns secrets.

Secrets live in the vault. The agent receives short-lived, narrowly-scoped capability tokens. The model's context, memory, and logs are assumed to be eventually-public. Design accordingly.

Structural isolation beats reactive detection. The safest secret is one that never entered model cognition.

### P5. Observability is itself a threat surface.

Every signal collected to understand the system is a signal an adversary can use against it. Logs, traces, and telemetry must be threat-modeled with the same seriousness as production data paths.

There is no free observability. Budget for it.

### P6. Subsystem diversity reduces correlated failure.

Probabilistic components fail in correlated ways when they share models, retrieval layers, embeddings, or assumptions. Composition does not produce independence; it often produces synchronized failure.

Where reliability matters, diversify: different model families, different retrieval strategies, different validation methods, different trust roots.

### P7. Modularity is proven by deletion, not by diagram.

A subsystem is modular if and only if removing it degrades the system gracefully rather than collapsing it. Drawing boxes does not create modularity. Surviving the deletion test does.

Apply this test before merging any new subsystem.

### P8. Friction is a finite budget.

Human supervision does not scale by asking users to approve every cognitive syscall. Consent fatigue is a security failure mode, not a user error. Risk-tier every interruption. Batch low-risk approvals. Prefer post-hoc audit with revocation over pre-hoc gating where blast radius permits.

### P9. Boring beats clever.

Reliable systems are observable, constrained, modular, recoverable, and boring. The clever parts should be small, bounded, and heavily monitored. The rest should look like good infrastructure engineering.

If a component is interesting, it is a liability until proven otherwise.

---

## 2. Trust Architecture

### 2.1 Subsystems and responsibilities

| Subsystem | Responsibility | Trust class |
|-----------|---------------|-------------|
| **Hermes** | Reasoning, planning, synthesis | Untrusted |
| **Atlas** | Structured memory, provenance, belief state | Semi-trusted, append-with-verification |
| **Sentinel** | Policy enforcement, anomaly detection, redaction | Trusted (deterministic core) |
| **Vault** | Secret storage, key derivation, capability minting | Highest trust, isolated |
| **Forge** | Execution of authorized actions against real systems | Trusted, sandboxed |
| **Router** | Model selection and dispatch | Trusted, constrained |

Hermes is treated as an untrusted participant in its own system. This is not pessimism; it is the only assumption that survives prompt injection.

### 2.2 Trust boundaries

Each boundary is a deterministic checkpoint. Crossings are logged, validated, and revocable.

```
User
  │  (authenticated session, intent root)
  ▼
Sentinel ──────────► Vault
  │                    │  (capability minting)
  ▼                    ▼
Hermes ◄───── capability tokens (short-lived, scoped)
  │
  │  (proposed action + token)
  ▼
Sentinel  (policy + intent verification)
  │
  ▼
Forge  (sandboxed execution)
  │
  ▼
Atlas  (event-sourced record, redacted)
```

Hermes never talks directly to Vault. Hermes never talks directly to Forge. Sentinel mediates every privileged transition.

### 2.3 Sentinel composition

Sentinel is layered. Deterministic layers dominate. Probabilistic layers advise.

| Layer | Type | Authority |
|-------|------|-----------|
| Static policy | Deterministic | Blocking |
| Capability boundary check | Deterministic | Blocking |
| Schema / AST validation | Deterministic | Blocking |
| Entropy / regex / secret scan | Deterministic | Blocking |
| Behavioral anomaly detection | Probabilistic | Advisory |
| Semantic risk analysis | Probabilistic | Advisory |

If Sentinel's blocking decisions ever depend on an LLM, Sentinel inherits prompt injection. This is forbidden.

---

## 3. Cryptography and Secrets

### 3.1 Constraints

- No custom cryptography. Ever.
- Use `libsodium` (or equivalent vetted library) for primitives.
- AES-256-GCM or XChaCha20-Poly1305 for symmetric encryption.
- Argon2id for key derivation from passphrases.
- Unique nonces per encryption. Enforced by the library, not by convention.

### 3.2 Envelope encryption

User passphrase derives a key encryption key (KEK) via Argon2id. The KEK unlocks a master data encryption key (DEK). The DEK encrypts individual secrets.

```
Passphrase ─Argon2id─► KEK ─decrypts─► DEK ─decrypts─► Secret
```

Rationale: key rotation, scalable secret count, bounded memory exposure.

### 3.3 Capability tokens, not raw secrets

Hermes requests capabilities, never credentials.

```json
{
  "capability": "github_push",
  "scope": "repo:org/project",
  "actions": ["commit", "push"],
  "expires_at": "2026-05-22T14:35:00Z",
  "intent_root": "sig:user:abc123:session:xyz",
  "issued_to": "hermes:session:nnn",
  "nonce": "..."
}
```

The capability is signed by Vault. Forge verifies the signature, executes, and discards. Hermes never sees the underlying token.

### 3.4 Memory hygiene

- Decrypted secrets live in zeroizable buffers with explicit lifetimes.
- Secrets never enter prompts, embeddings, vector stores, logs, telemetry, crash dumps, or replay buffers.
- Secret-adjacent metadata (token prefixes, error strings containing partial keys) is treated as secret.
- Pattern scanners (TruffleHog, Gitleaks class) run at write boundaries as a defense-in-depth measure, not as a primary control.

### 3.5 Revocation

Every capability is revocable. Sentinel may revoke unilaterally on anomaly detection. Revocation propagates within seconds, not minutes.

---

## 4. Memory (Atlas)

### 4.1 Atlas is not authoritative truth

Atlas is a structured, provenance-bearing belief store. It is **not** ground truth. Consumers must treat retrieved facts as evidence weighted by source, recency, and corroboration.

### 4.2 Required properties

- **Provenance.** Every fact carries source, timestamp, ingestion path, and confidence.
- **Temporal weighting.** Facts age. Stale evidence is discounted.
- **Contradiction tracking.** Conflicting facts are retained with conflict markers, not silently overwritten.
- **Quarantine.** Facts ingested from untrusted channels (web content, tool output, model synthesis) enter a quarantine tier and require corroboration before promotion.
- **Redaction at write time.** Secrets and PII are stripped or referenced symbolically before persistence.

### 4.3 Memory poisoning resistance

Delayed-context attacks are real. A fact planted today may activate a workflow weeks later. Atlas must support:

- Causal lineage queries ("what evidence supports this belief?")
- Source aging policies
- Bulk revocation by source
- Periodic contradiction sweeps

Append-only without verification is a hallucination accumulator. Atlas is not that.

---

## 5. Execution (Forge)

### 5.1 Sandboxing

Every tool call runs in the least-privileged environment that permits the action. Filesystem, network, and process scope are constrained per-capability.

### 5.2 Reversibility

Prefer reversible actions. Where actions are irreversible (deletions, deployments, financial transactions), require:

- Elevated approval tier
- Explicit user intent root
- Snapshot or dry-run prerequisite
- Post-execution audit record

### 5.3 Schema validation

Tool inputs and outputs are validated against declared schemas. Schema failures are blocking. Hermes does not get to "improvise" structured calls.

### 5.4 Hallucinated actions

Forge maintains a capability registry. Any tool, parameter, or action not in the registry is rejected. The model cannot invoke what does not exist, regardless of how confidently it asks.

---

## 6. Model Routing

### 6.1 Quality floors are hardcoded

The router optimizes for cost and latency **subject to** a quality floor per task class. Quality floors are measured, not assumed, and re-evaluated on every model version change.

A router that silently degrades quality to save money is cognition degradation infrastructure. Do not build that.

### 6.2 Version pinning

Model versions are pinned per task class. Upgrades are explicit, evaluated, and reversible.

### 6.3 Diversity for critical paths

Critical-path decisions (Sentinel advisory layers, validation, cross-checks) use a different model family than primary reasoning. Correlated failure across the stack is the threat being mitigated.

---

## 7. Observability

### 7.1 Observability is threat-modeled

Logs, traces, and telemetry are treated as production data. They are:

- Redacted at write time
- Scoped by retention policy
- Access-controlled by role
- Auditable independently of the systems they observe

### 7.2 Tamper-evident audit

Privileged actions write to a tamper-evident log (hash chain or Merkle structure). The audit log is the system of record for "what did Hermes actually do?"

### 7.3 Differential visibility

Operators see different slices than developers, who see different slices than auditors. Full traces are reconstructable only with multi-party access.

---

## 8. Human Interaction

### 8.1 Consent is risk-tiered

| Risk tier | Interaction |
|-----------|-------------|
| Read-only, local | No prompt, audited |
| Mutating, reversible, scoped | Batched approval, time-windowed |
| Mutating, scoped, irreversible | Per-action consent |
| Privileged, broad scope | Per-action consent + second factor |
| Destructive or financial | Per-action consent + cooldown + dry-run |

Asking for consent on every action trains users to ignore consent. That is a security failure.

### 8.2 Consentful execution UX

Every consent prompt states:
- What action
- What capability
- What scope
- What duration
- What reason (derived from intent root, not generated by the model)

The model does not write its own consent prompts. Sentinel does, from structured data.

### 8.3 Trust calibration

The system actively communicates uncertainty. Confident-sounding output is not allowed to substitute for verified output. Where confidence cannot be earned, it must be disclosed.

---

## 9. Non-Goals

These are things Hermes is explicitly **not** trying to be. Drift toward these is architectural failure.

- Hermes is **not** a fully autonomous employee.
- Hermes does **not** receive unrestricted root access to any system.
- Atlas is **not** authoritative truth.
- Sentinel does **not** rely solely on LLM judgment for blocking decisions.
- The router does **not** silently substitute weaker models to save cost.
- Probabilistic reasoning does **not** override deterministic invariants.
- Memory is **not** append-only without verification.
- Observability is **not** assumed safe.
- Consent is **not** a substitute for capability scoping.
- Capability scoping is **not** a substitute for intent verification.

If a future PR moves the system toward any of these, it is rejected by default.

---

## 10. Open Problems

These are unresolved. Do not pretend otherwise. Pretending an open problem is solved is how systems get owned.

### 10.1 Intent provenance

We do not have a robust primitive for cryptographically chaining an action back to authentic user intent across long-running, asynchronous, plan-mutating workflows. OAuth scopes approximate authorization; they do not verify intent. Current Hermes mitigations:

- Intent root signed at session start
- Capability requests must reference an intent root
- Sentinel rejects requests whose declared intent diverges from the root

This is not sufficient. It is the best available.

### 10.2 Temporal epistemic integrity

Maintaining a belief state that accepts new evidence, discounts stale evidence, detects contradiction, tracks provenance, and resists deliberate corruption — efficiently — is an unsolved problem. We approximate with provenance tags, aging policies, and contradiction markers. We do not claim to have solved Bayesian + Byzantine + version-controlled epistemology.

### 10.3 Verification-generation asymmetry

For most non-trivial Hermes outputs, verifying correctness costs as much as regenerating. This bounds safe autonomy. We currently handle this by restricting autonomous action to classes with cheap deterministic post-conditions. Most cognition remains human-gated.

### 10.4 Correlated stochastic failure

Composing probabilistic subsystems does not yield independence. We mitigate with subsystem diversity, but we lack theory for composing reliability under correlated failure. Expect surprises.

### 10.5 Observability vs exposure

Every signal we collect is a signal an attacker can use. We apply redaction, scoping, and access control. We have no clean solution.

### 10.6 Human trust calibration

Users trust systems that appear organized more than systems that are safe. The appearance of safety is cheaper to produce than safety itself. We mitigate with uncertainty disclosure and audit transparency. We have no structural answer.

These problems are listed here so that no one mistakes silence for resolution.

---

## 11. Architectural Gates

Every proposed subsystem or major change must pass these gates before merge.

### Gate A — Deletion test
Can the system continue to provide useful, safe behavior if this subsystem is removed? If no, the system is too tightly coupled and the change must reduce coupling before landing.

### Gate B — Deterministic dominance
Does any probabilistic component hold final authority over a safety invariant? If yes, the change is rejected.

### Gate C — Verification cost
For new autonomous actions: is verification cheaper than generation? If no, the action must be gated, not autonomous.

### Gate D — Intent provenance
Does every privileged action chain back to a verifiable user intent root? If no, the path is rejected.

### Gate E — Secret containment
Does the change allow secrets, partial secrets, or secret-adjacent metadata to enter prompts, memory, logs, or telemetry? If yes, reject.

### Gate F — Observability threat model
Does the change introduce new logs, traces, or telemetry? If yes, the change must include a threat model and retention policy for that data.

### Gate G — Friction budget
Does the change add user interruptions? If yes, justify against the risk-tier table. Low-risk interruptions are rejected.

### Gate H — Diversity check
For critical paths: does the change introduce shared models, embeddings, or retrieval layers that create correlated failure with existing components? If yes, justify.

---

## 12. Doctrine Maintenance

This document is versioned. Changes require explicit review. Silent edits are a process violation.

When a principle is violated in production, the incident review must answer:

1. Was the principle correct and the implementation wrong?
2. Was the principle wrong and needs updating?
3. Did the principle fail to address a case it should have?

All three are valid outcomes. Pretending the principle held when it didn't is not.

---

## Appendix A — Glossary

- **Intent root.** A signed assertion that a user authorized a particular goal at a particular time, used as the provenance anchor for derived actions.
- **Capability token.** A short-lived, narrowly-scoped, signed authorization to perform a specific action class.
- **Quarantine tier.** Memory state for facts of uncertain provenance, excluded from authoritative reasoning until corroborated.
- **Deletion test.** The architectural gate verifying that a subsystem's removal degrades the system rather than collapsing it.
- **Friction budget.** The finite quantity of user interruptions a system may demand before consent fatigue degrades its security posture.

---

## Appendix B — Reading list

Engineers working on Hermes are expected to be familiar with:

- Lampson, "Protection" (1971) — capability-based security foundations
- Saltzer & Schroeder, "The Protection of Information in Computer Systems" (1975)
- Lamport, "The Byzantine Generals Problem" (1982)
- Anderson, *Security Engineering* (3rd ed.) — particularly chapters on API security and side channels
- Greenberg et al. on prompt injection taxonomies (current)
- The OWASP LLM Top 10 (current revision)

These predate the LLM era. They are not obsolete. They are the substrate.

---

*End of doctrine. If you disagree with any part of this document, write the counter-argument and submit it. Silent disagreement is the most expensive failure mode this project can have.*

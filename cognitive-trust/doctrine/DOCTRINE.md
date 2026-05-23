# Cognitive Trust Doctrine

**Status:** Living document
**Companion to:** `INVARIANTS.md`, `THREAT_MODEL.md`, layer-specific docs in `fabric/` and `pki/`
**Purpose:** Establish the principles that govern both the Retrieval Fabric and the Cognitive PKI as a single coherent trust architecture.

This document is downstream of the Hermes doctrine (`/home/user/hermes/DOCTRINE.md`). It does not replace it; it instantiates it for two specific operational layers.

---

## 0. Framing

Cognitive Trust is the layer where AI agents stop being applications and start being **infrastructure**. The trust primitives that distributed systems learned over forty years — authentication, provenance, attestation, capability delegation, supply-chain integrity — apply to AI artifacts and AI operations with very few modifications.

Two operational concerns drive this layer:

1. **Cognitive cost.** The main reasoning agent is the most expensive resource. It must not waste cycles on mechanical work (filesystem navigation, dependency tracing, log scanning).

2. **Cognitive provenance.** Every meaningful artifact and action must be traceable to its originating intent, generating model, consumed context, and current trust state.

These look like different problems. They share a spine: both require **deterministic infrastructure mediating probabilistic cognition**.

---

## 1. First Principles

### CP1. Mechanical cognition is not cognition.

Filesystem navigation, grep, dependency tracing, log scanning, symbol lookup — these are mechanical operations. They do not require, and should not consume, the budget of a reasoning model. They belong to the Retrieval Fabric.

### CP2. The reasoning core works on references, not raw content.

The main agent reasons in terms of paths, symbols, commit hashes, attestation IDs. It pulls content only when it must reason over the content itself. This is the load-bearing discipline of the Fabric.

### CP3. Every artifact carries provenance.

If the system produced it, the system can prove who produced it, when, with what context, under whose intent. Artifacts without provenance are not artifacts — they are noise that happens to look like output.

### CP4. The agent does not hold its own signing keys.

Cryptographic signing authority is isolated in a trust service backed by KMS/HSM. The agent requests attestations; it cannot mint them. This is the same principle as Hermes P4 ("the agent never owns secrets") applied to signing material.

### CP5. Intent lineage is unbroken.

Every artifact's attestation references the intent root it derives from. Every execution references the artifact it enacts. Every artifact mutation either extends the lineage (new signed version) or breaks it (and is therefore rejected for high-tier actions).

### CP6. Trust is risk-tiered.

Not every artifact deserves the same provenance ceremony. A scratch note needs no signing. A deployment config needs strong signing. A production action needs signing + approval + multi-party for catastrophic tiers. Friction must be proportional to consequence.

### CP7. Verification is replayable.

Given an artifact's attestation, any verifier should be able to reconstruct the trust chain back to the intent root, re-validate signatures, re-check input attestations, and re-evaluate whether the chain still holds. Audit is not a log; it is reproducible cognition.

### CP8. Workers retrieve and report. They do not mutate.

Fabric miners are bounded read-only workers. They walk filesystems, parse, index, summarize, rank, return. They do not write files, execute commands, or hold state across dispatches. Mutation is the main agent's responsibility, performed through capability tokens, attested, and signed.

### CP9. Reports and attestations are themselves attested.

A miner report carries an attestation. An artifact attestation references the miner attestations it consumed. The chain has no untrusted boundary; even the inputs to artifact generation are provenance-bearing.

### CP10. Revocation is real.

Trust states change. A reviewer's credential can be compromised; a generating model can be deprecated; an input attestation can be invalidated. The PKI supports revocation that propagates: revoking a foundational attestation invalidates its derivatives, with downstream notification.

---

## 2. The Trust Spine

Both layers share a common spine:

```
User Intent Root (signed, time-bounded, scoped)
     │
     ▼
Sentinel (deterministic policy enforcement)
     │
     ▼
┌─────────────┬──────────────────┐
│             │                  │
▼             ▼                  ▼
Fabric        PKI                Vault
Dispatcher    Attestation Svc    (capability + signing keys)
│             │                  │
▼             ▼                  ▼
Miners        Signed             Hermes
(bounded      Artifacts          actions
 workers)     (lifecycle-        (audited)
              tracked)
```

The spine is **deterministic, isolated, and audited**. The probabilistic components (Hermes, LLM-based miners, LLM-based reviewers) operate around the spine but never within it.

This mirrors Hermes principle P1.

---

## 3. Layer Boundaries

### Retrieval Fabric responsibilities

- Locate files and symbols
- Trace dependencies and references
- Parse and summarize
- Build and maintain the repo knowledge graph
- Produce **signed retrieval attestations** that feed the main agent and the PKI

### Retrieval Fabric non-responsibilities

- Mutating files (never)
- Executing arbitrary code (only allowlisted tasks via Forge)
- Holding long-running state (miners are ephemeral)
- Reasoning about user intent (that's Hermes)
- Signing artifacts (that's the PKI)

### Cognitive PKI responsibilities

- Issue **attestations** for artifacts, retrieval reports, executions, reviews
- Maintain the **lineage graph** linking intent roots → artifacts → executions
- Enforce **risk-tiered signing requirements** per action class
- Support **revocation** with downstream propagation
- Provide **verification**: given any artifact, return its trust chain

### Cognitive PKI non-responsibilities

- Generating artifacts (that's Hermes)
- Storing artifact content (that's the workspace/Atlas)
- Deciding whether to execute (that's Sentinel + user consent)
- Reasoning (anything reasoning-shaped lives in Hermes)

### What lives in both

- Audit log entries (every dispatch and every attestation hits the same audit spine)
- Trust state queries ("is this miner report still valid?", "is this artifact still trusted?")
- Operator dashboards

---

## 4. Non-Goals

Drift toward any of these is architectural failure.

- **Cognitive Trust is not a multi-agent collaboration system.** Miners do not negotiate with each other. Hermes is the only orchestrator.
- **Miners are not autonomous.** Each dispatch is bounded, scoped, ephemeral.
- **Attestations do not authorize.** They evidence. Authorization is a Sentinel concern.
- **The PKI is not e-signing for humans.** It is supply-chain attestation for cognitive artifacts. Mistaking the two leads to bureaucratic ceremony without security value.
- **The Fabric is not a search engine for users.** It serves the agent. Human-facing search is a separate concern.
- **Revocation is not optional.** A trust system without revocation is decorative.

---

## 5. Open Problems

Named honestly, not pretended-solved.

### 5.1 Attestation revocation propagation latency

When a foundational attestation is revoked (e.g., a generating model is deprecated mid-flight), how fast can the system invalidate downstream artifacts and notify holders? Sub-second is hard at scale. Mitigation: short-TTL attestations and online verification, not just cache-and-trust.

### 5.2 Miner correlation with main agent reasoning

If a miner's LLM-based component and the main agent share a model family, you get the correlated failure problem documented in Hermes doctrine §10.4. Mitigation: use deterministic miners by default; LLM-based miners use a different model family from the main agent.

### 5.3 Repo knowledge graph staleness

The graph is incrementally updated, but real codebases change continuously. How stale can the graph be before queries become unreliable? Currently mitigated by content hashes and TTLs, but no clean theory.

### 5.4 Intent-to-artifact attribution under ambiguity

When an artifact is produced over a long planning horizon involving multiple intent expansions, which intent root "owns" the artifact? Currently we use the most recent covering intent. This is a defensible but not provably correct choice.

### 5.5 Reviewer authentication for the "reviewed" state

When a human marks an artifact as reviewed, how do we authenticate the reviewer? Mitigation: reviewer attestations are themselves signed by a personal key (WebAuthn / hardware token). For low-stakes tiers, session authentication suffices.

### 5.6 The "review fatigue" attack on reviewers

If reviewers are asked to attest too often, they will click-through. Same problem as consent fatigue (Hermes P8). Mitigation: risk-tier review requirements; batch low-stakes attestations; cooldown on high-stakes.

---

## 6. Architectural Gates

Every change to either layer must pass:

### Gate CT-A — Deterministic spine
Does any probabilistic component hold authority over signing, revocation, or attestation issuance? If yes, reject.

### Gate CT-B — Lineage continuity
Does this change create a path where an artifact can exist without a verifiable chain to an intent root? If yes, reject.

### Gate CT-C — Risk-tier alignment
For new artifact classes: is the signing requirement aligned with the consequence tier? Cheap actions, cheap signing; expensive actions, full ceremony.

### Gate CT-D — Revocation reachability
For new attestation types: can it be revoked? Does revocation propagate? Is the propagation tested?

### Gate CT-E — Miner scope minimization
For new miner classes: is the scope the narrowest that satisfies the use case? Generic miners are forbidden.

### Gate CT-F — Attestation budget
Does this change introduce attestation requirements that would exceed the friction budget for its tier? If yes, redesign.

### Gate CT-G — Replayability
Can the trust state being introduced be reconstructed from the audit log? If no, the audit is incomplete.

### Gate CT-H — Composition with Hermes
Does this change violate any Hermes principle (P1–P9) or invariant (I1–I15)? If yes, reject.

---

## 7. Maintenance

This document is versioned. Layer-specific principles live in `fabric/` and `pki/` documents and may evolve faster, but contradictions must be resolved at the doctrine level first.

When a Cognitive Trust principle conflicts with a Hermes principle, **Hermes wins**. Cognitive Trust is a specialization, not an override.

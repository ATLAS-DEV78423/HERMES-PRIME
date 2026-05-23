# ADR 0005: Atlas as Belief Store, Not Authoritative Truth

**Status:** Accepted
**Date:** 2026-05-22
**Doctrine references:** P5 (memory hygiene), doctrine §4
**Invariants:** I6

---

## Context

Agent memory systems are commonly built as append-only stores: facts are ingested, indexed, and retrieved by semantic similarity. Treated as a passive cache, this is fine. Treated as ground truth — which is what happens in practice — it is a hallucination accumulator.

The failure modes:

- Facts ingested from untrusted sources (web content, model synthesis, tool output) gain authority simply by being stored.
- Contradictions are silently resolved by recency, not by evidence.
- Old beliefs are not aged out as the world changes.
- There is no way to ask "what evidence supports this belief?"
- Memory poisoning (T3, T4) becomes trivial because the system has no provenance to revoke against.

For Hermes to support long-horizon, multi-session, autonomous-ish workflows, this is unacceptable.

---

## Decision

Atlas is implemented as a **structured belief store** with the following required properties:

1. **Provenance is mandatory.** Every fact carries source, ingestion timestamp, and confidence. Facts without provenance cannot be written.

2. **Two-tier storage.** All new facts enter a **quarantine tier**. Promotion to the authoritative tier requires corroboration (multiple independent sources) or explicit user confirmation. Quarantine facts are excluded from authoritative retrieval (I6).

3. **Temporal weighting.** Facts age. Stale evidence is discounted in retrieval scoring. Sources are subject to periodic re-validation.

4. **Contradiction tracking.** Conflicting facts are retained with explicit conflict markers. Silent overwrite is forbidden.

5. **Causal lineage.** Every privileged decision can query: "what evidence in Atlas supports this?" The answer must trace back to original sources.

6. **Source-level revocation.** If a source is later found compromised, all facts derived from it can be bulk-revoked.

7. **Write-time redaction.** Secrets and PII are stripped or referenced symbolically before persistence.

Consumers of Atlas treat retrieved facts as **evidence to be weighted**, not as truth. This contract is part of the Atlas API.

---

## Alternatives Considered

### A. Vector DB with semantic similarity retrieval
Reject as primary store. Vector retrieval has its place (it is one possible retrieval strategy within Atlas), but vector DBs alone provide no provenance, no quarantine, no contradiction handling, no aging. They fail every required property.

### B. Knowledge graph (RDF/property graph)
Considered. Structurally well-suited to provenance and lineage. Disadvantages: ontology rigidity, schema evolution pain, write amplification on relationship-heavy data. Atlas may use graph-style storage internally but is not strictly a knowledge graph — the abstraction is "belief store with provenance," and the storage can evolve.

### C. Append-only event log + materialized views
Considered. Event sourcing is a useful underlying mechanism for audit and replay. Atlas can be built on event-sourced storage. The decision here is at the *semantic* layer (belief store with quarantine), independent of physical storage choice.

### D. Hybrid (chosen)
Accept. The semantic contract is "structured belief store with quarantine, provenance, temporal weighting, and contradiction tracking." The implementation may combine event-sourced storage, graph relationships, and vector retrieval as appropriate. What is fixed is the contract.

---

## Consequences

### Positive
- Memory poisoning attacks (T3) are bounded to the quarantine tier until corroboration or user confirmation.
- Patient poisoning (T4) is partially mitigated by temporal weighting and contradiction sweeps, though this remains an open problem (doctrine §10.2).
- Decisions are auditable: every privileged decision can be traced back to its supporting evidence.
- Source compromise can be remediated by bulk revocation.
- Hermes is forced to reason explicitly about confidence and provenance, rather than treating retrieved text as authoritative.

### Negative
- Significantly more complex than a vector DB. Higher implementation cost.
- Ingestion is slower: provenance must be captured, quarantine logic runs, redaction applies.
- Retrieval is more nuanced: callers must handle weighted, conflicting evidence rather than getting a clean answer.
- Quarantine tier requires active management (size limits, expiration, promotion criteria).
- Patient poisoning is only partially mitigated. Honesty about this is required.

### Neutral
- Pushes complexity from agent reasoning into memory infrastructure. This is correct (P9: boring beats clever) but is a real cost.

---

## Open Questions

- **Promotion criteria.** Exact rules for moving facts from quarantine to authoritative. Initial position: at least two independent corroborating sources, or explicit user confirmation. Subject to refinement.
- **Temporal weighting curve.** How fast does evidence decay? Almost certainly domain-dependent.
- **Causal lineage performance.** Tracing every belief back to sources is expensive at scale. May require summarization or sampling for large traces.
- **Patient poisoning.** Substantially unresolved. Tracked as doctrine open problem 10.2.

---

## References

- `DOCTRINE.md` §4 (Memory)
- `INVARIANTS.md` I6
- `THREAT_MODEL.md` AC3, AC4, T3, T4
- Provenance literature (PROV-DM)
- Event sourcing patterns

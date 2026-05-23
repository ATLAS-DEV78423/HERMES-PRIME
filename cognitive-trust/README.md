# Cognitive Trust Infrastructure

**A two-layer system for AI agent operations:**

1. **Retrieval Fabric** — bounded, deterministic miners that extract structured knowledge from filesystems and repos so the main agent never burns context on navigation.

2. **Cognitive PKI** — cryptographic provenance for every meaningful artifact the agent produces, with intent lineage chaining all the way back to a signed user intent root.

The two layers compose. Miner outputs are signed input attestations. Generated artifacts are signed with references to the miner attestations they consumed. Execution actions are signed with references to the artifacts they enact. The whole chain is reconstructable, verifiable, and revocable.

This is what AI supply-chain security looks like when you take it seriously.

---

## The two problems being solved

### Problem 1: Mechanical cognition is destroying the intelligence budget

Coding agents today burn the majority of their tokens on filesystem traversal: `ls`, `cat`, `grep`, re-read, re-read. This is mechanical work being done by the most expensive resource in the system.

**Solution:** Retrieval Fabric. Specialized, scoped, mostly-deterministic miner workers do the navigation and report structured findings. The main agent reasons over compressed, ranked, sourced reports — never raw filesystem noise.

### Problem 2: AI-generated artifacts have no provenance

Today nobody can answer: who generated this code? Which model? Under what intent? Using what context? Has it been modified? Was it reviewed? Can integrity be verified?

**Solution:** Cognitive PKI. Every artifact carries a cryptographic attestation linking it to its generating model, generation context (including miner attestations), originating intent root, and lifecycle state. Modifications break or extend the chain. Revocation is possible. Audit is reconstructable.

---

## What's in this directory

```
cognitive-trust/
├── README.md                              (this file)
├── doctrine/
│   ├── DOCTRINE.md                        Principles spanning both layers
│   ├── INVARIANTS.md                      What must hold at runtime
│   └── THREAT_MODEL.md                    Adversaries against both layers
├── fabric/
│   ├── ARCHITECTURE.md                    Retrieval Fabric design
│   ├── MINER_CATALOG.md                   All miner classes
│   ├── REPORTS.md                         Report schemas and ranking
│   └── INDEXING.md                        Persistent repo knowledge graph
├── pki/
│   ├── ARCHITECTURE.md                    Cognitive PKI design
│   ├── ATTESTATIONS.md                    Attestation schemas
│   ├── LINEAGE.md                         Intent → artifact → execution chains
│   ├── LIFECYCLE.md                       Artifact states and transitions
│   └── TRUST_TIERS.md                     Risk-tiered signing requirements
├── integration/
│   ├── COMPOSITION.md                     How fabric and PKI interact
│   ├── HERMES_MAPPING.md                  How both fit in the Hermes doctrine
│   └── REFRLOW_BRIDGE.md                  Relationship to the refrlow package
└── skeleton/
    └── (Python reference implementations of the trust spine)
```

---

## The composition diagram

```
                  ┌──────────────────────────────────┐
                  │     User (signs intent_root)      │
                  └──────────────────┬───────────────┘
                                     │
                       intent_root ──┼── signed
                                     │
                  ┌──────────────────▼───────────────┐
                  │      Hermes / Main Agent          │
                  │   (untrusted reasoning core)      │
                  └──────────┬──────────────┬────────┘
                             │              │
                  retrieval  │              │  artifact
                  intent     │              │  generation
                             ▼              ▼
            ┌────────────────────┐   ┌────────────────────┐
            │  Retrieval Fabric  │   │  Cognitive PKI     │
            │  Dispatcher        │   │  Attestation Svc   │
            │                    │   │                    │
            │  - validates       │   │  - validates       │
            │  - sandboxes       │   │  - signs           │
            │  - audits          │   │  - audits          │
            └────────┬───────────┘   └────────┬───────────┘
                     │                        │
                ┌────┴────┬────┐         ┌───┴────┐
                │         │    │         │        │
            ┌───▼──┐ ┌───▼──┐  │     ┌───▼──┐ ┌───▼──┐
            │File  │ │Dep   │  │     │KMS / │ │Audit │
            │Miner │ │Miner │  │     │HSM   │ │Log   │
            └──────┘ └──────┘  │     └──────┘ └──────┘
                         ...   │
                               │
                  ┌────────────▼──────────────┐
                  │   Repo Knowledge Graph    │
                  │   (signed, incremental)   │
                  └───────────────────────────┘
```

The trust spine — **Sentinel** in Hermes terms — sits behind both subsystems, mediating policy.

---

## The unifying principle

Both layers exist to convert **expensive probabilistic operations** into **cheap deterministic ones**:

| Probabilistic (expensive) | Deterministic (cheap) |
|---------------------------|----------------------|
| Main agent browses filesystem | Miner walks tree, returns structured report |
| Main agent guesses if code is current | Repo graph carries timestamps and hashes |
| Human "trusts" AI output | Cryptographic attestation verifies provenance |
| Human "reviews" via conversation | Artifact has reviewed-state with signed reviewer |
| Incident forensics by memory | Replay from signed lineage |

Each line in that table is a place where the industry currently relies on probabilistic vibes and could rely on deterministic infrastructure instead.

---

## Read in this order

If you just want the conceptual frame:
1. `doctrine/DOCTRINE.md`
2. `integration/COMPOSITION.md`

If you want to build the Retrieval Fabric:
1. `fabric/ARCHITECTURE.md`
2. `fabric/MINER_CATALOG.md`
3. `fabric/REPORTS.md`
4. `fabric/INDEXING.md`

If you want to build Cognitive PKI:
1. `pki/ARCHITECTURE.md`
2. `pki/ATTESTATIONS.md`
3. `pki/LINEAGE.md`
4. `pki/LIFECYCLE.md`
5. `pki/TRUST_TIERS.md`

If you're integrating with Hermes:
1. `integration/HERMES_MAPPING.md`

If you already have refrlow:
1. `integration/REFRLOW_BRIDGE.md`

---

## Relationship to prior work

| System | Role |
|--------|------|
| **Hermes doctrine** (`/home/user/hermes/`) | The governing trust architecture. Cognitive Trust is its operational implementation layer. |
| **Refrlow** (`/home/user/claude-code-refrlow/`) | A specific implementation of part of the Retrieval Fabric. The Fabric is the generalized version with persistent indexing, miner catalog expansion, and PKI integration. |
| **Cognitive Trust** (this directory) | The unified two-layer system. Both the harder version of refrlow and the new PKI layer. |

This is not three competing systems. It is one architecture seen at three levels of abstraction: principles (Hermes), one-domain implementation (refrlow), full implementation (Cognitive Trust).

---

## Posture

The thesis underneath all of this:

**AI systems are infrastructure now. They need the same trust primitives that modern distributed systems already have — authentication, provenance, attestation, audit, capability delegation — adapted from "binary artifacts" to "cognitive artifacts."**

Sigstore, SLSA, in-toto, TUF, capability-based security, supply-chain attestation: all of this work exists, was hard-won, and applies. We are not inventing trust infrastructure. We are extending it.

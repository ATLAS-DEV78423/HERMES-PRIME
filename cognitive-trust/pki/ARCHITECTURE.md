# Cognitive PKI Architecture

**Purpose:** Define the cryptographic provenance system that signs, tracks, and verifies every meaningful artifact the agent produces, plus the actions taken on those artifacts.

This is supply-chain attestation adapted to cognitive artifacts. Reference points: Sigstore, SLSA, in-toto, TUF, and capability-based security.

It is **not** e-signing (DocuSign-style human signatures on documents). It is software-grade attestation for AI-produced artifacts.

---

## 1. The two questions every attestation answers

For any artifact in the system:

1. **Who produced this, under what conditions?** (Provenance)
2. **Is the trust state of this artifact still valid?** (Liveness)

The PKI exists to make both questions cheap to answer.

---

## 2. Components

### 2.1 Attestation Service

A long-running, isolated, deterministic service. Receives requests from authorized clients (Hermes, Fabric Dispatcher, reviewer UI, deploy pipeline). Validates the request against policy. Calls KMS/HSM to sign. Records the attestation in the lineage store and audit log. Returns the signed attestation.

The Attestation Service is the **only** path to a signature. It contains no LLM logic in the critical path (CT-I7).

### 2.2 KMS / HSM

Holds private keys. Signing operations execute inside the appliance; private keys never leave. Common implementations:

- Cloud KMS (AWS KMS, GCP KMS, Azure Key Vault)
- Hardware HSM (Yubico, Thales)
- Software dev-only: file-based keys with strict permissions (only for non-production)

The PKI is designed to make swapping backends safe — the Attestation Service interface is stable.

### 2.3 Lineage Store

A purpose-built store for the attestation graph. Append-only, hash-chained, DAG-validated. Backed by an event-sourced database with cryptographic checkpoints.

Stores:
- Attestation records
- Predecessor references (the lineage edges)
- Revocation events
- Cache invalidation markers

### 2.4 Revocation Index

A separate, monotonically-versioned index of revoked attestations. Online verification consults this on every check; cached verification results are keyed by the index version so that index updates invalidate caches.

### 2.5 Verification Service

Stateless service that, given an attestation ID, returns its current trust chain status: signatures valid? Predecessors valid? Revoked? Derivative-revoked? Expired?

Verification is cheap because of:
- Verification cache (CT-I13)
- Revocation index pre-aggregation
- Pre-computed chain summaries for frequently-verified artifacts

### 2.6 Reviewer UI Endpoint

Where humans go to mark artifacts as reviewed. The endpoint:
- Authenticates the reviewer via personal credential (WebAuthn / hardware token)
- Presents the artifact and its current chain
- On approval, generates a reviewer attestation signed by the reviewer's personal key
- Per CT-I10

### 2.7 Audit Log

Shared with the broader Hermes audit log. Every attestation issuance, every revocation, every verification, every lineage extension is recorded. Tamper-evident.

---

## 3. The attestation graph

The lineage store is a DAG. Nodes are attestations. Edges are predecessor references.

```
                   intent_root_attestation
                  /                       \
   retrieval_attestation        retrieval_attestation
   (file_miner)                 (dependency_miner)
        \                        /
         \                      /
          generation_attestation
          (artifact: patch_v14)
                   |
            review_attestation
            (by reviewer Alice)
                   |
          execution_attestation
          (deploy completed)
```

A new attestation may reference one or more predecessors. Predecessors are immutable once referenced (CT-I9).

---

## 4. Attestation types

| Type | What it attests | Issued by |
|------|----------------|-----------|
| `intent_root` | User has authorized this scope | User (via auth ceremony) |
| `retrieval` | A miner produced this report under these conditions | Fabric Dispatcher |
| `generation` | A model produced this artifact under these conditions | Hermes (via Attestation Service) |
| `validation` | A deterministic check passed on this artifact | Validator subsystem |
| `review` | A human reviewer evaluated this artifact | Reviewer (personal key) |
| `approval` | The artifact is approved for execution | Policy authority |
| `execution` | The artifact was executed; here are the results | Forge (after action) |
| `revocation` | A prior attestation is invalidated | Operator or automated revoker |
| `derivative_revocation` | A prior attestation's derivative was invalidated | Automated cascade |

See `ATTESTATIONS.md` for full schemas.

---

## 5. The trust chain pattern

For any artifact that drives a privileged action, the chain typically looks like:

```
intent_root
  → retrieval(s)            # Fabric gathered the relevant context
  → generation              # Model produced the artifact
  → validation(s)           # Deterministic checks (lint, typecheck, tests)
  → review (if required)    # Human attestation
  → approval (if required)  # Authorized issuance for execution
  → execution               # Forge enacted
```

Each step's attestation includes the predecessor IDs in its `references` field. Verification walks the chain from the leaf back to the intent root.

The chain has no untrusted boundary. Every input to every step is itself attested.

---

## 6. Architecture diagram

```
   ┌────────────────────────────────────────────────────┐
   │  Clients (Hermes, Fabric, Reviewer UI, Forge)      │
   └────────────────────┬───────────────────────────────┘
                        │ AttestationRequest
                        │ (mTLS + workload identity)
                        │
   ┌────────────────────▼───────────────────────────────┐
   │            Attestation Service                      │
   │  - validate request schema                          │
   │  - check client authorization                       │
   │  - validate predecessor references exist & valid    │
   │  - check tier ceremony requirements                 │
   │  - construct attestation envelope                   │
   └──────┬──────────────┬─────────────────┬────────────┘
          │              │                  │
          │ sign         │ store            │ audit
          │              │                  │
   ┌──────▼────┐   ┌────▼──────────┐   ┌──▼────────────┐
   │ KMS/HSM   │   │ Lineage Store │   │   Audit Log   │
   │ (private  │   │ (DAG, append- │   │ (hash-chained,│
   │  keys)    │   │  only)        │   │  tamper-evid) │
   └───────────┘   └───────────────┘   └───────────────┘
                          │
   ┌──────────────────────▼─────────────────────────────┐
   │       Verification Service (read-only)             │
   │  - walk chain                                       │
   │  - check revocation index                           │
   │  - return trust status                              │
   └────────────────────────────────────────────────────┘
                          │
   ┌──────────────────────▼─────────────────────────────┐
   │           Revocation Index (versioned)             │
   └────────────────────────────────────────────────────┘
```

---

## 7. Issuance flow

```
1. Client (e.g., Hermes) prepares an artifact.
2. Client constructs an AttestationRequest:
   - type: generation
   - subject: artifact content hash
   - intent_root_ref: <id>
   - predecessor_refs: [retrieval_att_1, retrieval_att_2, ...]
   - artifact_class: code_patch
   - subject_metadata: { language, file_count, ... }
3. Client sends request to Attestation Service over mTLS.
4. Attestation Service:
   - Authenticates client (workload identity)
   - Validates request schema
   - Looks up artifact_class → tier
   - Verifies tier ceremony requirements are met
     (e.g., does tier require a second witness?)
   - Resolves predecessor refs; checks they exist and are valid
   - Constructs attestation envelope
   - Sends payload to KMS for signing
   - Records attestation in lineage store
   - Appends entry to audit log
   - Returns signed attestation to client
5. Client stores attestation reference; downstream consumers verify it.
```

---

## 8. Verification flow

```
1. Verifier presents an attestation ID.
2. Verification Service:
   - Looks up attestation in lineage store
   - Checks cache: is there a recent verification for
     (attestation_id, current_revocation_index_version)?
     - If hit: return cached result
   - Else:
     - Verify signature using issuer's certificate chain
     - Walk predecessors recursively, verifying each
     - Check revocation index for this attestation and all predecessors
     - Determine final state: valid | expired | revoked | derivative_revoked
     - Cache result keyed by current revocation index version
3. Return TrustStatus to verifier.
```

Verification is O(1) on cache hit (per CT-I13) and O(chain length) on cache miss.

---

## 9. Revocation flow

```
1. Operator (or automated revoker) issues a RevocationRequest:
   - target_attestation_id
   - reason
2. Attestation Service:
   - Validates revoker authorization (operator role or automated policy)
   - Issues a revocation attestation (signed)
   - Updates revocation index (increments version)
   - Triggers cascade: enqueue all derivative attestations for
     derivative_revocation
3. Cascade worker (async):
   - For each downstream attestation in the lineage:
     - Mark derivative_revoked
     - Append cascade entry to audit log
   - Continues until all derivatives marked
   - SLA: under 60s (per CT-I5)
4. Verifiers checking any affected attestation:
   - On next verification, see incremented revocation index version
   - Cache invalidated; re-verification runs
   - Returns revoked or derivative_revoked
```

---

## 10. Why not just sign and forget?

A "sign and forget" model fails three ways:

1. **No revocation.** If a foundational attestation is later found compromised (e.g., the generating model was deprecated, or a reviewer's credential was stolen), there's no way to invalidate downstream artifacts.

2. **No lineage.** You can verify "this artifact came from somewhere" but not "this artifact came from authorized intent through these inputs."

3. **No mutation tracking.** A signed artifact that has been quietly modified by a human or another agent has no way to be detected.

The Cognitive PKI handles all three by treating attestations as a graph, not a flat list.

---

## 11. Composition with Hermes

| Hermes principle | PKI implementation |
|------------------|--------------------|
| P1 deterministic dominates | Attestation Service is deterministic; CT-I7 |
| P3 intent provenance | Every attestation chains to intent_root; CT-I2 |
| P4 agent never owns secrets | Agent never owns signing keys; CP4, CT-I1 |
| P5 observability threat surface | Audit log is itself signed; verification doesn't leak content |
| P6 subsystem diversity | Verification uses a different process than issuance |
| P7 modularity | KMS swappable; verification swappable |

The PKI does not override Hermes invariants. It instantiates them in the signing domain.

---

## 12. What this architecture is NOT

- **Not e-signing.** Reviewers attest via personal keys, but that's supply-chain attestation, not legal-document signing.
- **Not blockchain.** Append-only and hash-chained, but centralized for performance. Public verifiability via signed audit log checkpoints, not consensus.
- **Not OAuth.** Different problem. OAuth authorizes API calls; PKI provenance attests cognitive artifacts.
- **Not optional.** A deployment without the PKI loses CP3, CP5, CP7. The system regresses to vibes-based trust.
- **Not free.** Attestation adds latency (~10–50 ms per issuance) and storage cost. Risk-tiered ceremony (CP6) keeps costs proportional.

---

## 13. Open questions

- **KMS rotation under live workloads.** Signing keys rotate. Re-attestation of long-lived artifacts under new keys requires care. Initial approach: each attestation carries the certificate chain, including expired certs, so historical verification works even after rotation.
- **Cross-organization verification.** If two organizations share artifacts, how do they cross-verify? Initial scope: single-org PKI. Federation deferred.
- **Quantum-resilient signing.** Current signatures use ed25519. Migration path to post-quantum signatures (e.g., Dilithium) is part of long-term planning, not v1.

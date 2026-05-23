# Cognitive Trust Reference Skeleton

A minimal Python implementation of the Cognitive PKI layer: attestations, lineage store, signing service, verification, revocation.

**What's here:**

- `cogtrust/attestations.py` — Attestation envelope, types, canonical-form serialization
- `cogtrust/signing.py` — Signing service (ed25519 reference; KMS-swappable)
- `cogtrust/lineage.py` — Append-only DAG store with hash chain
- `cogtrust/revocation.py` — Revocation index with cascade
- `cogtrust/verification.py` — Chain verification with cache
- `cogtrust/service.py` — Attestation Service (the one entry point)
- `cogtrust/tiers.py` — Tier registry and ceremony requirements
- `tests/` — Tests for the above

**What's NOT here:**

- The Fabric (the refrlow package fills this role)
- KMS/HSM integration (the signing layer is swappable; default is in-process ed25519)
- The Repo Knowledge Graph (a separate component; not implemented in this skeleton)
- Reviewer UI (operator-facing; out of scope for the trust spine skeleton)

**Run the tests:**

```bash
cd cognitive-trust/skeleton
pip install -e .
pytest tests/ -v
```

The skeleton is intentionally focused on the parts of Cognitive Trust that *don't* have a reference implementation elsewhere. The Fabric is well-covered by refrlow; this fills in the PKI.

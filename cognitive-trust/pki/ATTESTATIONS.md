# Attestation Schemas

**Purpose:** Define the on-the-wire schema for each attestation type. Implementations may use JSON, CBOR, or Protobuf — the field names and semantics are fixed.

All attestations share an envelope. Type-specific payload sits inside `subject`.

---

## Common envelope

```json
{
  "attestation_id": "att_<uuid>",
  "type": "<intent_root|retrieval|generation|validation|review|approval|execution|revocation|derivative_revocation>",
  "schema_version": "1.0",

  "issuer": {
    "identity": "<service_name | user_id>",
    "kind": "service | personal",
    "cert_chain": ["<base64>", ...]
  },

  "subject": { /* type-specific; see below */ },

  "context": {
    "intent_root_ref": "att_<uuid>",
    "predecessor_refs": ["att_<uuid>", ...],
    "artifact_class": "<class_name>",
    "tier": 1
  },

  "subject_hashes": {
    "<logical_name>": "sha256:..."
  },

  "issued_at": "<iso8601>",
  "expires_at": "<iso8601 | null>",
  "not_before": "<iso8601 | null>",

  "policy_assertion": {
    "policies_satisfied": ["<policy_id>", ...],
    "policy_version": "<semver>"
  },

  "signature": {
    "algorithm": "ed25519",
    "value": "<base64>"
  }
}
```

Notes:

- `attestation_id` is globally unique.
- `issuer.cert_chain` includes the issuer cert + intermediates up to a trust root. Verifiers walk this chain.
- `intent_root_ref` is mandatory for every type except `intent_root` itself (which is the root).
- `predecessor_refs` is the lineage edge. Empty only for `intent_root`.
- `subject_hashes` lets verifiers detect post-attestation content tampering.
- `signature` covers the entire canonical-form envelope (everything above `signature`).

---

## Type-specific subjects

### intent_root

The user's authorization for a scope of work.

```json
{
  "type": "intent_root",
  "subject": {
    "intent_description": "Refactor the authentication module",
    "scope": {
      "paths": ["src/auth/**"],
      "actions": ["read", "write", "test", "commit"],
      "exclude": [".env", "secrets/"]
    },
    "session_id": "sess_<uuid>",
    "user_id": "user_<uuid>"
  },
  "expires_at": "2026-05-22T17:00:00Z",
  // ... envelope fields
}
```

Issued by: the user authentication ceremony (e.g., login + intent signing UI). Signed by the user's personal key.

### retrieval

A miner produced a structured report.

```json
{
  "type": "retrieval",
  "subject": {
    "miner": "dependency_miner",
    "task": "find_callers_of",
    "params_hash": "sha256:...",
    "report_hash": "sha256:...",
    "scope_effective": { ... },
    "budget_effective": { ... },
    "llm_used": false,
    "total_candidates": 14,
    "returned": 14
  },
  "subject_hashes": {
    "src/lib/auth.ts": "sha256:...",
    "src/api/init.ts": "sha256:..."
  },
  // ... envelope fields
}
```

Issued by: Fabric Dispatcher. The Dispatcher's identity is the issuer; it signs after policy enforcement.

### generation

A model produced an artifact.

```json
{
  "type": "generation",
  "subject": {
    "artifact_id": "art_<uuid>",
    "artifact_class": "code_patch",
    "artifact_hash": "sha256:...",
    "model": {
      "provider": "anthropic",
      "name": "claude-sonnet-4-5",
      "version": "2026-04-01",
      "deployment_id": "..."
    },
    "prompt_hash": "sha256:...",
    "input_attestations": [
      "att_retrieval_1",
      "att_retrieval_2"
    ],
    "generation_metadata": {
      "tokens_in": 4231,
      "tokens_out": 812,
      "duration_ms": 2104,
      "temperature": 0.0
    }
  },
  "subject_hashes": {
    "artifact": "sha256:..."
  },
  // ... envelope fields
}
```

Issued by: Hermes through the Attestation Service. Crucial: the agent does not sign; it requests attestation.

### validation

A deterministic check passed (or failed).

```json
{
  "type": "validation",
  "subject": {
    "validator": "typecheck",
    "validator_version": "tsc-5.4.2",
    "target_artifact": "att_generation_xyz",
    "result": "pass | fail",
    "details": {
      "errors": [],
      "warnings": []
    }
  },
  // ... envelope fields
}
```

Issued by: the validator runner. A failed validation is still attested — it's evidence.

### review

A human reviewer evaluated the artifact.

```json
{
  "type": "review",
  "subject": {
    "reviewer_id": "user_<uuid>",
    "target_artifact": "att_generation_xyz",
    "verdict": "approved | rejected | needs_changes",
    "comments_hash": "sha256:...",
    "review_duration_ms": 142000,
    "items_inspected": ["file_path", "diff", "test_results"]
  },
  "issuer": {
    "identity": "user_<uuid>",
    "kind": "personal",
    "cert_chain": ["<personal_cert>", "<intermediate>", "<root>"]
  },
  // ... envelope fields
}
```

Signed by: the reviewer's personal key (per CT-I10). The `issuer.kind` must be `personal`.

### approval

The artifact is approved for execution. Distinct from review: review is "I've looked"; approval is "I authorize."

```json
{
  "type": "approval",
  "subject": {
    "approver_id": "user_<uuid>",
    "target_artifact": "att_generation_xyz",
    "review_attestation": "att_review_abc",
    "execution_window": {
      "not_before": "2026-05-22T15:00:00Z",
      "not_after": "2026-05-22T16:00:00Z"
    },
    "execution_constraints": {
      "max_executions": 1,
      "rollback_required": true
    }
  },
  // ... envelope fields
}
```

For high tiers, requires both `review_attestation` and `approver_id != reviewer_id` (separation of duties).

### execution

Forge enacted the artifact.

```json
{
  "type": "execution",
  "subject": {
    "approval_attestation": "att_approval_xyz",
    "executed_at": "2026-05-22T15:14:00Z",
    "outcome": "success | partial | failed | rolled_back",
    "outcome_details_hash": "sha256:...",
    "side_effects": [
      { "kind": "file_write", "path": "...", "before_hash": "...", "after_hash": "..." },
      { "kind": "external_call", "endpoint": "...", "request_hash": "..." }
    ]
  },
  // ... envelope fields
}
```

Issued by: Forge. Records the actual outcome, including unhappy paths.

### revocation

A prior attestation is invalidated.

```json
{
  "type": "revocation",
  "subject": {
    "revoked_attestation": "att_xyz",
    "reason": "<short_reason_code>",
    "details_hash": "sha256:...",
    "revoker_role": "operator | automated_policy"
  },
  // ... envelope fields
}
```

Issued by: an authorized operator or automated policy (e.g., model deprecation). Cascades to derivatives within the SLA (CT-I5).

### derivative_revocation

A descendant of a revoked attestation is automatically invalidated.

```json
{
  "type": "derivative_revocation",
  "subject": {
    "affected_attestation": "att_abc",
    "root_revocation": "att_revocation_xyz",
    "cascade_depth": 3
  },
  // ... envelope fields
}
```

Issued by: the cascade worker. Distinguishable from explicit revocation so audit can tell them apart.

---

## Canonical form for signing

Before signing, the envelope is serialized in a canonical form:

- JSON Canonical Form (RFC 8785) or equivalent
- Keys sorted lexicographically
- No whitespace, no null fields, no duplicate keys
- The `signature` field is omitted (it's what's being computed)
- The `attestation_id` is included (computed first, then everything is signed)

The signed payload bytes are hashed with SHA-256; the hash is signed with ed25519.

---

## Verification rules

Given an attestation, a verifier must check:

1. **Schema validity.** Envelope structure correct; required fields present.
2. **Signature validity.** Signature over canonical form verifies under `issuer.cert_chain[0]`.
3. **Certificate chain.** Each cert in the chain validly signs the previous; chain terminates at a trusted root.
4. **Time bounds.** `issued_at` ≤ now, `not_before` ≤ now (if present), `expires_at` > now (if present).
5. **Predecessor validity.** Every attestation in `context.predecessor_refs` exists and verifies. (Recursive; cached.)
6. **Revocation status.** Attestation is not in revocation index; no predecessor is revoked (otherwise this is `derivative_revoked`).
7. **Content integrity.** For attestations with `subject_hashes`: re-hash the referenced content; must match. (Optional; only required when verifier can read the content.)
8. **Issuer authority.** For type-specific issuers: was the issuer actually authorized to issue this type?

If any check fails, the verifier returns the specific failure mode. Verifiers MUST NOT proceed on partial validity.

---

## Tier-specific requirements

Different artifact classes carry different ceremony. Examples (full table in `TRUST_TIERS.md`):

| Class | Tier | Required attestations |
|-------|------|----------------------|
| Scratch note | 0 | none |
| Internal summary | 1 | retrieval, generation |
| Code patch (local) | 2 | retrieval, generation, validation |
| Code patch (PR-bound) | 3 | retrieval, generation, validation, review |
| Deployment config | 4 | retrieval, generation, validation, review, approval |
| Production action | 5 | all of T4 + multi-party approval |

The Attestation Service refuses to issue a "ready for execution" approval if the tier's required attestations are missing.

---

## Field-level notes

### Why `prompt_hash` and not `prompt_text`?

Privacy and storage cost. Prompts may contain sensitive context; we don't want to persist them in the lineage. The hash is enough for forensic reproduction if the prompt is independently archived elsewhere with the same hash.

### Why both `intent_root_ref` AND `predecessor_refs`?

`intent_root_ref` is the always-direct path back to the user. `predecessor_refs` are the immediate inputs. They are not the same: `predecessor_refs` walks the chain step by step; `intent_root_ref` is a shortcut for the most common verification question.

### Why `subject_hashes` separate from `subject.artifact_hash`?

`subject` describes what the attestation is about. `subject_hashes` is a verifier convenience: lists every external artifact the attestation references, so verifiers can do integrity checks without parsing `subject`.

### Why is `signature.algorithm` a field?

Future-proofing. Today it's ed25519. Migration to post-quantum signatures will require versioning the algorithm.

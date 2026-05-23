# Lineage: From Intent to Execution

**Purpose:** Show, with worked examples, how an action in the system traces back through artifacts and retrievals to the originating user intent.

This is the operational answer to "who authorized this, why, and using what evidence?"

---

## 1. The shape of a lineage

A lineage is a DAG rooted at one or more intent_root attestations and ending at execution attestations (or staying at intermediate states if no execution has occurred).

```
intent_root
    │
    ├── retrieval (fabric, file_miner)
    ├── retrieval (fabric, dependency_miner)
    ├── retrieval (fabric, test_miner)
    │
    └── generation (hermes, code_patch)
            │
            ├── validation (typecheck, pass)
            ├── validation (lint, pass)
            ├── validation (unit_tests, pass)
            │
            └── review (alice, approved)
                    │
                    └── approval (bob, authorized for 1h)
                            │
                            └── execution (forge, success)
```

Reading top-to-bottom: a user authorized work, the Fabric gathered context, Hermes generated an artifact, validators checked it, Alice reviewed it, Bob approved it for execution, Forge executed.

Reading bottom-to-top from any node: full provenance.

---

## 2. Worked example: a small code patch

Setup: user wants Hermes to fix a typo in an error message.

### Step 1 — Intent root

User signs:

```json
{
  "type": "intent_root",
  "subject": {
    "intent_description": "Fix typo in error message in src/api/errors.ts",
    "scope": {
      "paths": ["src/api/errors.ts"],
      "actions": ["read", "write", "test", "commit"]
    },
    "session_id": "sess_2026_05_22_001",
    "user_id": "user_alice"
  },
  "expires_at": "2026-05-22T15:00:00Z",
  "attestation_id": "att_001"
}
```

### Step 2 — Hermes plans, dispatches a retrieval

```json
{
  "type": "retrieval",
  "subject": {
    "miner": "file_miner",
    "task": "stat",
    "params_hash": "sha256:abc...",
    "report_hash": "sha256:def..."
  },
  "context": {
    "intent_root_ref": "att_001",
    "predecessor_refs": []
  },
  "subject_hashes": {
    "src/api/errors.ts": "sha256:111..."
  },
  "attestation_id": "att_002"
}
```

### Step 3 — Hermes generates the patch

```json
{
  "type": "generation",
  "subject": {
    "artifact_id": "art_001",
    "artifact_class": "code_patch",
    "artifact_hash": "sha256:222...",
    "model": {
      "provider": "anthropic",
      "name": "claude-sonnet-4-5",
      "version": "2026-04-01"
    }
  },
  "context": {
    "intent_root_ref": "att_001",
    "predecessor_refs": ["att_002"]
  },
  "subject_hashes": {
    "artifact": "sha256:222..."
  },
  "attestation_id": "att_003"
}
```

### Step 4 — Validation

```json
{
  "type": "validation",
  "subject": {
    "validator": "typecheck",
    "target_artifact": "att_003",
    "result": "pass"
  },
  "context": {
    "intent_root_ref": "att_001",
    "predecessor_refs": ["att_003"]
  },
  "attestation_id": "att_004"
}
```

### Step 5 — Approval (low tier, no separate review)

```json
{
  "type": "approval",
  "subject": {
    "approver_id": "user_alice",
    "target_artifact": "att_003",
    "execution_window": {
      "not_before": "2026-05-22T14:30:00Z",
      "not_after": "2026-05-22T14:35:00Z"
    }
  },
  "context": {
    "intent_root_ref": "att_001",
    "predecessor_refs": ["att_003", "att_004"]
  },
  "attestation_id": "att_005"
}
```

### Step 6 — Execution

```json
{
  "type": "execution",
  "subject": {
    "approval_attestation": "att_005",
    "executed_at": "2026-05-22T14:30:15Z",
    "outcome": "success",
    "side_effects": [
      {
        "kind": "file_write",
        "path": "src/api/errors.ts",
        "before_hash": "sha256:111...",
        "after_hash": "sha256:333..."
      },
      {
        "kind": "git_commit",
        "sha": "abc123"
      }
    ]
  },
  "context": {
    "intent_root_ref": "att_001",
    "predecessor_refs": ["att_005"]
  },
  "attestation_id": "att_006"
}
```

### What we can now answer

- **Who did this?** user_alice, signing intent_root att_001.
- **What model produced the artifact?** claude-sonnet-4-5 build 2026-04-01.
- **What context informed it?** att_002 (file_miner.stat on src/api/errors.ts at hash 111...).
- **Was it validated?** Yes, att_004 (typecheck pass).
- **Was it approved?** Yes, att_005 by user_alice.
- **Did execution succeed?** Yes, att_006.
- **Has the source file changed since att_002 read it?** Compute current hash; compare to att_002.subject_hashes.

All of this from a single attestation chain.

---

## 3. Worked example: a high-tier action

Production deploy. Many more attestations, separation of duties.

```
att_intent_root (Alice, "deploy auth-service v1.4.2 to production")
    │
    ├── att_retrieval_file_inventory (Fabric)
    ├── att_retrieval_dependency_graph (Fabric)
    ├── att_retrieval_test_history (Fabric)
    │
    ├── att_generation_deploy_manifest (Hermes, claude-sonnet-4-5)
    │       │
    │       ├── att_validation_schema (deploy spec validator, pass)
    │       ├── att_validation_security_scan (pass)
    │       ├── att_validation_test_suite (pass: 184/184)
    │       ├── att_validation_canary_simulation (pass)
    │       │
    │       ├── att_review_alice ("approved, looks correct")
    │       │       (issuer.kind = personal, signed by Alice's key)
    │       │
    │       └── att_review_bob ("approved, second-reviewer per policy")
    │               (separate person; CT-I10)
    │
    └── att_approval (Carla, multi-party approver)
            (cooldown: 5 minutes between approval and execution)
            │
            └── att_execution (Forge, deploy command)
                    (outcome: success; rollback procedure documented)
```

Tier-5 ceremony enforced by the Attestation Service:

- 2 distinct reviewer attestations required (Alice + Bob)
- Approval issuer must be neither reviewer (Carla)
- 5-minute cooldown between approval and execution
- Execution window narrowly bounded

If any of these missing, the approval attestation issuance is refused.

---

## 4. Lineage queries

Given any attestation, the verification service can answer:

### "What is the full chain back to intent?"

Walk predecessor_refs recursively, returning the DAG.

### "Is this chain still valid?"

Check revocation index for every node; check expiry for every node; return aggregate status.

### "What artifacts has this intent root produced?"

Walk forward from intent_root_ref through all attestations referencing it.

### "What artifacts used this miner report?"

Walk forward through `predecessor_refs` containing the retrieval attestation.

### "What is the model identity for everything Alice has approved?"

Filter forward-walk from Alice's review attestations to find generation predecessors, return their `model` fields.

These are standard graph traversals on the lineage store.

---

## 5. Lineage breaks (mutation detection)

Suppose someone modifies `src/api/errors.ts` between att_002 (read) and att_006 (execution). The system detects this:

- At validation time: validator's run pulls the current file; its content_hash differs from att_002.subject_hashes; validation attestation can include a `source_drift_detected` flag
- At execution time: Forge re-checks subject_hashes before enacting; if any drift, refuses to execute and surfaces to user
- At verification time: a verifier walking the chain after the fact can detect drift

A modified file's existing chain becomes **broken** — the chain references an old content_hash, but the file has a new one. Downstream consumers see this.

To "re-attach" the file to the chain, a new generation attestation is issued with the new hash. The old chain remains in the audit log as historical evidence of the original state.

---

## 6. Forking and merging

A single artifact can have multiple downstream paths:

```
att_generation_001
    ├── att_validation_typecheck (pass)
    ├── att_validation_lint (pass)
    ├── att_review_alice (approved)
    └── att_review_bob (rejected, requested changes)
```

The forking is normal — the validations and reviews happened in parallel. Approval consumes both reviews; if one rejected, approval issuance fails or proceeds with explicit acknowledgment.

Merging happens when multiple generation attestations are inputs to a higher-level artifact (e.g., a release bundling multiple patches):

```
att_release_bundle
    predecessor_refs: [
      att_generation_patch_a,
      att_generation_patch_b,
      att_generation_patch_c
    ]
```

The release inherits the trust state of its weakest input. If any input is revoked, the release is derivative_revoked.

---

## 7. The intent expansion problem

What if a single intent root needs to cover work that wasn't fully specified upfront?

Approach: intent roots can be **expanded** with a new attestation that references the original and adds scope. The expansion is signed by the same user (or an authorized delegate) and creates a new effective intent root for derivative work.

```
att_intent_001 ("refactor auth")
    └── att_intent_expansion_002 ("also touch billing helpers")
             - references att_intent_001
             - signed by same user
             - new effective scope: union of both
```

Artifacts produced after the expansion reference the expansion attestation as their intent_root_ref. Artifacts produced before reference the original.

This handles the legitimate "I need to expand scope mid-session" case without breaking lineage integrity. See Hermes simulation Day 34 (INC-006) for the live example.

---

## 8. Auditor view

When an auditor wants to investigate "what produced this deployment?":

1. Find the execution attestation: att_execution_xyz.
2. Verification service returns: full chain back to intent_root, current trust state, any drift, any revocations.
3. For each generation step: model identity, prompt hash, generation parameters.
4. For each review/approval: reviewer/approver identity, timestamps, comments_hash (comments retrieved separately if authorized).
5. For each retrieval: which miner, what parameters, what content hashes.

The auditor never needs to "trust the system." They can independently verify every signature.

---

## 9. The "reproducible cognition" claim

Given the full lineage, plus archived prompts, plus deterministic miner outputs:

- Re-run the miners against the original content_hashes → same outputs
- Re-prompt the same model version with the same prompt → similar outputs (not bit-identical due to model nondeterminism, but structurally comparable)
- Walk the chain → re-validate every step

This is approximately reproducible. Bit-exact reproduction requires temperature=0 + model version pinning; even then, providers may produce drift. The PKI captures enough to make the question answerable, which is the point.

Compare to current state of the art: "I think the AI did it because we asked it to. I'm not sure when."

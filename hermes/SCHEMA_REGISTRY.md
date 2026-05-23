# Schema Registry

**Status:** Pre-implementation, frozen for Step 1  
**Purpose:** Define all data schemas that cross system boundaries in Hermes Prime. No untyped data crosses a subsystem boundary. If it crosses a boundary, it has a schema here.

This document is the single source of truth for inter-component data shapes. Implementation must match these schemas. Schemas here must change via ADR or schema-change PR, not inline during development.

---

## Governing Principle

> Schemas are civilization. Without schemas, everything devolves into prompt soup.

Every schema in this document:
- Has a unique stable ID
- Is versioned
- Specifies all required and optional fields
- Defines the validation rule that would catch a malformed instance
- Is accompanied by a valid example and at least one invalid example

---

## S001 — Action Proposal

**Produced by:** Hermes Planner  
**Consumed by:** Sentinel (Layer 1 validation)  
**Direction:** Hermes → Sentinel

```json
{
  "$schema": "https://hermes-prime/schemas/action-proposal/v1",
  "action_id": "urn:uuid:f81d4fae-7dec-11d0-a765-00a0c91e6bf6",
  "action_type": "filesystem.read",
  "scope": "/workspace/project/src/**/*.ts",
  "intent_root": "sig:user:abc123:session:xyz:2026-05-23T07:00:00Z",
  "capability": "cap:file-read:scoped",
  "parameters": {},
  "proposed_at": "2026-05-23T07:20:00Z"
}
```

**Required fields:** `action_id`, `action_type`, `scope`, `intent_root`, `capability`, `proposed_at`  
**Optional fields:** `parameters` (action-type-specific structured data)  

**`action_type` valid values (MVP):**
- `filesystem.read`
- `filesystem.write`
- `execution.command`
- `miner.dispatch`
- `memory.write`
- `capability.request`

**Validation rules:**
- `action_id` must be a valid URN UUID
- `scope` must not contain `..` sequences after normalization
- `scope` must not contain null bytes
- `scope` must not contain shell metacharacters (`;`, `&&`, `|`, backtick) 
- `intent_root` must be a valid signature reference (non-empty, structured prefix)
- `proposed_at` must be a valid ISO 8601 datetime

**Invalid example (path traversal):**
```json
{
  "action_id": "urn:uuid:...",
  "action_type": "filesystem.read",
  "scope": "/workspace/../etc/passwd",
  "intent_root": "sig:user:...",
  "capability": "cap:file-read:scoped",
  "proposed_at": "2026-05-23T07:20:00Z"
}
```
→ Fails Layer 4 OPA policy. Denial reason: `path_traversal_attempt`.

---

## S002 — Sentinel Decision

**Produced by:** Sentinel  
**Consumed by:** Forge (if permitted), Hermes Planner (if denied), Audit Log  
**Direction:** Sentinel → Forge / Hermes

```json
{
  "$schema": "https://hermes-prime/schemas/sentinel-decision/v1",
  "decision_id": "urn:uuid:a8098c1a-f86e-11da-bd1a-00112444be1e",
  "timestamp": "2026-05-23T07:20:01Z",
  "action_id": "urn:uuid:f81d4fae-7dec-11d0-a765-00a0c91e6bf6",
  "permitted": true,
  "risk_tier": "T0",
  "policy_rule": "filesystem.read.workspace_scoped",
  "blocking_layer": null,
  "denial_reason": null,
  "advisory_signals": [],
  "consent_required": false,
  "audit_written": true
}
```

**Denial example:**
```json
{
  "$schema": "https://hermes-prime/schemas/sentinel-decision/v1",
  "decision_id": "urn:uuid:...",
  "timestamp": "2026-05-23T07:20:01Z",
  "action_id": "urn:uuid:...",
  "permitted": false,
  "risk_tier": null,
  "policy_rule": null,
  "blocking_layer": 4,
  "denial_reason": "path_traversal_attempt: resolved path exits workspace root",
  "advisory_signals": [],
  "consent_required": null,
  "audit_written": true
}
```

**Required fields:** All fields are required. `null` is the explicit value for inapplicable fields, not omission.

**Validation rules:**
- `permitted: true` requires `risk_tier` to be non-null, `blocking_layer` to be null
- `permitted: false` requires `denial_reason` to be non-null, `blocking_layer` to be an integer 1–7
- `audit_written` must always be `true` — if the audit write failed, the decision is not returned
- `consent_required` must be `true` for any `risk_tier` of T2 or above

---

## S003 — Capability Token

**Produced by:** Vault  
**Consumed by:** Sentinel (Layer 2 validation)  
**Direction:** Vault → Hermes → Sentinel

```json
{
  "$schema": "https://hermes-prime/schemas/capability-token/v1",
  "token_id": "urn:uuid:...",
  "capability": "filesystem.read",
  "scope": "/workspace/project/src/",
  "actions": ["read"],
  "risk_tier_ceiling": "T1",
  "expires_at": "2026-05-23T08:20:00Z",
  "intent_root": "sig:user:abc123:session:xyz:2026-05-23T07:00:00Z",
  "issued_to": "hermes:session:nnn",
  "issued_at": "2026-05-23T07:20:00Z",
  "nonce": "base64:...",
  "signature": "sig:ed25519:..."
}
```

**Validation rules:**
- `expires_at` must be in the future at evaluation time
- `scope` must be a valid path or glob pattern within the declared workspace
- `risk_tier_ceiling` constrains what tier an action using this token may be assigned
- `signature` must be verifiable against Vault's current public key
- `intent_root` must match the intent root presented in the action proposal using this token

---

## S004 — Miner Attestation

**Produced by:** Retrieval Fabric miners  
**Consumed by:** Sentinel (miner report boundary check), Hermes Planner  
**Direction:** Miner → Sentinel → Hermes

```json
{
  "$schema": "https://hermes-prime/schemas/miner-attestation/v1",
  "attestation_id": "urn:uuid:...",
  "miner_id": "fm-001",
  "miner_type": "file_miner",
  "miner_version": "v0.1.0",
  "scan_scope": "/workspace/project/src/",
  "scan_time": "2026-05-23T07:20:00Z",
  "duration_ms": 84,
  "files_examined": [
    {
      "path": "/workspace/project/src/auth.ts",
      "hash": "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "size_bytes": 4096
    }
  ],
  "results": [
    {
      "file": "src/auth.ts",
      "line": 44,
      "relevance": 0.92,
      "match": "validate_token"
    }
  ],
  "confidence": 0.98,
  "content_summary_hash": "sha256:8f4329a2741a...",
  "signature": "sig:ed25519:..."
}
```

**Validation rules:**
- `signature` must verify against the miner's Vault-issued ephemeral public key
- `content_summary_hash` must match the hash of the `results` array contents
- `scan_scope` must be within the active session's capability token scope
- Unsigned or invalid attestations are rejected at the Sentinel boundary — the results are quarantined, not passed to the planner

---

## S005 — Memory Claim

**Produced by:** Hermes Planner, Miners (indirect)  
**Consumed by:** Atlas write path  
**Direction:** Any → Atlas

```json
{
  "$schema": "https://hermes-prime/schemas/memory-claim/v1",
  "fact_id": "urn:uuid:...",
  "claim": "The function parseConfig reads DATABASE_URL from process.env",
  "source": {
    "type": "miner_attestation",
    "attestation_id": "urn:uuid:...",
    "miner_type": "ast_miner"
  },
  "confidence": 0.95,
  "timestamp": "2026-05-23T07:20:00Z",
  "tier": "quarantine",
  "contradictions": [],
  "intent_root": "sig:user:..."
}
```

**`tier` values:** `quarantine` (default) | `authoritative` (requires promotion with corroboration)  
**Validation rules:**
- New claims always enter at `tier: quarantine`. Promotion to `authoritative` requires a separate write with a corroborating source.
- `source` must reference a verifiable artifact (attestation ID or signed user statement).
- Claims with no source reference are rejected at the Atlas write path.

---

## S006 — Provenance Attestation

**Produced by:** Cognitive PKI service  
**Consumed by:** Atlas, Audit Log, human verifiers  
**Direction:** PKI → any consumer

```json
{
  "$schema": "https://hermes-prime/schemas/provenance-attestation/v1",
  "attestation_id": "urn:uuid:...",
  "artifact_hash": "sha256:...",
  "artifact_type": "patch | miner_report | memory_claim | plan_step",
  "generated_by": "hermes:session:nnn",
  "model_id": "claude-sonnet-4.6",
  "intent_root": "sig:user:...",
  "parent_attestation_ids": [],
  "input_attestation_ids": ["urn:uuid:..."],
  "generated_at": "2026-05-23T07:20:00Z",
  "lifecycle_state": "generated | reviewed | committed | revoked",
  "signature": "sig:ed25519:..."
}
```

**Validation rules:**
- `signature` must verify against the PKI service's current signing key
- `input_attestation_ids` must all resolve to valid, non-revoked attestations
- `lifecycle_state` transitions are one-directional except `revoked` (which can be reached from any state)

---

## S007 — Fabric Pattern Match

**Produced by:** Pattern Miner (Fabric Retrieval Augmentation)  
**Consumed by:** Pattern Injection Miner → Hermes Planner  
**Direction:** Pattern Miner → Injection Miner → Hermes

```json
{
  "$schema": "https://hermes-prime/schemas/fabric-pattern-match/v1",
  "match_id": "urn:uuid:...",
  "pattern_name": "security-review",
  "pattern_hash": "sha256:...",
  "fabric_version": "v2.0.0",
  "retrieval_time": "2026-05-23T07:20:00Z",
  "confidence": 0.94,
  "reasoning_style": ["adversarial", "defensive", "exploit-aware"],
  "required_checks": ["credential leakage", "shell injection", "unsafe subprocess calls"],
  "output_structure": ["findings", "severity", "remediation"],
  "tags": ["security", "audit", "static-analysis"],
  "authority": "heuristic_guidance_only"
}
```

**`authority` is always `heuristic_guidance_only`.** This field exists precisely to make the constraint explicit in every instance. A pattern match that somehow carries `execution_authority` is a schema violation and must be rejected.

**Validation rules:**
- `authority` must equal `heuristic_guidance_only` — any other value is rejected
- `pattern_hash` must match the hash of the pattern file at `fabric_version`
- Pattern matches are never written to Atlas — they are session-scoped, ephemeral, and used only for prompt augmentation

---

## Schema Stability Rules

1. **Schemas are versioned.** Breaking changes require a new version (`/v2`). Additive changes (new optional fields) may be made within a version with documentation.
2. **Schemas in this document are the source of truth.** Implementation derives from the schema, not the reverse.
3. **Schema changes require a PR.** Inline changes during development are not permitted. If the schema is wrong, fix it here first.
4. **Every schema has a test.** Validation rules must have at least one positive and one negative test case in the test suite before any component uses the schema.
5. **Schemas do not carry free-text reasoning fields.** If a field would contain a natural-language sentence that the model might interpret as an instruction, it is the wrong field design. Use structured enums and references instead.

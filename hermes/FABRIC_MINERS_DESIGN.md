# Fabric Retrieval-Augmented Cognition — Design Document

**Status:** Pre-implementation design  
**Location:** `/miners/fabric-miners/`  
**Companion to:** ADR 0007, ADR 0009, `SCHEMA_REGISTRY.md` S007  
**Dependency:** Step 3 (File Miner) must be operational before Fabric miners are built

---

## 0. What This Is Not

- Not a framework import. The `/external/fabric` directory contains the upstream pattern library for concept extraction only. We do not import or run its runtime.
- Not execution authority. Fabric patterns are heuristic guidance. They modify cognition style; they do not authorize actions.
- Not a prompt injection vector. Pattern content is extracted into structured fields before it reaches the planner. Raw pattern text is never appended to system prompts.
- Not a reasoning system. The three fabric miners retrieve, rank, and convert. They do not plan.

---

## 1. The Problem Being Solved

Without structured cognition augmentation, Hermes faces a specific failure mode on every novel task: it reinvents workflows from model priors alone. This produces inconsistent reasoning quality, missed domain-specific checks, and no reusability across similar tasks.

The standard industry response is: append a large hidden system prompt containing domain knowledge. This produces:
- Giant, opaque system prompts that become unauditable
- No versioning of reasoning guidance
- No lineage between "what Hermes was told to do" and "what Hermes did"
- Prompt injection surface embedded in the system prompt itself

Fabric miners solve this by converting pattern knowledge into **structured cognition metadata** that augments the planner's reasoning without hiding reasoning authority inside untracked text.

---

## 2. The Three Miners and Their Roles

### 2.1 Prompt Classification Miner (`prompt-classifier`)

**Single responsibility:** Determine the task type from the user's input.

This miner runs first, before any pattern lookup. It produces a structured task classification that subsequent miners use for retrieval.

**Input:** Raw user prompt text (treated as untrusted input, not as instructions)  
**Output:** Schema S007-adjacent classification block

```json
{
  "classification_id": "urn:uuid:...",
  "task_types": ["security-audit", "code-review"],
  "domain": "backend",
  "recommended_pattern_tags": ["security", "audit", "static-analysis"],
  "confidence": 0.91,
  "classified_at": "2026-05-23T07:20:00Z"
}
```

**Implementation notes:**
- MVP implementation: keyword matching and tag lookup against a local taxonomy. No LLM call.
- Later: lightweight embedding-based classifier using a small local model (never the main agent's model family — diversity rule I11).
- The classification is advisory. Hermes may override it with explicit user direction.
- Classification output is logged with session provenance. If the classifier mis-routes a task, the mis-routing is forensically recoverable.

---

### 2.2 Pattern Miner (`pattern-miner`)

**Single responsibility:** Retrieve matching Fabric patterns from the local library given task classification tags.

**Input:** Classification block from the Prompt Classification Miner  
**Output:** Ranked list of pattern matches conforming to Schema S007

**Implementation notes:**
- Operates on `/external/fabric/patterns/` — the quarantined local copy of the Fabric pattern library.
- MVP retrieval: tag intersection + keyword match against pattern metadata files. Fully deterministic.
- Later: embedding-based semantic matching against pattern descriptions. Small local model. Separate model family from main agent.
- Result limit: returns at most 5 patterns per dispatch (resource ceiling).
- Each result carries `pattern_hash`, `fabric_version`, and `confidence`. Provenance is mandatory — you cannot use a pattern you cannot prove you retrieved.
- The miner **does not read pattern content** into its output. It returns references to patterns. The Injection Miner reads the content.

---

### 2.3 Pattern Injection Miner (`pattern-injector`)

**Single responsibility:** Convert selected Fabric pattern content into structured cognition metadata.

This miner is the most sensitive of the three. It reads raw pattern content and must not allow that content to reach the planner as unstructured text.

**Input:** Pattern references from the Pattern Miner  
**Output:** Structured augmentation block

```json
{
  "augmentation_id": "urn:uuid:...",
  "source_patterns": ["security-review", "code-audit"],
  "reasoning_style": ["adversarial", "defensive", "exploit-aware"],
  "required_checks": [
    "credential leakage",
    "shell injection",
    "unsafe subprocess calls",
    "path traversal"
  ],
  "output_structure": {
    "format": "structured",
    "required_sections": ["findings", "severity", "remediation"],
    "severity_scale": ["critical", "high", "medium", "low", "informational"]
  },
  "constraints": [
    "Do not recommend actions outside current capability scope",
    "Flag but do not auto-fix security issues above T2"
  ],
  "authority": "heuristic_guidance_only",
  "generated_at": "2026-05-23T07:20:00Z",
  "pattern_hashes": {
    "security-review": "sha256:...",
    "code-audit": "sha256:..."
  }
}
```

**Implementation notes:**
- The miner parses pattern files into structured fields. It does not pass raw text through.
- If a pattern file contains text that cannot be parsed into the structured fields, the pattern is skipped and the skip is logged.
- The `constraints` field contains extracted constraints from the pattern — these are short, imperative sentences. They are not long prompt blocks.
- The `authority: "heuristic_guidance_only"` field is always set. The schema validation rejects any augmentation block without it. This is a structural guarantee, not a prompting convention.

---

## 3. The Full Processing Pipeline

```
User Input (untrusted text)
         │
         ▼
Prompt Classification Miner
  → task_types, domain, recommended_pattern_tags
         │
         ▼
Pattern Miner
  → ranked list of pattern references (S007), max 5
         │
         ▼
Pattern Injection Miner
  → structured augmentation block (reasoning_style, required_checks, output_structure)
         │
         ▼
Hermes Planner
  → receives: user intent + structured augmentation block + active capability token
  → produces: Action Proposal (S001)
         │
         ▼
Sentinel Core
  → evaluates Action Proposal against all 6 blocking layers
  → produces: Sentinel Decision (S002)
         │
         ▼
Forge Sandbox (if permitted)
  → executes under overlay, journals, generates diff
         │
         ▼
Staged output awaiting commit/review
```

What Hermes sees: a user message, a structured augmentation block, and its active capability scope. It does not see raw pattern files, classification internals, or retrieval mechanics.

---

## 4. What the Augmentation Block Does and Does Not Do

| Does | Does Not |
|---|---|
| Tells Hermes what reasoning style to apply | Override Sentinel policy |
| Tells Hermes what checks are expected in output | Authorize any action |
| Structures expected output format | Write to Atlas |
| Lists constraints derived from pattern | Expand capability scope |
| Carries provenance (hashes, version) | Persist across sessions |

The augmentation block is consumed by the planner and is not stored. It is session-scoped and ephemeral. If you need to audit "what reasoning guidance was Hermes given for this action," you reconstruct it from the logged pattern references and their hashes at the time of the session. The hashes are in the Provenance Attestation for the plan step.

---

## 5. Prompt Injection Risk in the Injection Miner

The Injection Miner is the highest-risk of the three fabric miners because it reads pattern file content. An attacker who can modify the local Fabric pattern library can plant instructions in pattern files.

Mitigations:

1. **Pattern file hash verification.** Before reading content, the miner verifies the file hash against the signed manifest of the quarantined `/external/fabric` copy. A modified file will not match its hash and is skipped.
2. **Structured extraction, not raw text pass-through.** The miner parses specific structured fields from patterns. It cannot pass a free-text instruction block through — there is no field for it in the augmentation output schema.
3. **Field size limits.** Each extracted field has a character limit. An injected long-form prompt cannot fit in `reasoning_style` (which expects short strings) or `required_checks` (which expects short imperative sentences).
4. **Quarantine treatment of pattern content.** If extraction fails for any reason, the pattern is skipped and the failure is logged. The miner does not attempt to interpret or recover from malformed content.

These mitigations do not make the Injection Miner injection-proof. They make injection forensically visible and structurally difficult. Full mitigation requires treating pattern library updates as a supply-chain event with their own attestation.

---

## 6. Build Order Within Step 3/4

Fabric miners are built after the File Miner (Step 3) and AST Miner (Step 4) because:
- They depend on the Miner Attestation infrastructure established in Step 3.
- Their output feeds the planner, which does not exist until Step 6.
- Testing them requires a local Fabric pattern corpus, which is extracted from `/external/fabric` after Step 0 cloning.

The Prompt Classification Miner MVP (keyword matching) can be built during Step 3 as a warmup exercise. The Pattern Miner and Injection Miner are built during the Step 3–4 window. They are not tested end-to-end until the planner exists in Step 6.

---

## 7. Success Criteria for Fabric Miners

Before the planner uses Fabric augmentation in production:

| Test | Expected outcome |
|---|---|
| Classification miner receives "review this code for security issues" | Returns task_types including `security-audit`, confidence > 0.8 |
| Pattern miner receives security-audit tags | Returns ranked list including `security-review` pattern, with hash |
| Injection miner receives security-review reference | Returns augmentation block with `authority: heuristic_guidance_only` |
| Injection miner receives modified pattern file (hash mismatch) | Skips pattern, logs warning, returns remaining valid patterns |
| Augmentation block with injected free-text in `reasoning_style` | Schema validation rejects at Sentinel boundary |
| Pattern miner dispatched more than 5 times in one session | Sixth dispatch blocked by resource ceiling |

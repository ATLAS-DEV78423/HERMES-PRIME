# Refrlow + Hermes Integration

**Purpose:** Show how the refrlow dispatch pattern slots into the Hermes architecture without violating any doctrine principle. Refrlow is opinionated; Hermes is opinionated; this document is the contract between them.

If you're using refrlow as a standalone Claude Code addition, you can skip this document.

---

## 1. Where refrlow lives in Hermes

Refrlow is a pattern implemented inside the **Forge** subsystem.

Recall from `hermes/DOCTRINE.md` §2.1:

| Subsystem | Responsibility | Trust class |
|-----------|---------------|-------------|
| Hermes | Reasoning, planning, synthesis | Untrusted |
| Atlas | Structured memory, provenance, belief state | Semi-trusted |
| Sentinel | Policy enforcement, anomaly detection, redaction | Trusted |
| Vault | Secret storage, key derivation, capability minting | Highest trust |
| **Forge** | **Execution of authorized actions against real systems** | **Trusted, sandboxed** |

Refrlow's dispatcher is part of Forge. Refrlow's subagents are Forge-internal workers. From Hermes's perspective, dispatching a subagent looks like any other Forge capability call.

---

## 2. Mapping refrlow concepts to Hermes concepts

| Refrlow concept | Hermes equivalent |
|-----------------|-------------------|
| Main agent | Hermes (the reasoning core) |
| Dispatcher | Forge's request mediator |
| Subagent class | A family of Forge capabilities |
| Specific subagent task | A specific Forge capability (registered in `CAPABILITY_REGISTRY.md`) |
| Dispatch request | Capability request submitted to Sentinel |
| Dispatch report | Validated tool output that flows to Atlas |
| Allowlisted task_runner tasks | Forge capabilities under the doctrine's normal review |

---

## 3. Capability registration

Each subagent task corresponds to one Forge capability. For example, the file_miner subagent's tasks map to:

| Subagent task | Forge capability | Risk tier |
|---------------|------------------|-----------|
| `file_miner.find_by_glob` | `forge.refrlow.file_miner.find_by_glob` | T1 |
| `file_miner.enumerate_tree` | `forge.refrlow.file_miner.enumerate_tree` | T1 |
| `grep_miner.search_text` | `forge.refrlow.grep_miner.search_text` | T1 |
| `ast_miner.find_definition` | `forge.refrlow.ast_miner.find_definition` | T1 |
| `summarizer.purpose_summary` | `forge.refrlow.summarizer.purpose_summary` | T2 (uses LLM) |
| `validator.lint` | `forge.refrlow.validator.lint` | T1 |
| `validator.safe_to_delete` | `forge.refrlow.validator.safe_to_delete` | T1 |
| `task_runner.run_tests` | `forge.refrlow.task_runner.run_tests` | T2 |
| `task_runner.run_build` | `forge.refrlow.task_runner.run_build` | T2 |
| `diff_miner.log_for_path` | `forge.refrlow.diff_miner.log_for_path` | T1 |

These appear in the capability registry alongside any non-refrlow capabilities, follow the same TTL/scope rules, and go through Sentinel like any other action.

---

## 4. Trust composition

The refrlow trust posture composes cleanly with Hermes's:

### Hermes principles → refrlow implementations

| Hermes principle | Refrlow implementation |
|------------------|------------------------|
| P1: Deterministic dominates probabilistic | Dispatcher is fully deterministic. LLM subagents are advisory; their output is schema-validated and never authorizes action. |
| P2: Verification < generation | Subagent reports include content hashes; main agent can cheaply verify a claim by re-dispatching for the same hash. |
| P3: Intent provenance | Every dispatch carries `intent_root` reference; Sentinel rejects dispatches outside the active intent's scope. |
| P4: Agent never owns secrets | Subagents have no access to Vault. The `secret_fetcher` subagent class is permanently rejected. |
| P5: Observability is a threat surface | Dispatch logs are subject to the same redaction as other audit logs. Subagent reports containing secret patterns are redacted at write time. |
| P6: Subsystem diversity | Critical-path validation (e.g., `validator.safe_to_delete`) can use a different implementation from the primary search subagent. |
| P7: Deletion test | Refrlow as a whole can be removed; main agent falls back to direct reads. Functionality degrades; safety invariants hold. |
| P8: Friction is finite | Dispatch is cheaper than direct read; reduces consent prompts on read-heavy operations. |
| P9: Boring beats clever | Most subagents are deterministic wrappers over `ripgrep`, `find`, `tree-sitter`. Boring on purpose. |

### Hermes invariants → refrlow enforcement

| Invariant | Refrlow check |
|-----------|--------------|
| I1: No model authority over invariants | Dispatcher has no LLM in decision path. |
| I2: Intent root required | All dispatches above T1 must reference a valid intent root with covering scope. |
| I3: Secrets never enter model context | Subagent reports are scanned for secret patterns before reaching Hermes; matches quarantined. |
| I4: Capability tokens short-lived | Subagent TTLs are short by design (typically 5–30 seconds). |
| I5: Audit log append-only | All dispatches and reports are recorded in the tamper-evident audit log. |
| I6: Memory provenance | Subagent reports entering Atlas carry full provenance (subagent, params, time, content hashes). |
| I7: Sentinel blocking deterministic | Dispatch policy enforcement is fully deterministic. |
| I8: Irreversible actions need consent | `task_runner` tasks classified as irreversible (e.g., a hypothetical `run_deploy`) require per-action consent. |
| I9: Capability registry exhaustive | Refrlow's task allowlist *is* a Forge capability registry. Unknown tasks rejected. |
| I12: Observability respects redaction | Dispatch logs route through the standard redaction layer. |

---

## 5. Atlas integration

Subagent reports are valuable structured facts. They belong in Atlas — but as quarantine-tier facts until corroborated.

### Ingestion pattern

```
1. Subagent returns report.
2. Dispatcher validates schema.
3. Dispatcher routes report to:
   - Main agent (as ingested context, with framing)
   - Atlas (as a Q-tier fact, with provenance)
4. Atlas fact carries:
   - source: "subagent:file_miner:find_by_glob:req_abc123"
   - issued_at, completed_at
   - parameters (so query can be re-run)
   - content_hashes (so freshness can be checked)
5. Promotion to A-tier requires:
   - Re-dispatch produces the same result (corroboration), OR
   - User confirms the fact, OR
   - At least 2 independent subagents (e.g., grep_miner and ast_miner) corroborate.
```

### Skill emergence

Refrlow usage will generate skills in the Hermes sense (see `hermes/simulation/SKILLS.md`):

- **SK-XXX — Dispatch-before-read.** Pattern: always dispatch for unknown search spaces; direct-read only for known small files.
- **SK-XXX — Validate before edit.** Pattern: dispatch `validator.safe_to_delete` and `validator.typecheck` before any destructive edit.
- **SK-XXX — Module overview before refactor.** Pattern: dispatch `file_miner.enumerate_tree` + `ast_miner.extract_signatures` + `summarizer.module_overview` as a triplet before planning a multi-file refactor.

These are emergent patterns that the Hermes skill ledger should track over time.

---

## 6. Sentinel integration

Dispatches above T1 route through Sentinel. Typical flow:

```
Main agent (Hermes) → Forge dispatch request →
  Sentinel deterministic checks:
    - Subagent class allowed?
    - Task allowed for class?
    - Scope within active intent root?
    - Budget within per-turn policy?
    - Rate within per-class limit?
  → Sentinel advisory checks (probabilistic, optional):
    - Anomaly detection on dispatch patterns
  → If approved: Forge dispatcher executes subagent
  → Report validated by Forge
  → Report logged to audit + Atlas Q
  → Main agent ingests
```

T1 dispatches (read-only, deterministic subagents on small scopes) may bypass Sentinel for performance, with periodic sampled auditing.

---

## 7. Incident handling

Refrlow-related incidents fit the Hermes failure mode classes:

| Refrlow event | Failure class | Reference |
|---------------|---------------|-----------|
| `denied` (out of scope) | EXPECTED (E4) | Normal control flow |
| `truncated` | EXPECTED | Main agent must replan |
| `escalate` (injection detected in source) | DEGRADED | D7-class equivalent |
| Subagent returns content that triggers main-agent secret canary | CATASTROPHIC | K1 |
| Dispatcher rejects mass-fan-out attempt | EXPECTED | T-R8 mitigated |
| Subagent sandbox escape detected | CRITICAL | C6 |
| Cache poisoning detected | CRITICAL | C-class |

Incidents are recorded in the Hermes `INCIDENTS.md` log, not a separate refrlow log.

---

## 8. ADRs that would result from integration

If you integrate refrlow into a real Hermes deployment, expect to write ADRs covering:

- **ADR-NNNN — Refrlow as Forge implementation pattern.** Documents the decision to use delegated subagents over direct main-agent tool calls.
- **ADR-NNNN — Subagent class registry vs. open extension.** Documents the closed-class approach and what review a new class requires.
- **ADR-NNNN — LLM subagent injection-resistance requirements.** Documents the system-prompt and schema constraints on summarizer-class subagents.
- **ADR-NNNN — Dispatch caching policy.** Documents what gets cached, invalidation rules, and what subagent classes are cache-eligible.
- **ADR-NNNN — Task runner allowlist governance.** Documents the process for adding tasks to the `task_runner` allowlist.

Each follows the template in `hermes/decisions/_TEMPLATE.md`.

---

## 9. What changes in the simulation

If the 60-day simulation were re-run with refrlow inside Forge:

- **Phase I** would show subagent classes being added as capabilities, mirroring Days 1–7.
- **Phase II** would show `summarizer` injection-check events as advisories, similar to the entropy false positives in the original simulation.
- **Phase III**'s INC-004 (web injection) would have an equivalent: a summarizer encountering an injected file would produce an `escalate` report, the same defense-in-depth would catch the downstream effects.
- **Phase IV** would show emergence of dispatch-pattern skills.
- **Phase V**'s INC-008 (correlated failure) would have a refrlow variant: two LLM subagents (e.g., a summarizer and a doc_miner) using the same underlying model could produce correlated wrong answers; the canary pattern (deterministic validator) would catch it.

The shape of the simulation does not change. Refrlow is an *implementation choice* inside Forge, not a restructuring of the doctrine.

---

## 10. The one-line summary

**Refrlow is what Forge looks like when you take cost discipline as seriously as you take security discipline.**

Hermes's existing principles already imply most of refrlow's structure. Refrlow names the pattern, defines the schemas, and gives operators a reference implementation.

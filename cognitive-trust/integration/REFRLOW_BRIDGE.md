# Refrlow ↔ Cognitive Trust Bridge

**Purpose:** Explain the relationship between the `claude-code-refrlow` package and the Cognitive Trust architecture. Show how to migrate from one to the other (or use both side by side).

---

## 1. The relationship in one sentence

**Refrlow is a focused implementation of part of the Retrieval Fabric, optimized for drop-in use with Claude Code. Cognitive Trust is the full architecture, including PKI provenance and the persistent repo graph.**

You can use either. You can use both. Refrlow is a strict subset.

---

## 2. What refrlow has

| Component | Refrlow | Cognitive Trust Fabric |
|-----------|---------|----------------------|
| Dispatcher | ✅ | ✅ (extended) |
| File / Grep / AST miners | ✅ | ✅ (and more classes) |
| Summarizer (LLM hybrid) | ✅ | ✅ |
| Validator subagent class | catalog only | ✅ |
| Task runner subagent class | catalog only | ✅ |
| Schema / Diff / Doc miners | catalog only | ✅ |
| Health / Cross-repo / Embedding miners | not listed | ✅ |
| Per-class budgets | ✅ | ✅ |
| Per-turn caps | ✅ | ✅ |
| Schema-validated reports | ✅ | ✅ |
| Injection scanning | ✅ | ✅ (also at graph write time) |
| Secret scanning | ✅ | ✅ |
| Report framing | ✅ | ✅ |
| **Persistent repo graph** | ❌ | ✅ |
| **Incremental indexing** | ❌ | ✅ |
| **Source attestation on reports** | ❌ | ✅ (CT-I6) |
| **Cognitive PKI integration** | ❌ | ✅ |

Refrlow gives you cost discipline and injection resistance. Cognitive Trust adds persistence and provenance.

---

## 3. Migration path: refrlow → Cognitive Trust

If you've adopted refrlow and want to migrate to the full Fabric:

### Step 1 — Keep using refrlow as-is

The refrlow Dispatcher and miners continue to work. No code changes required in your main agent.

### Step 2 — Add the repo graph backend

Add a SQLite-backed graph store. Modify the Dispatcher to record graph entries as a side effect of dispatches. Miners now write to the graph in addition to returning reports.

This is a non-breaking change for the agent. The agent still sees the same reports.

### Step 3 — Add the Attestation Service

Deploy the PKI Attestation Service. Wire the Dispatcher to call `request_attestation()` after each dispatch, attaching the attestation to the outgoing report.

Update report consumers (agent and downstream) to validate attestations before use.

### Step 4 — Migrate the agent to issue intent roots

Update the main agent's session start to sign an intent root. Pass `intent_root_ref` through every dispatch. The Dispatcher now validates scope containment.

### Step 5 — Adopt generation attestations

When the agent produces an artifact (a code patch, a doc, a deploy plan), it now requests a generation attestation from the PKI. The agent's tooling integration must include this call.

### Step 6 — Adopt validation + review + approval

For artifact classes registered as T3+, the tooling enforces validation/review/approval ceremony.

This is the path. It's intentionally incremental — each step is independently valuable.

---

## 4. Side-by-side usage

You can use refrlow for your interactive coding sessions and Cognitive Trust for your CI/CD pipeline. The reports they produce are interoperable if the schemas align (they do; refrlow's are a strict subset).

Example: developer uses Claude Code with refrlow locally. When changes are committed, CI uses the full Cognitive Trust pipeline to re-mine, re-attest, and validate before deploy.

---

## 5. What changes in the daily experience

For a developer using Claude Code via refrlow today, adopting Cognitive Trust changes:

| Today (refrlow) | With Cognitive Trust |
|----------------|---------------------|
| Dispatcher returns reports | Dispatcher returns reports + attestations |
| Reports good for one turn | Reports may persist in graph; fast re-queries |
| No long-term repo memory | Graph remembers structure across sessions |
| No provenance for code Claude writes | Every generated patch has a signed provenance chain |
| "Trust the AI output" | "Verify the attestation chain before merging" |
| Code reviews are conversational | Code reviews produce signed reviewer attestations |
| Hard to audit "why was this deployed?" | Walk the lineage from the execution attestation |

For most interactive coding, the experience feels similar. The big wins are in:

- Production deploys (lineage = audit gold)
- Incident forensics (chain = clear cause)
- Long-running projects (graph = persistent shared understanding)
- Multi-developer collaboration (attestations attribute work)

---

## 6. What does NOT change

- The agent operating principles in `claude-code-refrlow/prompts/CLAUDE.md` are still correct. Hermes-style discipline applies in both worlds.
- Subagents remain bounded, ephemeral, non-mutating.
- Recursion limits, fan-out caps, scope containment — all the same.
- Injection and secret scanning — same.

You don't lose anything by upgrading.

---

## 7. Refrlow is intentionally smaller

Refrlow exists because **simple, narrow, immediately-usable** is valuable. Not every team needs PKI on day one. The path from "no Fabric" to "refrlow" is a 30-minute install. The path from "no provenance" to "full Cognitive PKI" is a multi-week engineering project.

Pricing structure of cognitive cost:

| Investment | Returns |
|------------|---------|
| Refrlow | Token savings, hallucination resistance, cleaner audit logs |
| + Repo graph | Persistent fast queries, cross-session memory |
| + Cognitive PKI | Cryptographic provenance, lineage, real revocation |

Each step justifies the next. None is wasted.

---

## 8. When to pick which

**Refrlow only:**
- Solo developer
- Pre-production projects
- Trying out the pattern
- Token cost is the primary concern

**Refrlow + repo graph (Fabric core, no PKI):**
- Small team with shared repos
- Long-running projects where re-mining is wasteful
- Want persistent agent knowledge across sessions

**Full Cognitive Trust:**
- Production systems
- Compliance requirements
- Multi-developer collaboration where attribution matters
- Incident-prone environments
- Anywhere the question "who made this change and why?" gets asked

The path between these is continuous. Don't over-invest until the value is there.

---

## 9. Code-level relationship

The refrlow Python package (`claude-code-refrlow/skeleton/refrlow/`) and the Cognitive Trust Python skeleton (`cognitive-trust/skeleton/`) share a compatible protocol layer. A refrlow report can be enriched with an attestation by passing it through the Attestation Service; the result is a valid Cognitive Trust attested report.

This means you don't have to rewrite the miner implementations. The CT skeleton imports and extends refrlow types where applicable.

---

## 10. Naming

Different names for compatible things:

| Refrlow term | Cognitive Trust term | Notes |
|--------------|---------------------|-------|
| Subagent | Miner | Same concept; CT prefers "miner" because the catalog includes non-LLM workers |
| Subagent class | Miner class | Same |
| Dispatch report | Miner report | Same |
| Dispatcher | Fabric Dispatcher | Same role; CT extends with graph writes and attestation |
| Refrlow protocol | Fabric protocol | Same schemas with attestation envelope added |

Naming is cheap; the architecture is what matters.

---

## 11. The honest summary

If you're building production agent infrastructure, you want Cognitive Trust. If you're optimizing tokens in a developer's day-to-day, refrlow is enough.

Don't mistake "refrlow is sufficient for my workflow" for "Cognitive Trust is overkill for production." Different problems, different answers.

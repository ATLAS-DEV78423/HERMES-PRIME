# Refrlow Cost Model

**Purpose:** Make the dispatch-vs-read-directly decision quantitative. Document the token economics so the main agent can reason about its own resource use, and so operators can tune budgets sensibly.

---

## The basic accounting

For any retrieval task, there are three cost components:

1. **Main agent tokens.** Tokens consumed in the expensive model's context.
2. **Subagent tokens.** Tokens consumed in the cheap model's context (zero for deterministic subagents).
3. **Dispatcher overhead.** Tokens consumed for the request envelope and report wrapping (small, fixed cost).

A dispatch is worth it when:

```
main_agent_cost(direct_read)  >  main_agent_cost(report) + subagent_cost + overhead
```

Since the main agent's cost is typically 10–50x the subagent's, this is a wide margin.

---

## Worked examples

Token costs below are illustrative — adjust to your actual model pricing. The ratios are what matter.

### Example 1 — Find all files importing a module

**Direct read approach:**
- Main agent runs `grep -r "import.*auth"` mentally
- Reads each candidate file to confirm
- Estimated tokens: 200 files × ~150 tokens = ~30,000 tokens
- At $3/M for Sonnet input: **$0.09**

**Dispatch approach:**
- Request envelope: ~200 tokens
- Subagent runs ripgrep deterministically (zero LLM cost)
- Report: ~800 tokens (8 matches with snippets)
- Main agent ingests: ~1,000 tokens
- At $3/M: **$0.003**

**Ratio: 30x cheaper via dispatch.**

### Example 2 — Understand a file's purpose

**Direct read approach:**
- Main agent reads the file: 218 lines × ~6 tokens = ~1,300 tokens
- Reasoning over content
- Total: ~1,300 tokens for reading + reasoning overhead

**Dispatch approach (purpose_summary):**
- Request envelope: ~200 tokens
- Summarizer (Haiku) reads file and produces summary: ~1,300 tokens at Haiku pricing
- Report: ~150 tokens (the summary)
- Main agent ingests: ~350 tokens
- Sonnet @ $3/M for 350 tokens: $0.001
- Haiku @ $0.25/M for 1,300 tokens: $0.0003
- Total: **$0.0013**

**Direct read total: ~$0.004**

**Ratio: 3x cheaper via dispatch.** Smaller win, but compounds across many files.

### Example 3 — Refactor planning across 80 files

**Direct read approach:**
- Read all 80 files: ~120,000 tokens
- Reason over structure: ~5,000 tokens
- Context window pressure: significant
- Sonnet @ $3/M: **$0.375**

**Dispatch approach:**
- `file_miner.enumerate_tree`: ~500 tokens
- `ast_miner.extract_signatures` × 80 files (deterministic): ~3,000 tokens of report
- `summarizer.module_overview`: ~1,500 tokens of report
- Main agent now has structured map: ~5,000 total tokens in main context
- Sonnet @ $3/M for ingestion: $0.015
- Haiku @ $0.25/M for summarizer work: $0.005
- Total: **$0.02**

**Ratio: ~19x cheaper via dispatch.** And the main agent retains 115,000 tokens of context for actual reasoning.

---

## Breakeven thresholds (rules of thumb)

These are heuristics, not laws. Tune to your environment.

| Task type | Read directly if | Dispatch if |
|-----------|------------------|-------------|
| Find files by name | ≤ 3 known paths | Any unknown search space |
| Find files by content | Never (always dispatch grep_miner) | Always |
| Read a specific small file | ≤ 200 lines AND will edit line-by-line | > 200 lines OR will only summarize |
| Find symbol definition | If you already know the file | If you don't know the file |
| Trace callers | Never (always ast_miner) | Always |
| Understand a module | ≤ 3 small files | Any larger scope |
| Run tests | N/A — always dispatch | Always |
| Validate before edit | N/A — always dispatch | Always |

**Default to dispatch.** The cost of an unnecessary dispatch is small (overhead). The cost of an unnecessary direct read is the entire file's worth of tokens.

---

## Budget guidance

Each subagent class has default budgets in `PROTOCOLS.md`. Operators may tune them based on cost sensitivity.

### Conservative profile (cost-sensitive)

```yaml
file_miner:
  max_tokens: 500
  max_results: 30
grep_miner:
  max_tokens: 1500
  max_results: 30
  context_lines: 1
ast_miner:
  max_tokens: 1500
  max_results: 30
summarizer:
  max_tokens: 300
  max_words: 60
validator:
  max_tokens: 800
task_runner:
  max_tokens: 2000
  ttl_seconds: 60
```

### Standard profile (default)

```yaml
file_miner:
  max_tokens: 1000
  max_results: 100
grep_miner:
  max_tokens: 2500
  max_results: 100
  context_lines: 2
ast_miner:
  max_tokens: 2500
  max_results: 100
summarizer:
  max_tokens: 600
  max_words: 120
validator:
  max_tokens: 1500
task_runner:
  max_tokens: 4000
  ttl_seconds: 120
```

### Generous profile (heavy-lifting sessions)

```yaml
file_miner:
  max_tokens: 2000
  max_results: 500
grep_miner:
  max_tokens: 5000
  max_results: 300
  context_lines: 3
ast_miner:
  max_tokens: 5000
  max_results: 300
summarizer:
  max_tokens: 1200
  max_words: 250
validator:
  max_tokens: 3000
task_runner:
  max_tokens: 10000
  ttl_seconds: 300
```

---

## Per-turn dispatch budget

To prevent runaway dispatching from a confused main agent, total per-turn token spend across subagents is capped.

Recommended defaults:

| Profile | Per-turn max tokens | Per-turn max dispatches |
|---------|--------------------|-----------------------|
| Conservative | 10,000 | 5 |
| Standard | 25,000 | 12 |
| Generous | 60,000 | 30 |

When the budget is hit, the dispatcher returns `denied: dispatch_budget_exceeded`. The main agent must replan, perhaps by asking the user whether to widen the budget for this turn.

---

## When dispatching is not worth it

Be honest about cases where dispatch overhead exceeds benefit:

### 1. Known single small file

If you know the exact path and the file is < 100 lines, direct read is fine. Dispatch overhead (~200 tokens for envelope + ~100 for report wrapping) is comparable to the file itself.

### 2. Iterative read-edit-read loops on the same file

If the main agent is actively editing a file, repeatedly re-reading it via subagent dispatch is silly. Read once directly, edit in context, write back.

### 3. Trivial known lookups

"What's in package.json?" — just read it.

### 4. When the subagent itself would need to do reasoning the main agent must do anyway

Don't dispatch a summarizer to compress a file you're about to refactor line-by-line. You need the full content; the summary doesn't help.

---

## Caching considerations

Subagent reports can be cached by `(subagent, task, params hash, scope hash, content hash)`. Cache hits are free.

**Caveats:**
- Cache must be invalidated on file modification. Use mtime + content hash, not mtime alone.
- LLM-based subagent reports (summarizer, doc_miner) should cache more conservatively — model changes invalidate.
- Cache hit rates are highest in repeated planning passes over an unchanged codebase. Initial exploration sees few hits.

**Recommended:** Implement caching at the dispatcher level, transparent to the main agent. The main agent dispatches as if no cache exists; the dispatcher serves cache hits where appropriate and notes `cache: hit` in the report.

---

## Measuring the win

Track these metrics to validate the cost model:

| Metric | Target | Bad signal |
|--------|--------|-----------|
| Main agent tokens per turn | Decreasing trend | Increasing trend (dispatch isn't being used) |
| Subagent tokens per turn | Increasing trend | Static (dispatch is underused) |
| Subagent / main token ratio | Growing | < 0.1 (almost no dispatch happening) |
| Cache hit rate (after warm-up) | 30–60% | < 5% (cache is broken) |
| `truncated` rate | < 5% of dispatches | > 20% (budgets too tight) |
| `escalate` rate | < 1% | > 5% (subagents seeing weird content; investigate) |

A healthy refrlow deployment has the main agent burning **fewer** tokens per session than a no-dispatch baseline, while accomplishing more work and producing a richer audit trail.

---

## Honest caveat

The cost model assumes pricing where the main model is 10–50x more expensive than the subagent model. If you're running everything on the same local model, the savings shrink to "reduced context pollution" only. That's still worthwhile, but the dollar argument weakens.

The other argument — **discipline, hallucination resistance, audit trail** — holds regardless of pricing. Dispatch even on local-only setups for those reasons.

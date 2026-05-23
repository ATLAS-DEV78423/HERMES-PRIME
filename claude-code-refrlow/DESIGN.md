# Refrlow Architecture Design

**Status:** Living document
**Companion to:** `PROTOCOLS.md`, `SUBAGENT_TAXONOMY.md`, `SECURITY.md`

---

## 1. Problem statement

The dominant pattern for coding agents today is: the main model does everything, including navigation. The model reads files, lists directories, greps for symbols, traces imports. All of this consumes the same context window the model uses for reasoning.

This produces three pathologies:

### 1.1 The context budget paradox

The main model's context is its most precious resource. Every byte of file content displaces a byte of reasoning space. A 200K context window sounds enormous until you read three large modules and a test file. Then you have 40K left for actually thinking.

### 1.2 The cost-of-search paradox

Finding a file should cost approximately nothing. In a typical codebase, `grep -r "function parseConfig" .` runs in milliseconds and costs zero dollars. When the main model performs the equivalent search by reading files one by one, the cost is hundreds to thousands of times higher with no quality benefit.

### 1.3 The hallucination-under-uncertainty paradox

When the model is uncertain about a file location or symbol definition, the cheap-feeling response is to guess. Guessing produces wrong edits to wrong files. The correct response — exhaustive search — feels expensive and is often skipped. Refrlow makes exhaustive search cheap, removing the incentive to guess.

---

## 2. The refrlow pattern

**Refrlow** = "reference-flow." The main agent reasons in terms of *references* (paths, symbols, hashes, line ranges) rather than raw content. Subagents convert references to content on demand and validate that content before it flows into the main context.

### 2.1 Three roles

| Role | Job | Cost class |
|------|-----|-----------|
| **Main Agent** | Plan, reason, write code, talk to user | Expensive (Claude Sonnet / Opus) |
| **Dispatcher** | Validate requests, sandbox subagents, validate reports | Free (deterministic code) |
| **Subagent** | Execute one narrow task, return structured report | Cheap (deterministic tool, or small model like Haiku / local) |

### 2.2 The flow

```
1. Main agent identifies a context need.
   Example: "I need to refactor the auth flow. Find all files that import from `auth/`."

2. Main agent emits a typed dispatch request.
   { "subagent": "file_miner",
     "task": "find_imports_of",
     "params": { "module": "auth/", "scope": "src/**" },
     "budget_tokens": 2000,
     "ttl_seconds": 30 }

3. Dispatcher validates the request against schema and policy.

4. Dispatcher spawns a sandboxed subagent with only the data it needs.

5. Subagent executes (often as a deterministic tool call, e.g. ripgrep + parse).

6. Subagent emits a typed report.
   { "status": "ok",
     "matches": [
       { "path": "src/api/login.ts", "line": 5, "import_form": "import { auth }" },
       ...
     ],
     "elapsed_ms": 84,
     "scope_searched": "src/**",
     "content_hashes": {...} }

7. Dispatcher validates the report against schema.

8. Main agent receives the structured report (compact, validated, sourced).
   It never saw the directory tree, the raw file bytes, or the search process.
```

The main agent now has exactly the information it needs to plan, in a fraction of the tokens.

---

## 3. Why subagents instead of just tools

A reasonable question: doesn't Claude Code already have tools like `read`, `glob`, `grep`? Why introduce subagents?

The distinction is real and important:

### Tools

- Stateless function calls.
- Output goes directly into the main agent's context.
- No interpretation, no compression, no validation layer beyond schema.
- The main agent must reason about the raw output.

### Subagents

- Stateful workers with their own (small) context.
- Output is a **report** — structured, summarized, validated before main-agent ingestion.
- Can chain tools and do interpretation (e.g. "search, filter, rank, summarize, return top 10 with snippets").
- Can use a different (cheaper) model than the main agent.
- Operate in a sandbox with bounded permissions.

The difference between a tool and a subagent is the difference between "give me the output of `find`" and "give me the 10 files most likely relevant to refactoring the auth flow, with one-line summaries and the relevant line numbers."

**The subagent absorbs the search complexity. The main agent sees only the answer.**

---

## 4. The dispatch lifecycle

Every subagent invocation goes through six phases:

### Phase 1 — Justification

The main agent must articulate *why* it needs the dispatch. Not for show; for auditability and for the main agent's own discipline. A dispatch without a clear justification is usually a sign the main agent is exploring rather than executing.

### Phase 2 — Request

A typed request matching one of the schemas in `PROTOCOLS.md`. Includes:
- subagent class
- task
- parameters
- budget (max tokens, max time)
- expected output schema

### Phase 3 — Validation

Dispatcher checks:
- Is this subagent class allowed?
- Is the task valid for this class?
- Are parameters within bounds?
- Does the requested budget fit policy?
- Is the requesting scope within the active workspace?

### Phase 4 — Execution

Subagent runs in a sandbox:
- Bounded filesystem access (read-only by default; never main-agent's vault/secrets)
- Bounded network access (usually none)
- Bounded compute time
- Bounded output size
- Distinct process, distinct token budget

### Phase 5 — Report validation

Dispatcher checks the returned report:
- Schema-valid?
- Within size budget?
- Provenance fields present (paths, hashes, timestamps)?
- No suspicious content (e.g., instruction-like text from file contents that could be a prompt-injection vector)?

### Phase 6 — Ingestion

Validated report enters the main agent's context as structured data, with explicit framing: *this is a subagent report from [class] dated [time], not user instructions.*

---

## 5. The "main agent sees only references" principle

This is the load-bearing principle of refrlow.

The main agent works with **references**: `src/auth/login.ts:42-58`, `symbol:parseConfig`, `commit:abc123`. Concrete content is fetched on demand, scoped to exactly what's needed, validated before ingestion.

This produces several emergent benefits:

- **Token discipline.** You can't waste tokens on content you never see.
- **Hallucination resistance.** References are either valid (subagent confirms) or not (subagent returns "not found"). The main agent can't confabulate a file that doesn't exist because the dispatch fails.
- **Audit trail.** Every piece of context the main agent reasoned over is traceable to a specific subagent dispatch with provenance.
- **Caching.** References are stable; content can be cached by hash without invalidating the agent's plans.
- **Parallelism.** Multiple subagents can run concurrently while the main agent waits. (Try doing that with the main model reading 10 files sequentially.)

---

## 6. Decision: when to dispatch vs when to read directly

Not every retrieval should be a subagent dispatch. Some heuristics:

**Dispatch when:**
- The search space is unknown or large (≥3 files unread or ≥1 directory unenumerated)
- The same retrieval is needed by multiple downstream steps (subagent can return ranked, deduplicated, summarized)
- The result needs structured filtering or ranking
- The content is sensitive (subagent enforces redaction before ingestion)
- The retrieval might be expensive in tokens (large files, log-scale codebases)

**Read directly when:**
- The exact path is known and small (≤2 known files)
- The content will be reasoned over line-by-line
- The retrieval is part of an active edit cycle (read → think → edit → re-read)

**Always dispatch:**
- Anything that crosses the workspace root (or worse, leaves the filesystem)
- Anything that requires entropy or pattern scanning on content
- Anything that needs to look at >5 files
- Anything where the result will be summarized rather than reasoned over verbatim

See `COST_MODEL.md` for quantitative breakeven analysis.

---

## 7. Failure handling

Subagents fail. The architecture must surface failures, not paper over them.

### 7.1 Failure modes

- **Timeout.** Subagent exceeded TTL. Report: `{ "status": "timeout", "partial_results": [...] }`
- **Budget exceeded.** Output would exceed budget. Report: `{ "status": "truncated", "matches_returned": 50, "estimated_total": 230 }`
- **Schema violation in source.** Subagent encountered malformed input (e.g. binary file when expecting text). Report: `{ "status": "skipped", "reason": "binary", "paths": [...] }`
- **Permission denied.** Subagent attempted out-of-sandbox access. Report: `{ "status": "denied", "attempted": "/etc/passwd", "reason": "outside workspace" }`
- **No results.** Search succeeded but found nothing. Report: `{ "status": "ok", "matches": [], "scope_searched": "..." }`

### 7.2 The main agent must handle these

A `"truncated"` result with 50 of 230 matches is **not** "50 matches found." The main agent must either widen the budget and re-dispatch, narrow the query, or surface to the user that the result is partial.

The dispatcher enforces this by **never collapsing failure into success**. Every report carries an explicit status field.

---

## 8. What refrlow is not

To prevent feature drift:

- **Not a general agent framework.** This is specifically for delegated retrieval and bounded execution by a main coding agent. Don't bolt on planning, dialogue, or long-running workflows.
- **Not autonomous.** Subagents do exactly what they're dispatched to do, return, and die. No standing processes.
- **Not a router.** This is not "send the task to the cheapest model that can do it." It's "decompose the task so retrieval happens outside the main context."
- **Not a multi-agent collaboration system.** Subagents do not talk to each other. They talk to the dispatcher. The dispatcher reports to the main agent.
- **Not a replacement for good tools.** Refrlow uses `ripgrep`, `find`, `tree-sitter`, `ast-grep`, etc. internally. It does not reinvent them.

---

## 9. Open problems

These are honest gaps, not solved problems:

### 9.1 Subagent hallucination

If a subagent uses an LLM (e.g. a Haiku model summarizing a file), it can hallucinate. Mitigation: subagent reports include hashes of source content; main agent can spot-check. Not a full solution.

### 9.2 Cross-dispatch caching

If two dispatches need overlapping data, naive implementation duplicates work. A cache helps but introduces staleness issues (file changed since cache hit). Open: cache invalidation strategy.

### 9.3 The dispatcher's policy DSL

As policies grow ("don't dispatch grep over node_modules", "redact .env files", "summarizer subagents need higher-tier consent"), the policy layer becomes a small language. This will eventually need its own discipline (see Hermes doctrine on policy engines becoming DSLs).

### 9.4 Subagent escalation

A subagent might legitimately need to escalate ("I found something suspicious in this file, please review before I summarize it"). The protocol allows this via the `escalate` status, but the main agent's handling of escalations is currently ad hoc.

---

## 10. Summary

Refrlow makes the main agent **expensive and lean**: it reasons, it doesn't browse. Subagents are **cheap and disposable**: they fetch, they report, they die. The dispatcher is the **deterministic spine**: it validates, sandboxes, and audits.

The benefit is not just cost. It is **discipline**: the main agent operates on validated, sourced, scoped reports rather than on the raw chaos of a filesystem. That discipline is what makes long-horizon coding work possible without context collapse.

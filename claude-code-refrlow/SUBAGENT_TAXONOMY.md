# Refrlow Subagent Taxonomy

**Purpose:** Define the classes of subagent that exist in refrlow. Each class has a single, well-defined responsibility. Adding a new class requires a clear gap in coverage and a design review — see "Anti-classes" at the bottom.

---

## Design principle

A subagent class is justified if and only if:

1. It has a **single responsibility** expressible in one sentence.
2. Its output schema is **fixed and small**.
3. It can be implemented **deterministically when possible** (no LLM), and only uses an LLM when interpretation is genuinely required.
4. It does **not** overlap with another existing class.

Classes that fail any of these are merged, split, or rejected.

---

## The classes

### 1. File Miner — `file_miner`

**Responsibility:** Find files matching path or metadata criteria. Return list of paths with metadata.

**Determinism:** 100% deterministic. Implemented over `find`, `glob`, `fd`.

**Tasks:**

| Task | Params | Returns |
|------|--------|---------|
| `find_by_glob` | `pattern`, `scope` | list of paths matching glob |
| `find_by_extension` | `ext`, `scope` | list of paths with extension |
| `find_recent` | `since`, `scope` | list of recently-modified paths |
| `find_large` | `min_bytes`, `scope` | list of paths over size threshold |
| `enumerate_tree` | `root`, `max_depth` | structured directory tree (paths only, no content) |

**Cost class:** Free (deterministic). Reports typically <1KB.

**Example dispatch:**
```json
{
  "subagent": "file_miner",
  "task": "find_by_glob",
  "params": { "pattern": "**/*.test.ts", "scope": "src/" },
  "budget_tokens": 500,
  "ttl_seconds": 5
}
```

---

### 2. Grep Miner — `grep_miner`

**Responsibility:** Search file contents for patterns. Return matches with file, line number, and surrounding context.

**Determinism:** 100% deterministic. Implemented over `ripgrep`.

**Tasks:**

| Task | Params | Returns |
|------|--------|---------|
| `search_text` | `pattern`, `scope`, `regex?`, `context_lines?` | matches with `path:line` + snippet |
| `search_word` | `word`, `scope` | whole-word matches |
| `count_matches` | `pattern`, `scope` | counts per file |
| `find_imports_of` | `module`, `scope` | files importing the given module |

**Cost class:** Free (deterministic). Reports scale with match count; budget enforces truncation.

**Example dispatch:**
```json
{
  "subagent": "grep_miner",
  "task": "find_imports_of",
  "params": { "module": "@/lib/auth", "scope": "src/" },
  "budget_tokens": 2000,
  "ttl_seconds": 10
}
```

---

### 3. AST Miner — `ast_miner`

**Responsibility:** Find symbols, definitions, references, and structural patterns using language-aware parsing.

**Determinism:** 100% deterministic. Implemented over `tree-sitter` or `ast-grep`.

**Tasks:**

| Task | Params | Returns |
|------|--------|---------|
| `find_definition` | `symbol`, `language`, `scope` | path + line + signature |
| `find_references` | `symbol`, `language`, `scope` | list of call/reference sites |
| `find_callers_of` | `function`, `language`, `scope` | files and lines that call the function |
| `find_pattern` | `ast_pattern`, `language`, `scope` | structural matches (e.g., "all async functions returning Promise<T>") |
| `extract_signatures` | `path`, `language` | function/class signatures only, no bodies |

**Cost class:** Free for small scopes; can be significant for large repos (parse time). Reports are structured and compact.

**Example dispatch:**
```json
{
  "subagent": "ast_miner",
  "task": "find_callers_of",
  "params": { "function": "parseConfig", "language": "typescript", "scope": "src/" },
  "budget_tokens": 1500,
  "ttl_seconds": 15
}
```

---

### 4. Summarizer — `summarizer`

**Responsibility:** Compress a single large file or a small set of files into a structured summary at a specified granularity.

**Determinism:** Hybrid. Structural extraction (imports, exports, function signatures) is deterministic. Prose summaries use a small LLM (Haiku or local Llama-class).

**Tasks:**

| Task | Params | Returns |
|------|--------|---------|
| `signature_summary` | `path` | imports, exports, top-level signatures — purely structural |
| `purpose_summary` | `path`, `max_words` | 1-paragraph "what this file does" — LLM-generated |
| `diff_summary` | `path`, `from_commit`, `to_commit` | high-level description of changes |
| `module_overview` | `paths[]` | structural map of a module — purely structural |

**Cost class:** `signature_summary` and `module_overview` are free. `purpose_summary` and `diff_summary` use a small model — typically 10–100x cheaper than main-agent reading the file.

**Risk note:** LLM-based summarizers are the most prompt-injectable subagent class. File contents may contain instructions targeting the summarizer's model. The dispatcher applies an injection-resistant system prompt (see `prompts/miner-system-prompt.md`) and validates that summaries do not contain references to actions, capabilities, or instructions.

**Example dispatch:**
```json
{
  "subagent": "summarizer",
  "task": "purpose_summary",
  "params": { "path": "src/lib/payment-flow.ts", "max_words": 80 },
  "budget_tokens": 500,
  "ttl_seconds": 20
}
```

---

### 5. Validator — `validator`

**Responsibility:** Check that a proposed edit, command, or file change conforms to a schema, lints clean, or passes a specific predicate.

**Determinism:** 100% deterministic in most cases (uses linters, type-checkers, custom predicates).

**Tasks:**

| Task | Params | Returns |
|------|--------|---------|
| `lint` | `path`, `linter?` | pass/fail + issues |
| `typecheck` | `path` or `paths[]` | pass/fail + errors |
| `schema_validate` | `path`, `schema_path` | pass/fail + violations |
| `test_subset` | `paths[]` | test pass/fail counts |
| `safe_to_delete` | `path` | dependents analysis: is anything still referencing this? |

**Cost class:** Free (deterministic tools).

**Example dispatch:**
```json
{
  "subagent": "validator",
  "task": "safe_to_delete",
  "params": { "path": "src/lib/legacy-helpers.ts" },
  "budget_tokens": 1000,
  "ttl_seconds": 30
}
```

---

### 6. Task Runner — `task_runner`

**Responsibility:** Execute a single, named, allowlisted command in a sandbox and return its output. **Not a general shell.** Allowlist only.

**Determinism:** Fully deterministic command execution; output is whatever the command produces.

**Tasks:**

| Task | Params | Returns |
|------|--------|---------|
| `run_tests` | `selector?`, `framework?` | test results (pass/fail per test) |
| `run_build` | `target?` | build status, errors |
| `run_typecheck` | `paths?` | type errors |
| `run_formatter` | `paths` | formatted output or diff |
| `run_named_task` | `task_name` | output of a predefined task (from `package.json` scripts, Makefile targets, etc.) |

**Cost class:** Free at dispatch; the command itself costs compute time. Output is captured and schema-checked before return.

**Risk note:** Task runners are the highest-risk subagent class because they execute real commands. They are limited to an explicit allowlist managed at the dispatcher level. **No arbitrary shell.** Adding a task to the allowlist requires the same review as adding a Hermes capability.

**Example dispatch:**
```json
{
  "subagent": "task_runner",
  "task": "run_tests",
  "params": { "selector": "auth", "framework": "vitest" },
  "budget_tokens": 3000,
  "ttl_seconds": 120
}
```

---

### 7. Diff Miner — `diff_miner`

**Responsibility:** Inspect git history, diffs, blames, and file evolution. Read-only.

**Determinism:** 100% deterministic. Implemented over `git`.

**Tasks:**

| Task | Params | Returns |
|------|--------|---------|
| `log_for_path` | `path`, `since?` | commits touching the path |
| `blame_for_lines` | `path`, `start_line`, `end_line` | last-modified commits per line |
| `diff_between` | `from`, `to`, `scope?` | structured diff |
| `who_changed` | `path`, `since?` | authors who modified the path |
| `last_modified` | `path` | most recent commit + timestamp |

**Cost class:** Free (git is fast).

---

### 8. Doc Miner — `doc_miner`

**Responsibility:** Extract structured information from documentation files (READMEs, design docs, API docs). Optimized for "find the section about X" style queries.

**Determinism:** Structural extraction (heading hierarchy, code blocks, tables) is deterministic. Semantic queries ("which section discusses authentication?") use a small LLM.

**Tasks:**

| Task | Params | Returns |
|------|--------|---------|
| `extract_section` | `path`, `heading_pattern` | matched sections with content |
| `list_headings` | `path` | heading hierarchy |
| `find_section_about` | `path` or `paths[]`, `topic` | sections semantically relevant to topic |
| `extract_code_blocks` | `path`, `language?` | code blocks from doc |

**Risk note:** Same as Summarizer for LLM-based tasks.

---

## Anti-classes (deliberately not built)

These are subagents that have been considered and rejected. Documenting them prevents re-proposal.

### `general_agent` (rejected)

**Why proposed:** "What if a subagent could do anything?"
**Why rejected:** Destroys the entire model. A general subagent is just another main agent. The point of refrlow is *narrow* delegation.

### `editor` (rejected)

**Why proposed:** "What if a subagent could make edits?"
**Why rejected:** Edits are the main agent's responsibility. Delegating edits means the main agent isn't reasoning over what's being changed. Subagents fetch and validate; they don't mutate.

### `planner` (rejected)

**Why proposed:** "Subagent that breaks down a task into steps."
**Why rejected:** Planning is the main agent's responsibility. Delegating it makes the main agent a coordinator, not a reasoner.

### `web_browser` (rejected for now)

**Why proposed:** Fetch external web content.
**Why rejected for now:** Massive injection surface (see Hermes T1). May be added later with strict sandboxing and quarantine treatment of all returned content. Not a baseline subagent class.

### `secret_fetcher` (permanently rejected)

**Why proposed:** "Subagent that retrieves credentials when needed."
**Why permanently rejected:** Violates the entire trust model. Secrets are handled by the vault layer (in Hermes) or by environment-bound execution (in Claude Code workflows). A subagent that fetches secrets is a credential-laundering service.

### `summary_chain` (rejected)

**Why proposed:** "Summarizer that calls itself recursively to handle very large inputs."
**Why rejected:** Recursive LLM-based summarization amplifies hallucination compounding. Better: deterministic chunking → parallel structural summary → main-agent synthesis if needed.

---

## Class hierarchy summary

```
SUBAGENT
├── Deterministic (no LLM)
│   ├── file_miner
│   ├── grep_miner
│   ├── ast_miner
│   ├── validator
│   ├── task_runner
│   └── diff_miner
└── Hybrid (LLM where needed)
    ├── summarizer
    └── doc_miner
```

**Default to deterministic.** Use LLM-based subagents only when interpretation is genuinely required, and treat their output as untrusted until validated.

---

## Composition patterns

Subagents are single-purpose, but the main agent commonly composes them:

### Pattern: "Understand this module before refactoring"

```
1. file_miner: enumerate_tree(root="src/auth/", max_depth=2)
   → returns directory structure

2. ast_miner: extract_signatures(path=each .ts file)
   → returns function/class signatures

3. summarizer: module_overview(paths=signatures)
   → returns structural map

4. ast_miner: find_references(symbol=public exports, scope="src/")
   → returns dependency graph
```

Total token cost to main agent: ~5KB of structured data.
If the main agent had done this manually: ~80–200KB of file content.

### Pattern: "Find the file that does X"

```
1. grep_miner: search_text(pattern="X", scope="src/")
   → returns candidate locations

2. ast_miner: extract_signatures(path=top-ranked candidates)
   → narrows to likely files

3. summarizer: purpose_summary(path=top 2 candidates, max_words=50)
   → confirms intent

4. Main agent picks file, reads it directly for the edit.
```

### Pattern: "Validate before merging an edit"

```
1. validator: lint(path=edited files)
2. validator: typecheck(paths=edited files + dependents)
3. task_runner: run_tests(selector=relevant test suite)
4. validator: safe_to_delete(path=removed files, if any)
```

All four can run in parallel. Main agent sees pass/fail summary.

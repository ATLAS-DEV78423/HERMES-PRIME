# Refrlow for Claude Code

**A reference-flow architecture for delegated context retrieval and bounded subagent dispatch.**

The core idea: the expensive main agent should never spend its own context window walking directories, grepping repos, or scanning files. It dispatches cheap, narrow, short-lived **subagents** that do the work and report back with precisely the artifacts needed.

This is not just a token-cost optimization. It is a **trust-boundary architecture**: subagents are constrained, sandboxed, and short-lived; their reports are validated before they enter the main agent's reasoning context.

---

## The core problem this solves

Modern coding agents (Claude Code included) hit three failure modes when they need to find things:

1. **Token waste.** Every `ls`, `grep`, `cat`, and re-read pulls bytes into the main context window. Multi-file refactors burn six-figure token counts on navigation alone.
2. **Context pollution.** Irrelevant file contents, log spam, and dead-end paths poison the working context. Quality of reasoning degrades as context fills with noise.
3. **Hallucinated locations.** Without grounded retrieval, the agent confabulates file paths, line numbers, and function names. Then it edits the wrong place.

Refrlow addresses all three by introducing **subagents** — narrowly-scoped workers that operate outside the main context, do exactly one job, and return structured reports.

---

## What's in this directory

```
claude-code-refrlow/
├── README.md                          (this file)
├── DESIGN.md                          The architecture spec
├── PROTOCOLS.md                       Subagent request/response schemas
├── SUBAGENT_TAXONOMY.md               File-miners + the other subagent classes
├── COST_MODEL.md                      Token accounting and when to dispatch
├── SECURITY.md                        Trust boundaries and threat model
├── HERMES_INTEGRATION.md              How this slots into the Hermes architecture
├── prompts/
│   ├── CLAUDE.md                      Drop-in system prompt for Claude Code
│   ├── miner-system-prompt.md         System prompt for file-miner subagents
│   └── runner-system-prompt.md        System prompt for task-runner subagents
└── skeleton/
    ├── refrlow/                       Python implementation skeleton
    │   ├── __init__.py
    │   ├── dispatcher.py              Main-agent-side dispatcher
    │   ├── protocol.py                Request/response schemas
    │   ├── sandbox.py                 Subagent sandboxing
    │   ├── reports.py                 Report validation
    │   └── miners/
    │       ├── __init__.py
    │       ├── base.py                Base Miner class
    │       ├── file_miner.py          Find files matching criteria
    │       ├── grep_miner.py          Search content
    │       ├── ast_miner.py           Find symbols / definitions
    │       └── summarizer.py          Compress large files
    └── tests/
        ├── test_protocol.py
        └── test_file_miner.py
```

---

## Quick mental model

```
                   ┌────────────────────────────┐
                   │   Main Agent (Claude Code) │
                   │   - planning               │
                   │   - reasoning              │
                   │   - editing                │
                   │   - user dialogue          │
                   └─────────────┬──────────────┘
                                 │
                                 │ dispatches typed requests
                                 │ receives validated reports
                                 │
                   ┌─────────────▼──────────────┐
                   │     Refrlow Dispatcher     │
                   │   - validates requests     │
                   │   - sandboxes subagents    │
                   │   - validates reports      │
                   │   - enforces budgets       │
                   └─────────────┬──────────────┘
                                 │
            ┌────────────────────┼────────────────────┐
            │                    │                    │
       ┌────▼─────┐         ┌────▼─────┐         ┌────▼─────┐
       │  File    │         │  Grep    │         │  AST     │
       │  Miner   │         │  Miner   │         │  Miner   │
       └──────────┘         └──────────┘         └──────────┘
       (cheap model         (cheap model         (deterministic
        or pure code)        or pure code)        AST tool)
```

**The main agent never sees the directory tree.** It sees structured reports: "the symbol `parseConfig` is defined at `src/lib/config.ts:42`, used at 14 sites (locations attached), test coverage at 78%."

---

## Read in this order

1. **`DESIGN.md`** — what refrlow is and why
2. **`SUBAGENT_TAXONOMY.md`** — the classes of subagents and what each does
3. **`PROTOCOLS.md`** — the request/response schemas
4. **`COST_MODEL.md`** — when dispatching is worth it
5. **`SECURITY.md`** — trust boundaries
6. **`prompts/CLAUDE.md`** — the drop-in system prompt
7. **`skeleton/`** — the Python reference implementation
8. **`HERMES_INTEGRATION.md`** — only if you also care about the Hermes doctrine

---

## Design principles (short version)

1. **Subagents are bounded.** Narrow scope, short TTL, structured output schema, no main-context access.
2. **Reports are validated before ingestion.** Subagent output is untrusted input until schema-checked and source-pinned.
3. **Cheap by default.** Use deterministic tools (find, grep, tree-sitter) when possible. Use small LLMs when not. Never use the main model for retrieval.
4. **Reports include provenance.** Every returned fact carries the exact path, line number, content hash, and timestamp.
5. **Dispatch is explicit.** The main agent must justify a dispatch ("I need to find all callers of X to plan the refactor"). This is auditable.
6. **No silent retries.** A failed subagent surfaces the failure; the main agent decides whether to retry, refine, or give up.

The rest of the docs operationalize these.

# Retrieval Fabric Architecture

**Purpose:** Define the architecture of the bounded miner system that converts filesystems, repos, logs, and external data into structured, signed, attested reports for the main agent to consume.

This is the generalized, production-grade version of the refrlow pattern. Refrlow is one implementation; the Fabric is the architecture.

---

## 1. The cost problem this addresses

A coding agent that does its own navigation burns 70–90% of its tokens on mechanical operations: directory listing, file reading for orientation, dependency tracing, log scanning. None of this is reasoning. All of it is expensive.

A coding agent operating against the Fabric burns those same operations against deterministic miners with tiny token cost and structured returns. Reasoning budget is preserved for actual reasoning.

The result is not just cheaper. The reasoning is *better*, because the context window is not polluted with raw file bytes.

---

## 2. Components

### 2.1 The Dispatcher

Single entry point for the main agent. Receives typed retrieval intents, validates against policy, routes to the appropriate miner, validates the report, attaches the attestation, and returns.

The dispatcher is **deterministic**. No LLM in its critical path.

### 2.2 Miners

Bounded, scoped, ephemeral workers. Each miner has:

- A single responsibility (the catalog enumerates them)
- A typed task list
- A bounded budget (TTL, max files, max results, max bytes)
- Read-only access to the workspace
- No persistent state between dispatches
- A clear classification: deterministic or LLM-using

Miners do not talk to each other. Miners do not dispatch other miners. Miners do not mutate state.

### 2.3 The Repo Knowledge Graph

A persistent, incrementally-updated graph storing:

- **Nodes:** files, symbols, modules, tests, commits, configs, dependencies
- **Edges:** imports, calls, defines, references, tests, modifies, depends-on, owns

Each node and edge carries:

- Source miner attestation
- Content hash of the underlying artifact
- Timestamp
- Probabilistic flag (true if any LLM-using miner contributed)

The graph is **the Fabric's memory**. Miners both read it (cheap query) and write it (incremental updates).

### 2.4 The Index Layer

Underneath the graph: traditional indexes for fast lookup.

- File path → metadata (size, mtime, content hash)
- Symbol → defining location(s)
- Symbol → calling locations
- Module → exports, imports
- Commit → files touched
- Filename → recent log entries (if log mining enabled)

Indexes are deterministic. They are the boring infrastructure layer.

### 2.5 The Attestation Hook

Every report leaving the Dispatcher carries a retrieval attestation. The Dispatcher calls the Cognitive PKI attestation service. The attestation includes:

- Miner class and task
- Effective scope (after policy clamping)
- Parameters
- Content hashes of every file read
- Report hash
- Issued-at, expires-at
- The Dispatcher's signed assertion that policy was satisfied

Consumers (main agent, artifact generators) refuse to use unattested reports.

---

## 3. Architecture diagram

```
            ┌──────────────────────────────────────┐
            │       Main Agent (Hermes)            │
            │   - issues retrieval intents         │
            │   - consumes attested reports        │
            └──────────────────┬───────────────────┘
                               │
                  retrieval intent (typed)
                               │
            ┌──────────────────▼───────────────────┐
            │         Fabric Dispatcher            │
            │         (deterministic)              │
            │                                       │
            │  - validates request schema           │
            │  - enforces scope/budget/policy       │
            │  - selects miner                      │
            │  - mediates attestation              │
            └────┬──────────────────────────┬─────┘
                 │                          │
            spawns miner          requests attestation
                 │                          │
        ┌────────▼────────┐      ┌─────────▼──────────┐
        │     Miner       │      │  Attestation Svc   │
        │   (sandboxed)   │      │   (PKI layer)      │
        └────────┬────────┘      └────────────────────┘
                 │
        reads + queries
                 │
        ┌────────▼────────────────────┐
        │  Workspace + Repo Graph     │
        │  + Indexes                  │
        └─────────────────────────────┘
```

---

## 4. Retrieval intent vocabulary

The main agent does not say "ls src/". The main agent expresses **intents**:

```
intent: locate_authentication_flow
  targets: [login_logic, jwt_handling, middleware]
  depth: medium
  freshness: 1h
```

```
intent: trace_callers
  symbol: parseConfig
  scope: workspace
  include_tests: true
  freshness: 5m
```

```
intent: find_failing_tests
  recency: 1d
  modules: [auth, payments]
```

```
intent: locate_secret_exposure
  scope: workspace
  patterns: [aws_keys, jwt, private_keys]
```

```
intent: extract_api_surface
  package: src/api
  freshness: realtime
```

The dispatcher translates each intent into one or more miner dispatches. The main agent sees one structured report, not the orchestration underneath.

**This is the cognitive DMA pattern.** The main agent expresses what it wants to know. The Fabric figures out which miners answer.

---

## 5. The "report, never raw" rule

A miner report contains structured findings, not raw content. Example, *bad*:

```json
{
  "files": [
    { "path": "auth/jwt.ts", "content": "<3000 lines of code>" },
    { "path": "auth/middleware.ts", "content": "<2400 lines>" }
  ]
}
```

Example, *good*:

```json
{
  "findings": [
    {
      "subject": "auth/jwt.ts",
      "relevance": 0.94,
      "reason_codes": ["signs_jwt", "handles_refresh", "imports_session_store"],
      "key_symbols": ["signToken", "refreshToken", "verifyToken"],
      "key_line_ranges": [[12, 48], [104, 156]],
      "related": ["middleware/auth.ts:requireAuth", "api/login.ts:handler"],
      "risk_flags": ["hardcoded_expiry_constant"],
      "content_hash": "sha256:..."
    }
  ],
  "total_candidates_examined": 47,
  "scope_searched": "src/auth/**"
}
```

The main agent reasons over the structured finding. If it needs to see the actual code in `auth/jwt.ts:12-48`, it makes a separate, narrow retrieval intent for that range.

---

## 6. Persistent vs ephemeral

| Component | Persistent? | Notes |
|-----------|-------------|-------|
| Dispatcher | Long-running service | Stateless across requests |
| Miner | Ephemeral per dispatch | Spawned, run, killed |
| Repo Knowledge Graph | Persistent | Incrementally updated |
| Indexes | Persistent | Rebuilt on schema change |
| Reports | Returned, not stored | Stored only if a consumer chooses |
| Retrieval attestations | Persistent in audit log | Verifiable forever |

---

## 7. Incremental update strategy

The repo graph is updated incrementally as miners run. Two modes:

### Pull mode (on dispatch)
A miner runs to satisfy a retrieval intent. As a side effect, it updates the graph with what it learned (newly seen files, new edges).

### Push mode (background watcher)
A filesystem watcher monitors the workspace. On change, it triggers minimal miners to re-derive affected graph entries. Stale entries are marked, then refreshed.

Both modes produce signed attestations. The graph never holds an unattested entry.

---

## 8. Querying the graph

The main agent (via dispatcher) queries the graph instead of re-running mining:

```
query:
  pattern: "callers of parseConfig, transitively, up to depth 3"
  language: typescript
  scope: src/
```

The graph returns the answer with per-edge attestations. If any edge is stale (content hash mismatch), the dispatcher re-mines that edge before returning.

This is the **graph traversal vs filesystem rediscovery** distinction. Cheap, fast, attested.

---

## 9. Miner classification

| Class | Type | Notes |
|-------|------|-------|
| File Miner | Deterministic | Path/name/metadata lookup |
| Dependency Miner | Deterministic | Imports, references, calls via AST |
| Schema Miner | Deterministic | Type signatures, API surface |
| Git Miner | Deterministic | History, blame, diffs |
| Log Miner | Deterministic + optional LLM | Pattern match; LLM for clustering |
| Test Miner | Deterministic | Test discovery, failure correlation |
| Secret Miner | Deterministic | Pattern + entropy scanning |
| Policy Miner | Deterministic | Config and rule lookup |
| Refactor Miner | Deterministic + optional LLM | Affected-code analysis; LLM for risk summary |
| Doc Miner | Deterministic + optional LLM | Heading/section extraction; LLM for semantic queries |

Default to deterministic. LLM-using miners require explicit justification, run under the injection-resistant miner prompt, and tag their reports `llm_used: true` (CT-I15).

See `MINER_CATALOG.md` for full task lists per class.

---

## 10. Composition with the rest of the architecture

| Concern | Owner |
|---------|-------|
| Reasoning, planning, synthesis | Hermes (main agent) |
| Retrieval (filesystem, repo, graph) | Fabric |
| Artifact attestation | Cognitive PKI |
| Capability authorization | Sentinel |
| Secret handling | Vault |
| Mutation (file writes, command execution) | Forge |
| Memory (long-term beliefs) | Atlas |

The Fabric is one component. It does retrieval. Nothing else.

---

## 11. Failure modes specific to the Fabric

| Mode | Class | Response |
|------|-------|----------|
| Miner timeout | DEGRADED | Return `truncated`/`timeout`; main agent replans |
| Graph staleness detected | DEGRADED | Quarantine stale entries; re-mine; serve fresh |
| Miner attestation refused | CRITICAL | Block report release; investigate attestation service |
| Repo graph corruption | CRITICAL | Halt graph writes; rebuild from sources |
| Miner sandbox escape | CATASTROPHIC | Kill miner; quarantine its inputs; full audit |
| LLM miner injection-tagged report | DEGRADED | Surface to consumer with `probabilistic_input` flag |
| Persistent budget exhaustion | DEGRADED | Throttle dispatches; surface to user |

---

## 12. What this architecture is not

- Not a search engine for end users
- Not a general agent framework
- Not autonomous miners with planning capability
- Not a replacement for IDE tooling (it complements; many miners *wrap* IDE-grade tools)
- Not a multi-agent system; it is a service with workers

---

## 13. Open implementation questions

- **Graph backend.** Sqlite + JSON for small repos; Neo4j or similar for large. Initial impl: sqlite.
- **Watcher mode.** Initial impl: pull-only. Push mode added when warranted by scale.
- **Cross-repo graphs.** Initial scope: single workspace. Multi-repo deferred.
- **Embedding-based retrieval.** Optional layer; not required for the deterministic base.

These are explicitly open. Don't pretend they're solved.

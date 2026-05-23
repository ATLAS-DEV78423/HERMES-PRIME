# Repo Knowledge Graph + Indexing

**Purpose:** Define the persistent layer that lets miner queries return in milliseconds and lets the main agent reason over repo structure without re-deriving everything per session.

This is the difference between *graph traversal* and *filesystem rediscovery*.

---

## 1. The graph

A property graph (nodes + edges, both with attributes). Backed initially by SQLite + JSON; production deployments can use Neo4j, DuckDB, or similar.

### Node types

| Node | Carries |
|------|---------|
| `File` | path, size, mtime, content_hash, language, source_attestation |
| `Symbol` | name, kind (function/class/var), defining_file, defining_line, signature, source_attestation |
| `Module` | path, language, exports[], imports[], source_attestation |
| `Test` | name, defining_file, defining_line, status (pass/fail/unknown), last_run_at, source_attestation |
| `Commit` | sha, author, timestamp, message, source_attestation |
| `Config` | path, format, schema (if known), source_attestation |
| `Dependency` | name, version, kind (runtime/dev), source_attestation |
| `Route` | method, path_pattern, handler_symbol, framework, source_attestation |

### Edge types

| Edge | From → To | Notes |
|------|-----------|-------|
| `imports` | File → Module | "this file imports this module" |
| `exports` | Module → Symbol | "this module exports this symbol" |
| `defines` | File → Symbol | "this file defines this symbol" |
| `references` | File → Symbol | "this file references (but does not define) this symbol" |
| `calls` | Symbol → Symbol | "this function calls this function" |
| `tests` | Test → Symbol \| File | "this test exercises this code" |
| `modifies` | Commit → File | "this commit touched this file" |
| `depends_on` | Module → Dependency | "this module needs this external dep" |
| `routes_to` | Route → Symbol | "this URL routes to this handler" |
| `owns` | Module → File | declared ownership (codeowners file, etc.) |

Every node and edge carries `source_attestation`, the attestation of the miner that asserted it. Per CT-I14.

---

## 2. Why a graph (and not just indexes)

Indexes answer point queries: "where is `parseConfig` defined?"

Graphs answer relational queries: "what are all the call paths from public API handlers to `parseConfig`, and which of them are exercised by tests?"

The Fabric needs both. Indexes back the graph for fast lookup; the graph composes them.

---

## 3. Index layer

Underneath the graph, traditional indexes:

| Index | Key | Value |
|-------|-----|-------|
| `path_index` | path | (size, mtime, content_hash, language) |
| `symbol_def_index` | (symbol_name, language) | list of (file, line) where defined |
| `symbol_ref_index` | (symbol_name, language) | list of (file, line) where referenced |
| `import_index` | module_name | list of files that import this module |
| `route_index` | (method, path_pattern) | handler symbol |
| `commit_path_index` | (path, commit_sha) | commit metadata |
| `test_subject_index` | symbol_or_file | list of tests covering it |

Index updates are atomic with attestation issuance: if the attestation is recorded, the index entries derived from it are visible. If the attestation is revoked, derived entries are invalidated.

---

## 4. Provenance per node/edge

The Fabric does not store an unattested fact. Period.

If a user manually edits the graph (a maintenance operation), the operator's attestation is recorded. If a miner asserts a fact, the miner's attestation is recorded. Either way, every entry has a "why do we believe this?" answer.

This is CT-I14 made operational. It is also the direct application of the Hermes Atlas pattern (provenance is mandatory, doctrine §4.2) to the repo graph.

---

## 5. Freshness and staleness

Files change. Without freshness tracking, the graph rots into a confidently-wrong artifact.

### Freshness signals

- **mtime** (cheap, fallible across filesystems)
- **content_hash** (definitive, slightly expensive)
- **attestation expiry** (each attestation declares a TTL)

### Staleness handling

A graph entry is **fresh** if its source's content_hash matches the hash in its source_attestation.

A graph entry is **stale** if the source's content_hash has changed.

A graph entry is **expired** if its attestation has passed `expires_at`.

On query:

- Fresh entries return as-is.
- Stale entries are quarantined; the dispatcher re-mines them before returning; new attestation issued; entries updated.
- Expired entries are re-validated (cheap: re-hash and re-attest if unchanged) or re-mined (if changed).

The main agent always sees fresh entries. Staleness is the Fabric's problem.

---

## 6. Incremental update modes

### Pull mode (default)

A miner runs to satisfy a retrieval intent. As a side effect, it writes/updates graph entries for what it learned.

Pros: no background load, only do work when needed.
Cons: first-touch latency on cold queries.

### Push mode (optional)

A filesystem watcher monitors the workspace. On change, it triggers a minimal miner to re-derive affected graph entries proactively.

Pros: queries are always fast.
Cons: background CPU + I/O cost; more complex; watcher correctness matters.

Default: pull mode. Switch to push mode for workspaces with high query rates and predictable hot files.

---

## 7. Query examples

### Q: "Find all callers of parseConfig"

```sql
SELECT caller.file, caller.line, caller.in_function
FROM symbol_ref_index r
JOIN nodes caller ON caller.id = r.referrer_node_id
WHERE r.symbol = 'parseConfig'
  AND r.kind = 'call'
  AND r.source_attestation.revoked = false
```

Returns in milliseconds. Each result carries its source attestation.

### Q: "Transitive dependents of parseConfig, depth 3"

A graph traversal:

```
seed = node where Symbol.name = 'parseConfig'
result = bfs(graph, seed, edge_type='references' OR 'calls',
            direction='inbound', max_depth=3)
filter: result entries with fresh, non-revoked attestations
```

### Q: "Files modified in the last 24h that contain tests for module X"

Joins git_miner data with test_miner data, both already in the graph.

The point: **the agent does not re-derive these. It queries the graph.**

---

## 8. Graph schema evolution

Schemas change. Adding a new node type or edge type is a versioned operation.

- Schema versions are signed by the operator
- New schema versions can read old data (forward compatibility)
- Migrations re-derive affected entries from sources, producing new attestations
- The schema version is part of every attestation context

This prevents "the graph means subtly different things now because schema drifted."

---

## 9. Graph corruption and recovery

If graph corruption is detected (chain validation failure, attestation index inconsistency, schema violation):

1. Halt graph writes immediately
2. Read-only mode on graph queries (returning `degraded: true` in responses)
3. Operator reviews
4. Recovery options:
   - Restore from snapshot + replay attested updates
   - Wipe and re-mine from sources (slow but always correct)
5. Resume only after explicit operator attestation that integrity is restored

Per CT-I11.

---

## 10. Sizing

Initial sizing for the SQLite backend:

| Repo size | Nodes | Edges | DB size | Query p99 |
|-----------|-------|-------|---------|-----------|
| Small (<10K files) | ~50K | ~200K | <100 MB | <50ms |
| Medium (<100K files) | ~500K | ~2M | <2 GB | <200ms |
| Large (>100K files) | varies | varies | switch to graph DB | varies |

These are reference figures. Actual numbers depend on language and tooling.

---

## 11. What the graph is NOT

- **Not a search engine.** It's a structural map. Use embedding_miner for semantic search.
- **Not truth.** It's evidence. Consumers must respect freshness and revocation.
- **Not eventually consistent at request boundaries.** Within a dispatch, what you read is consistent. Across dispatches, freshness may have shifted; check attestation timestamps.
- **Not user-facing.** End-user search/navigation tools should sit on top of the graph if useful, but the graph itself exists to serve the agent.

---

## 12. Cross-repo

Initial implementation: single workspace per graph. Multi-repo (one graph spanning many repos) is deferred.

When added, multi-repo introduces:

- Cross-repo edges (rare but exist)
- Per-repo attestation issuers
- Access control (which agent/operator can query which repo's nodes)
- Significantly higher index sizes

This is intentionally out of scope for v1. Build the single-repo case well first.

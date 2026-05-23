# Miner Catalog

**Purpose:** Enumerate every miner class, its single responsibility, its task list, its determinism class, and its operational notes.

A miner class is justified only if it:
1. Has a single, well-defined responsibility
2. Cannot be composed from existing miners
3. Has a fixed output schema
4. Defaults to deterministic implementation

Classes that fail any of these are rejected. See "Rejected classes" at the end.

---

## 1. File Miner — `file_miner`

**Responsibility:** Locate files by path, glob, extension, recency, or size.

**Determinism:** 100% deterministic.

**Tasks:**
- `find_by_glob(pattern, scope)`
- `find_by_extension(ext, scope)`
- `find_recent(since, scope)`
- `find_large(min_bytes, scope)`
- `enumerate_tree(root, max_depth)`
- `stat(paths[])` — metadata for known paths

**Notes:** The cheapest, most-used miner. Reports rarely exceed 1 KB.

---

## 2. Dependency Miner — `dependency_miner`

**Responsibility:** Trace imports, references, and call relationships between code units.

**Determinism:** 100% deterministic (uses tree-sitter / ast-grep / language ASTs).

**Tasks:**
- `find_definition(symbol, language, scope)`
- `find_references(symbol, language, scope)`
- `find_callers_of(function, language, scope)`
- `find_imports_of(module, scope)`
- `transitive_dependents(symbol, max_depth)`
- `module_graph(root)` — full import graph for a module
- `unused_exports(scope)` — exports with zero references

**Notes:** Updates the repo graph with edges as it runs.

---

## 3. Schema Miner — `schema_miner`

**Responsibility:** Extract type signatures, API surface, schema definitions.

**Determinism:** 100% deterministic.

**Tasks:**
- `extract_signatures(path)`
- `api_surface(package)` — all public exports + signatures
- `find_route_definitions(framework, scope)` — REST/GraphQL/RPC routes
- `extract_types(path)` — TS interfaces, Python dataclasses, etc.
- `extract_db_schema(scope)` — migrations, ORM models
- `diff_api_surface(from_commit, to_commit, package)`

---

## 4. Git Miner — `git_miner`

**Responsibility:** Inspect repository history, blame, diffs, branches.

**Determinism:** 100% deterministic.

**Tasks:**
- `log_for_path(path, since?)`
- `blame_for_lines(path, start_line, end_line)`
- `diff_between(from, to, scope?)`
- `who_changed(path, since?)`
- `last_modified(path)`
- `branches_containing(commit)`
- `recent_commits(since, author?)`
- `merge_base(branch_a, branch_b)`

---

## 5. Log Miner — `log_miner`

**Responsibility:** Extract relevant entries from log files; cluster failure patterns.

**Determinism:** Hybrid. Pattern search is deterministic. Clustering similar errors uses LLM (optional).

**Tasks:**
- `find_entries(pattern, scope, time_range)`
- `find_errors(scope, time_range)` — heuristic error pattern set
- `cluster_failures(scope, time_range)` — LLM-based (flagged probabilistic)
- `correlate_with_deploy(time_range)` — joins logs with git deploy events
- `last_seen(pattern, scope)`

**Notes:** Highest injection risk among non-LLM miners — log content is adversary-controllable in many systems. Patterns are scanned for embedded prompt-like sequences before being attested.

---

## 6. Test Miner — `test_miner`

**Responsibility:** Locate tests, correlate failures with code, surface coverage gaps.

**Determinism:** 100% deterministic.

**Tasks:**
- `find_tests_for(path)` — tests covering this source file
- `find_failing(scope, since?)`
- `coverage_for(path)` — coverage data if available
- `flaky_tests(scope, window)` — historical flakiness from CI data
- `tests_modified_recently(scope, since)`

---

## 7. Secret Miner — `secret_miner`

**Responsibility:** Detect leaked credentials, keys, tokens in the workspace.

**Determinism:** 100% deterministic.

**Tasks:**
- `scan_for_secrets(scope, patterns?)` — entropy + regex
- `find_in_history(patterns?, since?)` — git history scan
- `verify_no_secrets_in_diff(from, to)` — pre-commit check
- `list_known_secret_patterns()` — what we detect

**Notes:** This is a defensive miner. Findings are routed through Sentinel with high priority. The miner does not include the secret values in its report — only locations and pattern names.

---

## 8. Policy Miner — `policy_miner`

**Responsibility:** Locate configuration files, policy rules, IaC definitions, capability declarations.

**Determinism:** 100% deterministic.

**Tasks:**
- `find_configs(format?, scope)` — yaml/json/toml/etc.
- `find_iac(provider?)` — terraform/cloudformation/pulumi
- `find_rbac_rules(scope)`
- `find_capability_declarations(scope)` — for Hermes-style capability registries
- `find_env_var_uses(scope)`

---

## 9. Refactor Miner — `refactor_miner`

**Responsibility:** Map the blast radius of a proposed refactor.

**Determinism:** Hybrid. Affected-code analysis is deterministic. Risk summary is LLM (optional).

**Tasks:**
- `affected_by_symbol_rename(symbol, new_name, scope)`
- `affected_by_signature_change(symbol, new_signature, scope)`
- `affected_by_file_move(from_path, to_path, scope)`
- `risk_summary(refactor_plan)` — LLM-based (flagged probabilistic)

---

## 10. Doc Miner — `doc_miner`

**Responsibility:** Extract structured info from documentation files.

**Determinism:** Hybrid. Structural extraction deterministic; semantic queries use LLM.

**Tasks:**
- `extract_section(path, heading_pattern)`
- `list_headings(path)`
- `find_section_about(scope, topic)` — LLM (flagged)
- `extract_code_blocks(path, language?)`
- `find_changelog_entries(scope, since?)`

---

## 11. Health Miner — `health_miner`

**Responsibility:** Query operational state of services and endpoints.

**Determinism:** 100% deterministic.

**Tasks:**
- `check_endpoint(url, expected_status?)`
- `check_port(host, port)`
- `latest_metrics(service, metric_names[])` — from monitoring backend
- `recent_alerts(service, window)`

**Notes:** Network-using miner. Requires explicit network grant in sandbox config.

---

## 12. Cross-Repo Miner — `cross_repo_miner`

**Responsibility:** Same operations as other miners, but spanning multiple registered repositories.

**Determinism:** Same as wrapped miner.

**Tasks:** Same task list as the underlying miner, with `repos[]` parameter instead of `scope`.

**Notes:** Disabled by default. Enabling requires per-repo grant. Cross-repo retrieval is a significantly larger attack surface.

---

## 13. Embedding Miner — `embedding_miner`

**Responsibility:** Semantic similarity search over indexed content.

**Determinism:** Hybrid. Embedding generation is deterministic (per model); similarity lookup is deterministic. Interpretation of similarity scores is the consumer's responsibility.

**Tasks:**
- `find_similar_to(text, scope, top_k)`
- `find_similar_to_file(path, scope, top_k)`
- `cluster(scope, n_clusters)`

**Notes:** Optional layer. Use when keyword/AST search is insufficient. Embeddings are computed once and cached; only the lookup is per-dispatch.

---

## Summary table

| Miner | Determinism | Network | Risk |
|-------|-------------|---------|------|
| file_miner | Deterministic | No | Low |
| dependency_miner | Deterministic | No | Low |
| schema_miner | Deterministic | No | Low |
| git_miner | Deterministic | No | Low |
| log_miner | Hybrid | No | Medium (injection in logs) |
| test_miner | Deterministic | No | Low |
| secret_miner | Deterministic | No | Low |
| policy_miner | Deterministic | No | Low |
| refactor_miner | Hybrid | No | Low |
| doc_miner | Hybrid | No | Medium (injection in docs) |
| health_miner | Deterministic | **Yes** | Medium (network surface) |
| cross_repo_miner | Inherits | No | Higher (broader scope) |
| embedding_miner | Hybrid | No | Low |

---

## Rejected classes

Documented to prevent re-proposal.

### `general_miner` (rejected)
A miner that "does anything." Rejected: violates single-responsibility. The whole point of the catalog is narrow scope.

### `editor_miner` (rejected)
A miner that edits files. Rejected: violates CP8 (workers retrieve and report). Mutation belongs to Forge, mediated by Sentinel.

### `planner_miner` (rejected)
A miner that does planning. Rejected: planning is the main agent's responsibility.

### `web_browser_miner` (rejected for now)
Fetch and process external web pages. Massive injection surface (Hermes T1). Deferred until injection-resistant fetching pipeline is built.

### `secret_fetcher_miner` (permanently rejected)
A miner that retrieves credentials. Rejected: violates P4 / CP4. Secrets are handled by Vault, never by miners.

### `recursive_miner` (rejected)
A miner that can dispatch other miners. Rejected: violates Hermes principle that subagents do not chain. Only the main agent orchestrates.

### `cache_invalidation_miner` (rejected)
A miner that decides what to evict from caches. Rejected: cache policy is dispatcher-level, not miner-level.

---

## Class budget defaults

Per `INVARIANTS.md` CT-I12, these are caps. Requests cannot exceed.

| Miner | max_files | max_results | max_bytes_per_result | ttl_s |
|-------|-----------|-------------|----------------------|-------|
| file_miner | 5000 | 200 | 2 KB | 10 |
| dependency_miner | 5000 | 300 | 2 KB | 30 |
| schema_miner | 500 | 500 | 4 KB | 20 |
| git_miner | N/A | 200 | 4 KB | 15 |
| log_miner | 100 | 200 | 4 KB | 30 |
| test_miner | 500 | 300 | 2 KB | 30 |
| secret_miner | 50000 | 100 | 1 KB | 60 |
| policy_miner | 1000 | 100 | 4 KB | 15 |
| refactor_miner | 5000 | 200 | 4 KB | 60 |
| doc_miner | 100 | 100 | 4 KB | 30 |
| health_miner | N/A | 50 | 1 KB | 10 |
| embedding_miner | N/A | 50 | 1 KB | 5 |

Operators may set tighter caps; never looser.

# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- **Interactive REPL** (`hermes repl`) — working governed REPL with LLM-based conversation, tool calling, session persistence, and `/clear`/`/quit` commands
- **Session management** (`hermes sessions list|search|view|rename|delete|export|stats|prune`) — enhanced SQLite-backed session store with FTS5 search, JSONL export, and source filtering
- **Skills hub** (`hermes skills search|browse|inspect|install|check|uninstall`) — wrap upstream skills hub with Sentinel audit tracing
- **Cron scheduler** (`hermes cron list|create|pause|resume|run|remove|status`) — governed cron job management wrapping upstream cron system
- **Profile management** (`hermes profile list|create|switch|rename|delete|active`) — multi-instance profile support with isolated HERMES_HOME
- **Gateway scaffold** (`hermes gateway --platforms`) — multi-platform messaging gateway wrapper
- **`--prompt` injection fix** — now checks upstream command registry before hijacking tokens as AI prompts (unblocks `hermes setup`, `hermes version`, `hermes config`, etc.)
- Documentation: comprehensive subsystem documentation in README and docs/usage.md

### Fixed
- Type annotation fix in `miners/ast_miner/miner.py` — `names` list now properly typed as `list[str | None]`
- Removed circular self-import in `hermes_prime/infrastructure_setup.py` — `create_vault()` now calls `create_trust_store()` directly from module scope
- `ToolRegistry.tool_schemas()` now safely filters out `None` schemas instead of propagating them
- Memory consolidator `source_fact_ids` sort logic — pre-binds to local variable to avoid repeated attribute access
- Robustness: all 504 tests passing, ruff clean, mypy clean across 105 source files

## [0.2.0] - 2026-05-23
- Initial public beta release with governance-first architecture and Sentinel core.

## [0.2.1] - 2026-05-23
- Phase 2: Memory integration — recall included in prompt, memory attestations attached to audit traces.
- CI and docs improvements.

# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- Documentation: superpowers integration plans and design specs (interactive agent, unified CLI, full agent integration)
- Obsidian graphify custom integration module

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

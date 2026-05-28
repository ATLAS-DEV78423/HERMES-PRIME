# Hermes Prime Documentation

Hermes Prime is a local-first governance engine for autonomous AI operations. This site contains operator and developer documentation.

## Manuals

| Guide | Description |
|-------|-------------|
| [Setup Manual](setup.md) | Install, verify, and troubleshoot your environment |
| [Usage Manual](usage.md) | CLI reference including **`hermes doctor`** and **`hermes repair`** |
| [Memory Governance](memory_governance.md) | Memory fabric design and trust tiers |
| [Guardrails](guardrails.md) | Security and operational guidelines |

## Quick reference

```bash
# Install
pip install -e ".[dev]"

# Health check and self-repair
hermes doctor
hermes repair

# Governance
hermes inspect --json
hermes mint --scope . --issued-to me --capability cap:file-read:scoped --actions filesystem.read
```

## Architecture (repository)

Deep design docs live under [`hermes/`](../hermes/):

- [Foundational Primitives](../FOUNDATIONAL_PRIMITIVES.md)
- [CLI Identity](../hermes/CLI_IDENTITY.md)
- [Schema Registry](../hermes/SCHEMA_REGISTRY.md)
- [Threat Model](../hermes/THREAT_MODEL.md)

### Visual architecture

- [Architecture Diagram](architecture.md) — Mermaid system architecture and data flow
- [`graphify-out/graph.json`](../graphify-out/graph.json) — Auto-generated knowledge graph (4330 nodes, 1933 edges)
- [`scripts/generate_graphify_graph.py`](../scripts/generate_graphify_graph.py) — Knowledge graph generator

## Project links

- [GitHub Repository](https://github.com/ATLAS-DEV78423/HERMES-PRIME)
- [README / Overview](../README.md)

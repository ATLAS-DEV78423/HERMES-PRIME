# Monorepo Layout

This is the intended Hermes Prime monorepo shape.

The layout is designed to keep doctrine, trust, retrieval, and orchestration separated while still living under one coherent workspace.

```text
hermes-prime/
├── core/
│   ├── hermes-agent/
│   ├── ATLAS-AI/
│   └── SENTINAL/
├── infrastructure/
│   ├── vault/
│   ├── provenance/
│   ├── retrieval-fabric/
│   └── policy-engine/
├── external/
│   ├── fabric/
│   ├── opa/
│   ├── sigstore/
│   ├── tree-sitter/
│   ├── llama_index/
│   └── neo4j/
├── doctrine/
│   ├── DOCTRINE.md
│   ├── THREAT_MODEL.md
│   ├── GATES.md
│   └── DECISIONS/
├── miners/
│   ├── file-miner/
│   ├── dependency-miner/
│   ├── git-miner/
│   └── schema-miner/
├── forge/
├── atlas/
├── sentinel/
├── vault/
└── provenance/
```

## Directory intent

- `core/` is for the three primary system repositories.
- `infrastructure/` is for the shared trust and execution spine.
- `external/` is for upstream references that influence implementation but do not define the system.
- `doctrine/` is the governance layer.
- `miners/` is where retrieval-specific workers and adapters belong.
- `forge/`, `atlas/`, `sentinel/`, `vault/`, and `provenance/` are the local product boundaries that eventually replace the skeletal docs with real code.

## Naming note

Keep the architecture term `Sentinel` in documentation even if a repository preserves the upstream spelling `SENTINAL`.

That keeps the governance concept clean while still tracking the existing upstream name.

## Clone policy

You do not need every repository cloned to define the architecture or scaffold the workspace.

Clone what is needed for:

- implementation
- adapter work
- direct reference reading
- validation against upstream behavior

Do not clone merely to make the stack feel more complete.


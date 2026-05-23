# MemPalace Integration — Design Spec (Phases 0–2)

## Mission

Integrate MemPalace into HERMES-PRIME as:

> A governed cognitive state substrate with deterministic retrieval, memory arbitration, temporal reasoning, and reflective consolidation.

NOT chatbot memory, infinite conversation storage, vector dump persistence, or passive retrieval-only memory.

## Core Principle

Memory is NOT storage. Memory is validated operational state continuity.

MemPalace holds the **raw verbatim payload**. The governed wrapper (`MemoryRecord`) IS the memory.

---

## Scope

This spec covers **Phases 0, 1, and 2** of the roadmap:

- **Phase 0:** Memory Governance Spec document
- **Phase 1:** MemPalace backend adapter + sandbox benchmarks
- **Phase 2:** Memory Object Model (`MemoryRecord`)

Subsequent phases (Temporal Knowledge Graph, Context Compiler, Governor, Reflection, Decay, Federation, Orchestration, Observability) are separate specs.

---

## Architecture

```
┌─────────────────────────────────────────┐
│             MemoryStore                 │  ← existing, unchanged
│  write / recall / get / revoke / gc     │
└──────────────┬──────────────────────────┘
               │ uses
┌──────────────▼──────────────────────────┐
│          MemoryBackend (ABC)            │  ← existing interface
│  store / get / search / gc / count      │
└──────┬──────────────┬───────────────────┘
       │              │
┌──────▼──────┐  ┌────▼────────────────┐
│ SQLite      │  │ MemPalaceBackend    │  ← NEW
│MemoryBackend│  │ (sync adapter)      │
└─────────────┘  └────┬─────────────────┘
                      │ delegates to
               ┌──────▼──────────────────┐
               │    mempalace library    │
               │  (verbatim store)       │
               └─────────────────────────┘
┌─────────────────────────────────────────┐
│          MemoryRecord (NEW)             │
│  governed wrapper around payload        │
└─────────────────────────────────────────┘
```

**Rules:**
- Agents NEVER query MemPalace directly
- All access goes through `MemoryStore` → backend
- `MemPalaceBackend` is the ONLY file that imports `mempalace`

---

## Phase 0: Memory Governance Spec

**Deliverable:** `docs/memory_governance.md`

### Memory Types

| Type | Purpose | Retention | Example |
|------|---------|-----------|---------|
| `working` | In-progress scratch | 24h or task end | "Currently processing file X" |
| `episodic` | Observed events, actions | 90d | "Agent Y deployed to staging" |
| `reflective` | Post-task consolidation | 30d | "Task Z failed due to timeout" |
| `semantic` | Extracted facts, patterns | permanent | "API endpoint is at /v2/users" |
| `strategic` | Compressed learnings | permanent | "Avoid Tool X > 5 concurrent calls" |
| `governance` | Policies, ACLs, rules | immutable | "Tier T3 actions require attestation" |

### Trust Levels

Mapped to existing `TrustState` enum:

| Governance Level | TrustState | Meaning |
|-----------------|------------|---------|
| `unverified` | `UNVERIFIED` | Raw observation, no corroboration |
| `inferred` | `OBSERVED` | Seen multiple times, not yet validated |
| `validated` | `VALIDATED` | Corroborated, contradictions resolved |
| `immutable` | `EXECUTABLE` | Governance records, system-owned, never decays |

### Retention Tiers

```yaml
volatile:   24h    # working
temporary:  30d    # reflective
standard:   90d    # episodic
durable:    365d   # semantic
permanent:  never  # strategic, governance
```

### Ownership Rules

- Every memory has a `source_agent` — no anonymous memory
- Governance memories are system-owned, mutable only by the Governor
- Agent scratchpads (`working` type) are agent-private by default
- Promotion to `validated` requires corroboration (confidence >= 0.8 or multiple sources)
- Cross-agent visibility is explicitly granted, not default

### Decay Policy Basis

Decay factors (formalized in Phase 7):
- Age relative to retention tier
- Access frequency (rarely accessed decays faster)
- Contradiction count (high contradiction → faster decay)
- Trust score (immutable governance never decays)
- Strategic value (strategic type exempt)

### Prohibition

No raw chain-of-thought storage. Store:
- Decisions made
- Constraints discovered
- Outcomes observed
- Validated reasoning summaries

NOT infinite CoT dumps.

---

## Phase 1: MemPalace Backend Adapter

### File

`hermes_prime/memory/backends/mempalace_backend.py`

### Implementation

Implements the existing `MemoryBackend` ABC (sync) using MemPalace's Python API:

```python
class MemPalaceBackend(MemoryBackend):
    def __init__(self, palace_path: str = "~/.hermes-prime/palace"):
        ...

    def store(self, claim: MemoryClaim) -> None:
        # mempalace.mine(content, wing=memory_type, room=source_agent)

    def search(self, query: str, limit: int = 10) -> list[MemorySearchResult]:
        # mempalace.search(query, limit=limit) → wrap in MemorySearchResult

    def get(self, fact_id: str) -> MemoryClaim | None:
        # retrieve via mempalace metadata by id

    def list_all(self) -> list[MemoryClaim]:
    def delete(self, fact_id: str) -> bool:
    def count(self) -> int:
    def gc(self, before_timestamp: str) -> int:
```

### Wing/Room/Drawer Mapping

| HERMES Concept | MemPalace Concept |
|----------------|-------------------|
| Memory type | Wing |
| Source agent | Room |
| Individual record | Drawer |

This leverages MemPalace's native scoping for deterministic retrieval.

### Dependency

- `pyproject.toml`: add `mempalace>=3.3` as optional dependency under `[project.optional-dependencies] memory = ["mempalace>=3.3"]`
- No other file in HERMES-PRIME imports `mempalace` directly

### Sandbox Benchmarks

Tests under `tests/memory/test_mempalace_backend.py` verifying:
- Write throughput (records/sec)
- Retrieval latency (p50/p95)
- Embedding drift over repeated writes
- Persistence across process restarts
- Context reconstruction quality (round-trip fidelity)
- GC correctness

Benchmarks are comparative against SQLite backend where applicable.

---

## Phase 2: Memory Object Model

### File

`hermes_prime/memory/records.py` (new)

### Enums

```python
class MemoryType(str, Enum):
    WORKING = "working"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    STRATEGIC = "strategic"
    REFLECTIVE = "reflective"
    GOVERNANCE = "governance"


class ValidationStatus(str, Enum):
    UNVERIFIED = "unverified"
    CORROBORATED = "corroborated"
    CONTRADICTED = "contradicted"
```

### MemoryRecord

```python
@dataclass
class MemoryRecord:
    # Identity
    id: str                              # urn:uuid (same as MemoryClaim.fact_id)
    memory_type: MemoryType

    # Content (the payload — MemPalace stores this verbatim)
    content: str

    # Provenance
    source_agent: str
    intent_root: str
    created_at: datetime
    updated_at: datetime
    checksum: str                        # sha256 of content

    # Trust
    confidence: float                    # 0.0–1.0, mirrors epistemic_confidence
    trust_level: TrustState

    # Relationships
    lineage: list[str]                   # parent record ids (directed acyclic)
    causal_parent: Optional[str]         # immediate causal predecessor
    tags: list[str]

    # Validation
    validation_status: ValidationStatus

    # Storage link
    embedding_id: Optional[str]          # mempalace's internal ID if applicable
```

### Integration with Existing Code

`MemoryRecord` is a **superset** of `MemoryClaim`. The `MemoryStore.write()` method returns a `MemoryRecord` while still storing the underlying `MemoryClaim` via the backend. No existing API breaks.

| Existing (`MemoryClaim` / `MemoryStore`) | New (`MemoryRecord`) |
|---|---|
| `MemoryClaim.claim` | `MemoryRecord.content` |
| `MemoryClaim.source` | derived as `{"agent": source_agent}` |
| `MemoryClaim.epistemic_confidence` | `MemoryRecord.confidence` |
| `MemoryClaim.trust_state` | `MemoryRecord.trust_level` |
| `MemoryClaim.intent_root` | `MemoryRecord.intent_root` |
| `MemoryClaim.contradictions` | derived from `validation_status` + lineage |
| *(missing)* | `memory_type`, `lineage`, `causal_parent`, `tags` |

### Conversion Utils

```python
def record_from_claim(claim: MemoryClaim, memory_type: MemoryType = MemoryType.EPISODIC) -> MemoryRecord:
    ...

def claim_from_record(record: MemoryRecord) -> MemoryClaim:
    ...
```

---

## Directory Structure

After Phases 0–2:

```
hermes_prime/
├── memory/
│   ├── __init__.py
│   ├── backends.py              # MemoryBackend ABC, MemorySearchResult (existing)
│   ├── store.py                 # MemoryStore (existing, enhanced)
│   ├── depth.py                 # DepthPolicy (existing, updated)
│   ├── provenance.py            # ProvenanceLinker (existing)
│   ├── records.py               # MemoryRecord, MemoryType, ValidationStatus (NEW)
│   └── backends/
│       ├── __init__.py
│       ├── sqlite_backend.py    # existing
│       ├── mem0_backend.py      # existing
│       ├── zep_backend.py       # existing
│       ├── atlas_backend.py     # existing
│       └── mempalace_backend.py # MemPalaceBackend (NEW)
docs/
├── memory_governance.md         # (NEW)
└── superpowers/specs/
    └── 2026-05-23-mempalace-integration-design.md  # this document
```

---

## Error Handling

- `MemPalaceBackend` wraps mempalace exceptions in `MemoryStoreError`
- Missing records return `None` from `get()`, not exceptions
- GC failures are logged but non-fatal
- Write failures propagate to the caller; `MemoryStore.write()` returns `success=False` with error message

## Testing Strategy

| Layer | Tests | Location |
|-------|-------|----------|
| `MemoryRecord` construction | Unit: valid/invalid types, conversion round-trip | `tests/memory/test_records.py` |
| `MemPalaceBackend` CRUD | Integration: store/get/search/delete/gc against real mempalace | `tests/memory/test_mempalace_backend.py` |
| `MemoryStore` with MemPalace | Integration: full write → recall → promote flow | `tests/memory/test_store_mempalace.py` |
| Governance doc | Review only (not code-testable) | `docs/memory_governance.md` |

---

## Future Phases (Not in this spec)

- Phase 3: Temporal Knowledge Graph (Neo4j/Memgraph)
- Phase 4: Context Compiler (retrieval pipeline)
- Phase 5: Memory Governor (contradiction detection, arbitration)
- Phase 6: Reflective Consolidation Engine (post-task pattern extraction)
- Phase 7: Memory Decay System (scheduled lifecycle management)
- Phase 8: Cross-Agent Memory Federation (visibility layers)
- Phase 9: Memory-Aware Orchestration (adaptive agent selection)
- Phase 10: Memory Observability (dashboard, replay system)

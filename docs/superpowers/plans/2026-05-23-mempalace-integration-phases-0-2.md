# MemPalace Integration — Implementation Plan (Phases 0–2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate MemPalace as a governed backend for HERMES-PRIME, adding MemoryRecord object model, governance doc, and MemPalaceBackend adapter.

**Architecture:** MemPalace stores verbatim payloads in ChromaDB (wings=memory_types, rooms=agents). The existing `MemoryBackend` ABC and `MemoryStore` remain unchanged. `MemoryRecord` wraps `MemoryClaim` with memory_type/lineage/causal_parent for governed semantics. All agent access goes through `MemoryStore` → backend.

**Tech Stack:** Python 3.10+, mempalace>=3.3, existing hermes_prime.memory framework

---

## File Structure

### Created
- `docs/memory_governance.md` — Phase 0: governance spec documentation
- `hermes_prime/memory/records.py` — Phase 2: MemoryRecord, MemoryType, ValidationStatus, conversion utils
- `hermes_prime/memory/backends/mempalace_backend.py` — Phase 1: MemPalaceBackend(MemoryBackend)
- `tests/memory/test_records.py` — unit tests for MemoryRecord
- `tests/memory/test_mempalace_backend.py` — integration tests for MemPalaceBackend

### Modified
- `pyproject.toml` — add `mempalace>=3.3` optional dependency
- `hermes_prime/memory/__init__.py` — export MemoryRecord, MemoryType, ValidationStatus, MemPalaceBackend
- `hermes_prime/memory/store.py` — add `record` field to `MemoryStoreResult`, return `MemoryRecord` from `write()`
- `hermes_prime/memory/backends/__init__.py` — (empty, no change needed)

---

### Task 1: Write Memory Governance Doc

**Files:**
- Create: `docs/memory_governance.md`

- [ ] **Step 1: Create governance document**

```markdown
# Memory Governance Spec

## Memory Types

| Type | Purpose | Retention | Example |
|------|---------|-----------|---------|
| `working` | In-progress scratchpad | 24h or task end | "Currently processing file X" |
| `episodic` | Observed events, agent actions | 90d | "Agent Y deployed to staging" |
| `reflective` | Post-task consolidation output | 30d | "Task Z failed due to timeout" |
| `semantic` | Extracted facts, constraints | permanent | "API endpoint is at /v2/users" |
| `strategic` | Compressed learnings, operational constraints | permanent | "Avoid Tool X > 5 concurrent calls" |
| `governance` | Policies, trust rules, ACLs | immutable | "Tier T3 actions require attestation" |

## Trust Levels (maps to TrustState)

| Level | TrustState | Meaning |
|-------|------------|---------|
| `unverified` | `UNVERIFIED` | Raw observation, no corroboration |
| `inferred` | `OBSERVED` | Seen multiple times, not yet validated |
| `validated` | `VALIDATED` | Corroborated, contradictions resolved |
| `immutable` | `EXECUTABLE` | Governance records, system-owned |

## Retention Tiers

| Tier | Duration | Types |
|------|----------|-------|
| volatile | 24h | working |
| temporary | 30d | reflective |
| standard | 90d | episodic |
| durable | 365d | semantic |
| permanent | never | strategic, governance |

## Ownership Rules

1. Every memory has a `source_agent` — no anonymous memory
2. Governance memories are system-owned, mutable only by the Governor
3. Agent scratchpads (`working`) are agent-private by default
4. Promotion to `validated` requires confidence >= 0.8 or multiple corroborating sources
5. Cross-agent visibility must be explicitly granted, not default

## Decay Policy (basis for Phase 7)

Factors: age, access frequency, contradiction count, trust score, strategic value.
- Immutable governance: never decays
- Validated strategic: never decays
- Audit lineage: never decays
- All other types: decay based on composite score

## Prohibitions

- No raw chain-of-thought storage
- Only store: decisions, constraints, outcomes, validated reasoning summaries
- No anonymous memory (every record has a source_agent)
```

- [ ] **Step 2: Commit**

```bash
git add docs/memory_governance.md
git commit -m "docs: add memory governance spec (Phase 0)"
```

---

### Task 2: Add MemoryRecord Object Model

**Files:**
- Create: `hermes_prime/memory/records.py`
- Create: `tests/memory/test_records.py`
- Modify: `hermes_prime/memory/__init__.py`

- [ ] **Step 1: Write the failing tests**

File `tests/memory/test_records.py`:

```python
from datetime import datetime, timezone
from hermes_prime.contracts import TrustState
from hermes_prime.memory.records import MemoryRecord, MemoryType, ValidationStatus, record_from_claim, claim_from_record
from hermes_prime.memory.provenance import ProvenanceLinker
from hermes_prime.contracts import MemoryClaim, IntentRoot


def test_memory_type_enum_values():
    assert MemoryType.WORKING.value == "working"
    assert MemoryType.EPISODIC.value == "episodic"
    assert MemoryType.SEMANTIC.value == "semantic"
    assert MemoryType.STRATEGIC.value == "strategic"
    assert MemoryType.REFLECTIVE.value == "reflective"
    assert MemoryType.GOVERNANCE.value == "governance"


def test_validation_status_enum_values():
    assert ValidationStatus.UNVERIFIED.value == "unverified"
    assert ValidationStatus.CORROBORATED.value == "corroborated"
    assert ValidationStatus.CONTRADICTED.value == "contradicted"


def test_memory_record_construction():
    now = datetime.now(timezone.utc)
    record = MemoryRecord(
        id="urn:uuid:123e4567-e89b-12d3-a456-426614174000",
        memory_type=MemoryType.EPISODIC,
        content="API endpoint is /v2/users",
        source_agent="agent-alpha",
        intent_root="urn:uuid:f81d4fae-7dec-11d0-a765-00a0c91e6bf6",
        created_at=now,
        updated_at=now,
        checksum="abc123",
        confidence=0.85,
        trust_level=TrustState.VALIDATED,
        lineage=[],
        causal_parent=None,
        tags=["api", "endpoint"],
        validation_status=ValidationStatus.CORROBORATED,
        embedding_id=None,
    )
    assert record.id == "urn:uuid:123e4567-e89b-12d3-a456-426614174000"
    assert record.memory_type == MemoryType.EPISODIC
    assert record.confidence == 0.85
    assert record.trust_level == TrustState.VALIDATED


def test_record_from_claim():
    linker = ProvenanceLinker()
    intent = IntentRoot(
        intent_root="urn:uuid:f81d4fae-7dec-11d0-a765-00a0c91e6bf6",
        scope="test",
        issued_to="agent-alpha",
        issued_at="2026-01-01T00:00:00Z",
        expires_at="2026-12-31T00:00:00Z",
        signature="sig:test",
    )
    claim = linker.build_claim(
        claim_text="API endpoint is /v2/users",
        source={"agent": "agent-alpha", "type": "observation"},
        intent_root=intent,
        epistemic_confidence=0.85,
        source_trust="observed",
    )
    record = record_from_claim(claim, memory_type=MemoryType.SEMANTIC)
    assert record.id == claim.fact_id
    assert record.content == claim.claim
    assert record.confidence == claim.epistemic_confidence
    assert record.trust_level == claim.trust_state
    assert record.memory_type == MemoryType.SEMANTIC
    assert record.source_agent == "agent-alpha"
    assert record.checksum is not None and len(record.checksum) > 0
    assert record.validation_status == ValidationStatus.UNVERIFIED
    assert record.lineage == []
    assert record.causal_parent is None
    assert record.tags == []


def test_claim_from_record():
    now = datetime.now(timezone.utc)
    record = MemoryRecord(
        id="urn:uuid:123e4567-e89b-12d3-a456-426614174000",
        memory_type=MemoryType.STRATEGIC,
        content="Avoid Tool X > 5 concurrent calls",
        source_agent="agent-beta",
        intent_root="urn:uuid:f81d4fae-7dec-11d0-a765-00a0c91e6bf6",
        created_at=now,
        updated_at=now,
        checksum="def456",
        confidence=0.95,
        trust_level=TrustState.VALIDATED,
        lineage=["urn:uuid:parent-1"],
        causal_parent="urn:uuid:parent-1",
        tags=["constraint", "tool-x"],
        validation_status=ValidationStatus.CORROBORATED,
        embedding_id=None,
    )
    claim = claim_from_record(record)
    assert claim.fact_id == record.id
    assert claim.claim == record.content
    assert claim.epistemic_confidence == record.confidence
    assert claim.trust_state == record.trust_level
    assert claim.source["agent"] == record.source_agent
    assert claim.source["memory_type"] == record.memory_type.value


def test_record_from_claim_round_trip():
    linker = ProvenanceLinker()
    intent = IntentRoot(
        intent_root="urn:uuid:f81d4fae-7dec-11d0-a765-00a0c91e6bf6",
        scope="test",
        issued_to="agent-alpha",
        issued_at="2026-01-01T00:00:00Z",
        expires_at="2026-12-31T00:00:00Z",
        signature="sig:test",
    )
    claim = linker.build_claim(
        claim_text="Round trip test",
        source={"agent": "agent-alpha"},
        intent_root=intent,
    )
    record = record_from_claim(claim, memory_type=MemoryType.EPISODIC)
    claim2 = claim_from_record(record)
    assert claim2.fact_id == claim.fact_id
    assert claim2.claim == claim.claim
    assert claim2.epistemic_confidence == claim.epistemic_confidence
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/memory/test_records.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'hermes_prime.memory.records'"

- [ ] **Step 3: Write MemoryRecord implementation**

File `hermes_prime/memory/records.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from hermes_prime.contracts import MemoryClaim, TrustState
from hermes_prime.utils import sha256_text


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


@dataclass
class MemoryRecord:
    id: str
    memory_type: MemoryType
    content: str
    source_agent: str
    intent_root: str
    created_at: datetime
    updated_at: datetime
    checksum: str
    confidence: float = 0.0
    trust_level: TrustState = TrustState.UNVERIFIED
    lineage: list[str] = field(default_factory=list)
    causal_parent: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    validation_status: ValidationStatus = ValidationStatus.UNVERIFIED
    embedding_id: Optional[str] = None


def record_from_claim(
    claim: MemoryClaim,
    memory_type: MemoryType = MemoryType.EPISODIC,
    tags: Optional[list[str]] = None,
    lineage: Optional[list[str]] = None,
    causal_parent: Optional[str] = None,
) -> MemoryRecord:
    from hermes_prime.utils import utc_now_iso, parse_iso8601

    source_agent = ""
    if isinstance(claim.source, dict):
        source_agent = claim.source.get("agent", "")

    created = parse_iso8601(claim.timestamp) if claim.timestamp else datetime.now()

    return MemoryRecord(
        id=claim.fact_id,
        memory_type=memory_type,
        content=claim.claim,
        source_agent=source_agent,
        intent_root=claim.intent_root,
        created_at=created,
        updated_at=created,
        checksum=sha256_text(claim.claim),
        confidence=claim.epistemic_confidence,
        trust_level=claim.trust_state if isinstance(claim.trust_state, TrustState) else TrustState(claim.trust_state),
        lineage=lineage or [],
        causal_parent=causal_parent,
        tags=tags or [],
        validation_status=ValidationStatus.UNVERIFIED,
        embedding_id=None,
    )


def claim_from_record(record: MemoryRecord) -> MemoryClaim:
    from hermes_prime.utils import utc_now_iso

    return MemoryClaim(
        fact_id=record.id,
        claim=record.content,
        source={
            "agent": record.source_agent,
            "memory_type": record.memory_type.value,
            "tags": record.tags,
            "lineage": record.lineage,
        },
        epistemic_confidence=record.confidence,
        verification_status=record.validation_status.value,
        source_trust="validated" if record.trust_level in (TrustState.VALIDATED, TrustState.EXECUTABLE) else "observed",
        timestamp=record.updated_at.isoformat().replace("+00:00", "Z") if record.updated_at else utc_now_iso(),
        trust_state=record.trust_level,
        tier="authoritative" if record.trust_level in (TrustState.VALIDATED, TrustState.EXECUTABLE) else "quarantine",
        contradictions=[],
        intent_root=record.intent_root,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/memory/test_records.py -v`
Expected: PASS (all 5 tests)

- [ ] **Step 5: Update memory `__init__.py` exports**

Edit `hermes_prime/memory/__init__.py`. Read current content, then replace it.

Current content:
```python
from hermes_prime.memory.backends import MemoryBackend, MemorySearchResult
from hermes_prime.memory.store import MemoryStore
from hermes_prime.memory.provenance import ProvenanceLinker
from hermes_prime.memory.depth import DepthPolicy

__all__ = [
    "MemoryBackend",
    "MemorySearchResult",
    "MemoryStore",
    "ProvenanceLinker",
    "DepthPolicy",
]
```

Replace with:
```python
from hermes_prime.memory.backends import MemoryBackend, MemorySearchResult
from hermes_prime.memory.store import MemoryStore
from hermes_prime.memory.provenance import ProvenanceLinker
from hermes_prime.memory.depth import DepthPolicy
from hermes_prime.memory.records import MemoryRecord, MemoryType, ValidationStatus, record_from_claim, claim_from_record

__all__ = [
    "MemoryBackend",
    "MemorySearchResult",
    "MemoryStore",
    "ProvenanceLinker",
    "DepthPolicy",
    "MemoryRecord",
    "MemoryType",
    "ValidationStatus",
    "record_from_claim",
    "claim_from_record",
]
```

- [ ] **Step 6: Run full memory test suite**

Run: `python -m pytest tests/memory/ -v`
Expected: all existing tests pass + new tests pass

- [ ] **Step 7: Commit**

```bash
git add hermes_prime/memory/records.py hermes_prime/memory/__init__.py tests/memory/test_records.py
git commit -m "feat(memory): add MemoryRecord object model with MemoryType, ValidationStatus (Phase 2)"
```

---

### Task 3: Enhance MemoryStore for MemoryRecord

**Files:**
- Modify: `hermes_prime/memory/store.py`

- [ ] **Step 1: Write failing tests**

Append to existing `tests/memory/test_store.py` (or create if not exists):

First, read `tests/memory/` to check existing test files:

```bash
Get-ChildItem -Path tests/memory/ -Recurse -Name
```

Then add these tests:

```python
def test_write_returns_record(memory_store, sample_intent):
    result = memory_store.write(
        claim_text="MemoryRecord integration test",
        source={"agent": "test-agent"},
        intent_root=sample_intent,
        epistemic_confidence=0.75,
    )
    assert result.success
    assert result.record is not None
    assert result.record.content == "MemoryRecord integration test"
    assert result.record.source_agent == "test-agent"
    assert result.record.memory_type is not None
    assert result.record.checksum is not None


def test_write_record_has_trust_level(memory_store, sample_intent):
    result = memory_store.write(
        claim_text="Trust level test",
        source={"agent": "test-agent"},
        intent_root=sample_intent,
    )
    assert result.success
    assert result.record.trust_level is not None


def test_write_record_default_memory_type(memory_store, sample_intent):
    result = memory_store.write(
        claim_text="Default type test",
        source={"agent": "test-agent"},
        intent_root=sample_intent,
    )
    assert result.success
    assert result.record.memory_type.value == "episodic"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/memory/test_store.py -v`
Expected: FAIL — "MemoryStoreResult" has no attribute "record"

- [ ] **Step 3: Add `record` field to MemoryStoreResult**

Edit `hermes_prime/memory/store.py`. Add import and field:

Add import at top:
```python
from hermes_prime.memory.records import MemoryRecord, MemoryType, record_from_claim
```

Add to `MemoryStoreResult` dataclass:
```python
@dataclass
class MemoryStoreResult:
    success: bool
    fact_id: str = ""
    attestation: MemoryAttestation | None = None
    error: str = ""
    claim: MemoryClaim | None = None
    record: MemoryRecord | None = None  # NEW
    results: list[MemorySearchResult] = field(default_factory=list)
```

- [ ] **Step 4: Modify `MemoryStore.write()` to populate record**

In the `write` method of `MemoryStore`, after `self.backend.store(claim)` succeeds, add:

```python
record = record_from_claim(claim, memory_type=MemoryType.EPISODIC)
```

Then update the return to include record:

```python
return MemoryStoreResult(
    success=True,
    fact_id=claim.fact_id,
    attestation=attestation,
    claim=claim,
    record=record,  # NEW
    total_count=total + 1,
)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/memory/test_store.py -v`
Expected: PASS

- [ ] **Step 6: Run full memory test suite**

Run: `python -m pytest tests/memory/ -v`
Expected: all existing tests pass + new tests pass

- [ ] **Step 7: Commit**

```bash
git add hermes_prime/memory/store.py tests/memory/test_store.py
git commit -m "feat(memory): return MemoryRecord from MemoryStore.write() (Phase 2)"
```

---

### Task 4: Add MemPalace Backend Adapter

**Files:**
- Create: `hermes_prime/memory/backends/mempalace_backend.py`
- Create: `tests/memory/test_mempalace_backend.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Add mempalace dependency**

Edit `pyproject.toml`, add to `[project.optional-dependencies]`:

```toml
memory = ["mempalace>=3.3"]
```

- [ ] **Step 2: Write integration tests**

File `tests/memory/test_mempalace_backend.py`:

```python
"""Integration tests for MemPalaceBackend.

These tests require mempalace to be installed.
Run with: python -m pytest tests/memory/test_mempalace_backend.py -v
"""

import pytest
from hermes_prime.contracts import MemoryClaim, TrustState, MemoryTier
from hermes_prime.utils import new_urn_uuid, utc_now_iso


@pytest.fixture
def mempalace_backend():
    from hermes_prime.memory.backends.mempalace_backend import MemPalaceBackend
    import tempfile, os
    db_dir = tempfile.mkdtemp(prefix="mempalace_test_")
    backend = MemPalaceBackend(palace_path=db_dir)
    yield backend
    import shutil
    shutil.rmtree(db_dir, ignore_errors=True)


@pytest.fixture
def sample_claim():
    return MemoryClaim(
        fact_id=new_urn_uuid(),
        claim="Test memory content for MemPalace backend",
        source={"agent": "test-agent", "type": "test"},
        epistemic_confidence=0.8,
        verification_status="unverified",
        source_trust="observed",
        timestamp=utc_now_iso(),
        trust_state=TrustState.UNVERIFIED,
        tier=MemoryTier.QUARANTINE,
        contradictions=[],
        intent_root="urn:uuid:f81d4fae-7dec-11d0-a765-00a0c91e6bf6",
    )


def test_store_and_get(mempalace_backend, sample_claim):
    mempalace_backend.store(sample_claim)
    retrieved = mempalace_backend.get(sample_claim.fact_id)
    assert retrieved is not None
    assert retrieved.fact_id == sample_claim.fact_id
    assert retrieved.claim == sample_claim.claim


def test_store_and_search(mempalace_backend, sample_claim):
    mempalace_backend.store(sample_claim)
    results = mempalace_backend.search("Test memory content", limit=5)
    assert len(results) >= 1
    assert any(r.fact_id == sample_claim.fact_id for r in results)


def test_get_nonexistent(mempalace_backend):
    retrieved = mempalace_backend.get("urn:uuid:nonexistent")
    assert retrieved is None


def test_delete(mempalace_backend, sample_claim):
    mempalace_backend.store(sample_claim)
    deleted = mempalace_backend.delete(sample_claim.fact_id)
    assert deleted is True
    assert mempalace_backend.get(sample_claim.fact_id) is None


def test_delete_nonexistent(mempalace_backend):
    deleted = mempalace_backend.delete("urn:uuid:nonexistent")
    assert deleted is False


def test_count(mempalace_backend, sample_claim):
    assert mempalace_backend.count() == 0
    mempalace_backend.store(sample_claim)
    assert mempalace_backend.count() == 1


def test_list_all(mempalace_backend, sample_claim):
    mempalace_backend.store(sample_claim)
    all_claims = mempalace_backend.list_all()
    assert len(all_claims) == 1
    assert all_claims[0].fact_id == sample_claim.fact_id


def test_gc(mempalace_backend, sample_claim):
    from datetime import datetime, timedelta, timezone
    mempalace_backend.store(sample_claim)
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat().replace("+00:00", "Z")
    deleted = mempalace_backend.gc(future)
    assert deleted == 1
    assert mempalace_backend.count() == 0
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/memory/test_mempalace_backend.py -v`
Expected: FAIL — ModuleNotFoundError for mempalace_backend

- [ ] **Step 4: Write MemPalaceBackend implementation**

File `hermes_prime/memory/backends/mempalace_backend.py`:

```python
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

from hermes_prime.contracts import MemoryClaim, MemoryTier, TrustState
from hermes_prime.memory.backends import MemoryBackend, MemorySearchResult
from hermes_prime.utils import new_urn_uuid, utc_now_iso


class MemPalaceBackend(MemoryBackend):
    """MemoryBackend implementation using MemPalace as the verbatim store.

    Maps HERMES memory records to MemPalace's wing/room/drawer model:
    - memory_type → wing
    - source_agent → room
    - individual record → drawer
    """

    def __init__(self, palace_path: str | None = None):
        if palace_path is None:
            palace_path = os.path.join(os.path.expanduser("~"), ".hermes-prime", "palace")
        self.palace_path = str(Path(palace_path).expanduser().resolve())
        self._collection = None
        self._initialized = False

    def _ensure_initialized(self):
        if self._initialized:
            return
        from mempalace.config import MempalaceConfig
        os.makedirs(self.palace_path, exist_ok=True)
        self._initialized = True

    def _get_collection(self):
        self._ensure_initialized()
        if self._collection is None:
            from mempalace.palace import get_collection
            self._collection = get_collection(self.palace_path)
        return self._collection

    def _wing_for_claim(self, claim: MemoryClaim) -> str:
        memory_type = "episodic"
        if claim.source and isinstance(claim.source, dict):
            memory_type = claim.source.get("memory_type", "episodic")
        return f"hermes_{memory_type}"

    def _room_for_claim(self, claim: MemoryClaim) -> str:
        agent = "unknown"
        if claim.source and isinstance(claim.source, dict):
            agent = claim.source.get("agent", "unknown")
        return agent

    def store(self, claim: MemoryClaim) -> None:
        self._ensure_initialized()
        from mempalace.miner import add_drawer

        wing = self._wing_for_claim(claim)
        room = self._room_for_claim(claim)
        collection = self._get_collection()

        add_drawer(
            collection=collection,
            wing=wing,
            room=room,
            content=claim.claim,
            source_file=f"hermes://{claim.fact_id}",
            chunk_index=0,
            agent="hermes-prime",
        )

    def get(self, fact_id: str) -> MemoryClaim | None:
        self._ensure_initialized()
        try:
            from mempalace.palace import get_collection
            collection = get_collection(self.palace_path)
            results = collection.get(
                where={"source_file": f"hermes://{fact_id}"},
                limit=1,
            )
            if results and results.get("ids") and len(results["ids"]) > 0:
                idx = 0
                metadata = results["metadatas"][idx] if results.get("metadatas") else {}
                documents = results["documents"][idx] if results.get("documents") else ""
                return self._claim_from_mempalace_result(
                    fact_id=fact_id,
                    content=documents,
                    metadata=metadata,
                )
            return None
        except Exception:
            return None

    def search(self, query: str, limit: int = 10) -> list[MemorySearchResult]:
        self._ensure_initialized()
        try:
            from mempalace.searcher import search_memories
            result = search_memories(
                query=query,
                palace_path=self.palace_path,
                n_results=limit,
            )
            if isinstance(result, dict) and "results" in result:
                search_results = []
                for r in result["results"]:
                    fact_id = self._fact_id_from_drawer(r)
                    search_results.append(MemorySearchResult(
                        fact_id=fact_id,
                        claim=r.get("text", ""),
                        source={"agent": r.get("room", "unknown")},
                        epistemic_confidence=float(r.get("similarity", 0.0)),
                        verification_status="unverified",
                        source_trust="observed",
                        timestamp=utc_now_iso(),
                        trust_state=TrustState.UNVERIFIED.value,
                        tier=MemoryTier.QUARANTINE.value,
                        contradictions=[],
                        intent_root="",
                        similarity=float(r.get("similarity", 0.0)),
                    ))
                return search_results
            return []
        except Exception:
            return []

    def list_all(self) -> list[MemoryClaim]:
        self._ensure_initialized()
        try:
            collection = self._get_collection()
            results = collection.get(limit=1000)
            claims = []
            if results and results.get("ids"):
                for i, doc_id in enumerate(results["ids"]):
                    metadata = results["metadatas"][i] if results.get("metadatas") else {}
                    content = results["documents"][i] if results.get("documents") else ""
                    fact_id = self._fact_id_from_source(metadata)
                    claims.append(self._claim_from_mempalace_result(
                        fact_id=fact_id,
                        content=content,
                        metadata=metadata,
                    ))
            return claims
        except Exception:
            return []

    def delete(self, fact_id: str) -> bool:
        self._ensure_initialized()
        try:
            collection = self._get_collection()
            existing = collection.get(
                where={"source_file": f"hermes://{fact_id}"},
                limit=1,
            )
            if existing and existing.get("ids") and len(existing["ids"]) > 0:
                collection.delete(ids=[existing["ids"][0]])
                return True
            return False
        except Exception:
            return False

    def count(self) -> int:
        self._ensure_initialized()
        try:
            collection = self._get_collection()
            return collection.count()
        except Exception:
            return 0

    def gc(self, before_timestamp: str) -> int:
        self._ensure_initialized()
        try:
            collection = self._get_collection()
            all_items = collection.get(limit=10000)
            if not all_items or not all_items.get("ids"):
                return 0
            to_delete = []
            for i, meta in enumerate(all_items.get("metadatas", [])):
                if meta and "filed_at" in meta:
                    if meta["filed_at"] < before_timestamp:
                        to_delete.append(all_items["ids"][i])
            if to_delete:
                collection.delete(ids=to_delete)
            return len(to_delete)
        except Exception:
            return 0

    def _claim_from_mempalace_result(
        self, fact_id: str, content: str, metadata: dict
    ) -> MemoryClaim:
        agent = metadata.get("room", "unknown") if metadata else "unknown"
        return MemoryClaim(
            fact_id=fact_id,
            claim=content,
            source={"agent": agent, "memory_type": metadata.get("wing", "episodic") if metadata else "episodic"},
            epistemic_confidence=0.5,
            verification_status="unverified",
            source_trust="observed",
            timestamp=metadata.get("filed_at", utc_now_iso()) if metadata else utc_now_iso(),
            trust_state=TrustState.UNVERIFIED,
            tier=MemoryTier.QUARANTINE,
            contradictions=[],
            intent_root="",
        )

    def _fact_id_from_drawer(self, result: dict) -> str:
        source = result.get("source_file", "")
        if source and source.startswith("hermes://"):
            return source[len("hermes://"):]
        return new_urn_uuid()

    def _fact_id_from_source(self, metadata: dict) -> str:
        if metadata:
            source = metadata.get("source_file", "")
            if source and source.startswith("hermes://"):
                return source[len("hermes://"):]
        return new_urn_uuid()
```

- [ ] **Step 5: Install mempalace and run tests**

```bash
pip install mempalace>=3.3
python -m pytest tests/memory/test_mempalace_backend.py -v
```

Expected: PASS (all 9 tests)

- [ ] **Step 6: Run full memory test suite**

Run: `python -m pytest tests/memory/ -v`
Expected: all existing tests pass + all new tests pass

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml hermes_prime/memory/backends/mempalace_backend.py tests/memory/test_mempalace_backend.py
git commit -m "feat(memory): add MemPalaceBackend adapter (Phase 1)"
```

---

## Self-Review Checklist

- **Spec coverage:** Governance doc covers memory_types, trust_levels, retention, ownership, decay policy, prohibitions. MemoryRecord covers all fields from the spec. MemPalaceBackend implements all 7 MemoryBackend ABC methods.
- **Placeholder scan:** No "TBD", "TODO", or vague instructions. Every step has complete code.
- **Type consistency:** `MemoryRecord.confidence` matches `MemoryClaim.epistemic_confidence`. `MemoryRecord.trust_level` matches `MemoryClaim.trust_state` (both `TrustState`). `MemoryType` matches the governance spec's 6 types. `ValidationStatus` has 3 states as designed. Method signatures in Task 4 (MemPalaceBackend) match the `MemoryBackend` ABC from existing `backends.py`.
- **Test coverage:** MemoryRecord construction (1 test), record_from_claim (1), claim_from_record (1), round-trip (1), enum values (2), MemPalaceBackend CRUD (9), MemoryStore record return (3).

from __future__ import annotations

from datetime import datetime, timezone

from hermes_prime.contracts import IntentRoot, MemoryClaim, TrustState
from hermes_prime.memory.records import (
    MemoryRecord,
    MemoryType,
    ValidationStatus,
    claim_from_record,
    record_from_claim,
)
from hermes_prime.memory.provenance import ProvenanceLinker
from hermes_prime.utils import new_urn_uuid


class TestMemoryRecord:
    def test_memory_type_enum_values(self):
        assert MemoryType.WORKING.value == "working"
        assert MemoryType.EPISODIC.value == "episodic"
        assert MemoryType.SEMANTIC.value == "semantic"
        assert MemoryType.STRATEGIC.value == "strategic"
        assert MemoryType.REFLECTIVE.value == "reflective"
        assert MemoryType.GOVERNANCE.value == "governance"

    def test_validation_status_enum_values(self):
        assert ValidationStatus.UNVERIFIED.value == "unverified"
        assert ValidationStatus.CORROBORATED.value == "corroborated"
        assert ValidationStatus.CONTRADICTED.value == "contradicted"

    def test_memory_record_construction(self):
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
        assert record.validation_status == ValidationStatus.CORROBORATED
        assert record.checksum == "abc123"
        assert record.causal_parent is None

    def test_record_from_claim(self):
        linker = ProvenanceLinker()
        intent = IntentRoot(
            intent_root=new_urn_uuid(),
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

    def test_claim_from_record(self):
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

    def test_record_from_claim_round_trip(self):
        linker = ProvenanceLinker()
        intent = IntentRoot(
            intent_root=new_urn_uuid(),
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

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
    from hermes_prime.utils import parse_iso8601

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

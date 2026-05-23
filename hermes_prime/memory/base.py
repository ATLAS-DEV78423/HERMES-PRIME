from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from hermes_prime.contracts import MemoryClaim


@dataclass
class MemorySearchResult:
    fact_id: str
    claim: str
    source: dict[str, Any]
    epistemic_confidence: float
    verification_status: str
    source_trust: str
    timestamp: str
    trust_state: str
    tier: str
    contradictions: list[dict[str, Any]] = field(default_factory=list)
    intent_root: str = ""
    similarity: float = 0.0

    @classmethod
    def from_claim(cls, claim: MemoryClaim, similarity: float = 0.0) -> MemorySearchResult:
        return cls(
            fact_id=claim.fact_id,
            claim=claim.claim,
            source=claim.source,
            epistemic_confidence=claim.epistemic_confidence,
            verification_status=claim.verification_status,
            source_trust=claim.source_trust,
            timestamp=claim.timestamp,
            trust_state=claim.trust_state.value if hasattr(claim.trust_state, 'value') else claim.trust_state,
            tier=claim.tier.value if hasattr(claim.tier, 'value') else claim.tier,
            contradictions=list(claim.contradictions),
            intent_root=claim.intent_root,
            similarity=similarity,
        )


class MemoryBackend(ABC):
    @abstractmethod
    def store(self, claim: MemoryClaim) -> None:
        ...

    @abstractmethod
    def get(self, fact_id: str) -> MemoryClaim | None:
        ...

    @abstractmethod
    def search(self, query: str, limit: int = 10) -> list[MemorySearchResult]:
        ...

    @abstractmethod
    def list_all(self) -> list[MemoryClaim]:
        ...

    @abstractmethod
    def delete(self, fact_id: str) -> bool:
        ...

    @abstractmethod
    def count(self) -> int:
        ...

    @abstractmethod
    def gc(self, before_timestamp: str) -> int:
        ...

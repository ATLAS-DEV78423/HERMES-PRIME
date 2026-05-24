from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from hermes_prime.contracts import IntentRoot, MemoryClaim, TrustState
from hermes_prime.memory.store import MemoryStore, MemoryStoreResult


@dataclass
class ContradictionResult:
    fact_id: str
    contradictions: list[dict[str, Any]] = field(default_factory=list)

    @property
    def has_contradictions(self) -> bool:
        return len(self.contradictions) > 0


_WORD_SPLIT = re.compile(r"\W+")


def _tokenize(text: str) -> set[str]:
    return {t.lower() for t in _WORD_SPLIT.split(text) if len(t) > 2}


def _jaccard_similarity(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    intersection = a & b
    union = a | b
    return len(intersection) / len(union)


class ContradictionDetector:
    def __init__(self, similarity_threshold: float = 0.5) -> None:
        self.similarity_threshold = similarity_threshold

    def detect_against_claim(
        self,
        claim: MemoryClaim,
        existing_claims: list[MemoryClaim],
    ) -> list[dict[str, Any]]:
        contradictions: list[dict[str, Any]] = []
        new_tokens = _tokenize(claim.claim)

        for existing in existing_claims:
            if existing.fact_id == claim.fact_id:
                continue
            if existing.intent_root != claim.intent_root:
                continue

            existing_tokens = _tokenize(existing.claim)
            sim = _jaccard_similarity(new_tokens, existing_tokens)

            if sim >= self.similarity_threshold:
                contradictions.append({
                    "fact_id": existing.fact_id,
                    "reason": f"similar claim within same intent (similarity={sim:.2f})",
                    "existing_claim": existing.claim,
                    "similarity": sim,
                })

        return contradictions

    def detect_explicit(
        self,
        fact_id: str,
        explicit: list[str],
        existing_claims: list[MemoryClaim],
    ) -> list[dict[str, Any]]:
        contradictions: list[dict[str, Any]] = []
        existing_by_id: dict[str, MemoryClaim] = {
            c.fact_id: c for c in existing_claims
        }
        for target_id in explicit:
            if target_id in existing_by_id:
                contradictions.append({
                    "fact_id": target_id,
                    "reason": "explicit contradiction declared",
                    "existing_claim": existing_by_id[target_id].claim,
                    "similarity": 0.0,
                })
        return contradictions


class MemoryGovernor:
    def __init__(
        self,
        memory_store: MemoryStore,
        detector: Optional[ContradictionDetector] = None,
    ) -> None:
        self.memory_store = memory_store
        self.detector = detector or ContradictionDetector()

    def review(
        self,
        claim_text: str,
        source: dict[str, Any],
        intent_root: IntentRoot,
        epistemic_confidence: float = 0.5,
        source_trust: str = "observed",
        causal_parent: Optional[str] = None,
        contradicts: Optional[list[str]] = None,
    ) -> MemoryStoreResult:
        existing_claims = self.memory_store.list_all().claims

        store_result = self.memory_store.write(
            claim_text=claim_text,
            source=source,
            intent_root=intent_root,
            epistemic_confidence=epistemic_confidence,
            source_trust=source_trust,
            causal_parent=causal_parent,
        )

        if not store_result.success or not store_result.claim:
            return store_result

        claim = store_result.claim
        detected: list[dict[str, Any]] = []

        if claim.intent_root:
            detected = self.detector.detect_against_claim(claim, existing_claims)

        if contradicts:
            explicit = self.detector.detect_explicit(
                claim.fact_id, contradicts, existing_claims,
            )
            detected.extend(explicit)

        if detected:
            claim.contradictions = detected
            self.memory_store.backend.store(claim)

            for c in detected:
                other_id = c["fact_id"]
                other = self.memory_store.backend.get(other_id)
                if other is not None:
                    back_ref = {
                        "fact_id": claim.fact_id,
                        "reason": c["reason"],
                        "existing_claim": claim.claim,
                        "similarity": c.get("similarity", 0.0),
                    }
                    if back_ref not in other.contradictions:
                        other.contradictions.append(back_ref)
                    self.memory_store.backend.store(other)

        result = self.memory_store.get(claim.fact_id)
        if result.success:
            result.total_count = len(detected)
        return result

    def arbitrate(
        self,
        fact_id_a: str,
        fact_id_b: str,
        resolution: str = "keep_a",
    ) -> MemoryStoreResult:
        claim_a = self.memory_store.backend.get(fact_id_a)
        claim_b = self.memory_store.backend.get(fact_id_b)

        if claim_a is None or claim_b is None:
            return MemoryStoreResult(
                success=False,
                error="one or both fact_ids not found",
            )

        claim_a.contradictions = [
            c for c in claim_a.contradictions
            if c.get("fact_id") != fact_id_b
        ]
        claim_b.contradictions = [
            c for c in claim_b.contradictions
            if c.get("fact_id") != fact_id_a
        ]

        if resolution == "keep_a":
            claim_a.trust_state = TrustState.VALIDATED
            claim_b.trust_state = TrustState.REVOKED
        elif resolution == "keep_b":
            claim_a.trust_state = TrustState.REVOKED
            claim_b.trust_state = TrustState.VALIDATED
        else:
            return MemoryStoreResult(
                success=False,
                error=f"unknown resolution: {resolution}",
            )

        self.memory_store.backend.store(claim_a)
        self.memory_store.backend.store(claim_b)

        return MemoryStoreResult(success=True, fact_id=fact_id_a)

    def get_contradictions(
        self, fact_id: str,
    ) -> list[dict[str, Any]]:
        claim = self.memory_store.backend.get(fact_id)
        if claim is None:
            return []
        return list(claim.contradictions)

    def get_contradiction_count(self, fact_id: str) -> int:
        return len(self.get_contradictions(fact_id))

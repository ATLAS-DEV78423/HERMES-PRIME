from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from hermes_prime.contracts import IntentRoot, MemoryClaim
from hermes_prime.memory.graph import KnowledgeGraph
from hermes_prime.memory.records import MemoryType, record_from_claim
from hermes_prime.memory.store import MemoryStore, MemoryStoreResult


@dataclass
class ConsolidationRequest:
    intent_root: IntentRoot
    summary: str
    patterns: list[dict[str, Any]] = field(default_factory=list)
    source_fact_ids: Optional[list[str]] = None


@dataclass
class PatternResult:
    fact_id: str
    pattern: dict[str, Any]


@dataclass
class ConsolidationResult:
    success: bool
    intent_root: str
    reflective_fact_id: str = ""
    source_count: int = 0
    patterns: list[PatternResult] = field(default_factory=list)
    error: str = ""


class ReflectiveConsolidator:
    def __init__(
        self,
        memory_store: MemoryStore,
    ) -> None:
        self.memory_store = memory_store

    def consolidate(self, request: ConsolidationRequest) -> ConsolidationResult:
        all_claims = self.memory_store.list_all().claims
        source_claims = [
            c for c in all_claims
            if c.intent_root == request.intent_root.intent_root
        ]

        if request.source_fact_ids is not None:
            source_claims = [
                c for c in source_claims
                if c.fact_id in request.source_fact_ids
            ]
            source_claims.sort(
                key=lambda c: request.source_fact_ids.index(c.fact_id)
                if c.fact_id in request.source_fact_ids
                else 0,
            )

        source_ids = [c.fact_id for c in source_claims]

        causal_parent = source_ids[0] if source_ids else None

        ref_result = self.memory_store.write(
            claim_text=request.summary,
            source={"agent": "system:consolidator", "memory_type": "reflective", "consolidation_of": request.intent_root.intent_root},
            intent_root=request.intent_root,
            epistemic_confidence=0.9,
            source_trust="validated",
            causal_parent=causal_parent,
        )

        if not ref_result.success:
            return ConsolidationResult(
                success=False,
                intent_root=request.intent_root.intent_root,
                error=ref_result.error,
            )

        pattern_results: list[PatternResult] = []
        for pattern in request.patterns:
            pattern_text = pattern.get("text", "")
            pattern_source_ids = pattern.get("source_fact_ids", [])

            pattern_causal = pattern_source_ids[0] if pattern_source_ids else ref_result.fact_id

            pat_result = self.memory_store.write(
                claim_text=pattern_text,
                source={
                    "agent": "system:consolidator",
                    "memory_type": "strategic",
                    "consolidation_of": request.intent_root.intent_root,
                    "pattern_type": pattern.get("type", ""),
                },
                intent_root=request.intent_root,
                epistemic_confidence=0.95,
                source_trust="validated",
                causal_parent=pattern_causal,
            )

            if pat_result.success:
                pattern_results.append(PatternResult(
                    fact_id=pat_result.fact_id,
                    pattern=pattern,
                ))

        return ConsolidationResult(
            success=True,
            intent_root=request.intent_root.intent_root,
            reflective_fact_id=ref_result.fact_id,
            source_count=len(source_ids),
            patterns=pattern_results,
        )

    def get_consolidations(
        self,
        intent_root: str,
    ) -> list[MemoryClaim]:
        all_claims = self.memory_store.list_all().claims
        return [
            c for c in all_claims
            if c.intent_root == intent_root
            and isinstance(c.source, dict)
            and c.source.get("memory_type") == "reflective"
        ]

    def get_patterns(
        self,
        intent_root: str,
    ) -> list[MemoryClaim]:
        all_claims = self.memory_store.list_all().claims
        return [
            c for c in all_claims
            if c.intent_root == intent_root
            and isinstance(c.source, dict)
            and c.source.get("memory_type") == "strategic"
        ]

    def get_reflective_lineage(
        self,
        fact_id: str,
    ) -> list[dict[str, Any]]:
        lineage_ids = self.memory_store.knowledge_graph.get_lineage(fact_id)
        result: list[dict[str, Any]] = []
        for lid in lineage_ids:
            claim = self.memory_store.backend.get(lid)
            if claim is not None:
                result.append({
                    "fact_id": claim.fact_id,
                    "claim": claim.claim,
                    "source": claim.source,
                })
        return result

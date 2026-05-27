from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from hermes_prime.memory.base import MemorySearchResult
from hermes_prime.memory.graph import KnowledgeGraph
from hermes_prime.memory.store import MemoryStore

_TRUST_ORDER: dict[str, int] = {
    "UNVERIFIED": 0,
    "OBSERVED": 1,
    "ATTESTED": 2,
    "VALIDATED": 3,
    "EXECUTABLE": 4,
}


def _trust_score(trust_state: str) -> int:
    return _TRUST_ORDER.get(trust_state.upper(), -1)


@dataclass
class ContextQuery:
    query: str
    limit: int = 10
    min_confidence: float = 0.0
    min_tier: str = "quarantine"
    min_trust: str = "unverified"
    memory_types: Optional[list[str]] = None
    include_lineage: bool = True
    compress_chains: bool = False


@dataclass
class CompressedChain:
    root_id: str
    root_claim: str
    depth: int
    summary: str
    fact_ids: list[str]


@dataclass
class ContextResult:
    query: str
    memories: list[MemorySearchResult] = field(default_factory=list)
    chains: list[CompressedChain] = field(default_factory=list)
    total_found: int = 0
    filtered_count: int = 0
    trust_distribution: dict[str, int] = field(default_factory=dict)


class TrustFilter:
    def filter(
        self,
        results: list[MemorySearchResult],
        min_confidence: float = 0.0,
        min_trust: str = "unverified",
        min_tier: str = "quarantine",
        memory_types: Optional[list[str]] = None,
    ) -> list[MemorySearchResult]:
        min_trust_score = _trust_score(min_trust)
        filtered: list[MemorySearchResult] = []
        for r in results:
            trust_score = _trust_score(r.trust_state)
            if trust_score < min_trust_score:
                continue
            if trust_score < 0:
                continue
            if r.epistemic_confidence < min_confidence:
                continue
            tier = r.tier if hasattr(r, "tier") else "quarantine"
            if tier == "quarantine" and min_tier != "quarantine":
                continue
            if r.tier == "quarantine" and min_tier == "authoritative":
                continue
            if memory_types is not None:
                mt = r.source.get("memory_type", "") if isinstance(r.source, dict) else ""
                if mt not in memory_types:
                    continue
            filtered.append(r)
        return filtered

    def rank(self, results: list[MemorySearchResult]) -> list[MemorySearchResult]:
        def _score(r: MemorySearchResult) -> tuple:
            trust = _trust_score(r.trust_state)
            sim = r.similarity if hasattr(r, "similarity") else 0.0
            return (trust, sim)

        return sorted(results, key=_score, reverse=True)


class ChainCompressor:
    def __init__(self, knowledge_graph: KnowledgeGraph) -> None:
        self.graph = knowledge_graph

    def compress(self, results: list[MemorySearchResult]) -> list[CompressedChain]:
        result_by_id: dict[str, MemorySearchResult] = {}
        for r in results:
            if r.fact_id:
                result_by_id[r.fact_id] = r

        roots: list[str] = []
        for r in results:
            if not r.fact_id:
                continue
            lineage = self.graph.get_lineage(r.fact_id)
            ancestors_in_results = [a for a in lineage if a in result_by_id]
            if not ancestors_in_results:
                roots.append(r.fact_id)

        chains: list[CompressedChain] = []
        seen: set[str] = set()
        for root_id in roots:
            descendants = self._collect_descendants_in_results(root_id, result_by_id)
            chain_ids = [root_id] + descendants
            seen.update(chain_ids)
            root_result = result_by_id[root_id]
            chain_claims = [root_result.claim]
            for d_id in descendants:
                if d_id in result_by_id:
                    chain_claims.append(result_by_id[d_id].claim)
            chains.append(
                CompressedChain(
                    root_id=root_id,
                    root_claim=root_result.claim,
                    depth=len(chain_ids),
                    summary=" | ".join(chain_claims),
                    fact_ids=chain_ids,
                )
            )

        for r in results:
            if r.fact_id and r.fact_id not in seen:
                chains.append(
                    CompressedChain(
                        root_id=r.fact_id,
                        root_claim=r.claim,
                        depth=1,
                        summary=r.claim,
                        fact_ids=[r.fact_id],
                    )
                )

        return chains

    def _collect_descendants_in_results(
        self,
        fact_id: str,
        result_by_id: dict[str, MemorySearchResult],
    ) -> list[str]:
        collected: list[str] = []
        queue: list[str] = [fact_id]
        while queue:
            current = queue.pop(0)
            for child in self.graph.get_descendants(current):
                if child in result_by_id and child not in collected:
                    collected.append(child)
                    queue.append(child)
        return collected


class ContextCompiler:
    def __init__(
        self,
        memory_store: MemoryStore,
        trust_filter: Optional[TrustFilter] = None,
        chain_compressor: Optional[ChainCompressor] = None,
    ) -> None:
        self.memory_store = memory_store
        self.trust_filter = trust_filter or TrustFilter()
        self.chain_compressor = chain_compressor

    def compile(self, query: ContextQuery) -> ContextResult:
        store_result = self.memory_store.recall(query.query, limit=query.limit * 2)
        all_results = store_result.results or []

        filtered = self.trust_filter.filter(
            all_results,
            min_confidence=query.min_confidence,
            min_trust=query.min_trust,
            min_tier=query.min_tier,
            memory_types=query.memory_types,
        )

        ranked = self.trust_filter.rank(filtered)
        truncated = ranked[: query.limit]

        trust_dist: dict[str, int] = {}
        for r in truncated:
            ts = r.trust_state
            trust_dist[ts] = trust_dist.get(ts, 0) + 1

        chains: list[CompressedChain] = []
        if query.compress_chains and self.chain_compressor:
            chains = self.chain_compressor.compress(truncated)

        return ContextResult(
            query=query.query,
            memories=truncated,
            chains=chains,
            total_found=len(all_results),
            filtered_count=len(all_results) - len(filtered),
            trust_distribution=trust_dist,
        )

    def compile_by_intent(
        self,
        intent_root: str,
        query: str = "",
        limit: int = 10,
        min_confidence: float = 0.0,
        min_trust: str = "unverified",
        compress_chains: bool = False,
    ) -> ContextResult:
        store_result = self.memory_store.list_all()
        all_claims = store_result.claims or []

        all_results: list[MemorySearchResult] = []
        for claim in all_claims:
            if claim.intent_root == intent_root:
                text_match = True
                if query:
                    text_match = query.lower() in (claim.claim or "").lower()
                if text_match:
                    all_results.append(MemorySearchResult.from_claim(claim))

        filtered = self.trust_filter.filter(
            all_results,
            min_confidence=min_confidence,
            min_trust=min_trust,
        )
        ranked = self.trust_filter.rank(filtered)
        truncated = ranked[:limit]

        trust_dist: dict[str, int] = {}
        for r in truncated:
            ts = r.trust_state
            trust_dist[ts] = trust_dist.get(ts, 0) + 1

        chains: list[CompressedChain] = []
        if compress_chains and self.chain_compressor:
            chains = self.chain_compressor.compress(truncated)

        return ContextResult(
            query=query,
            memories=truncated,
            chains=chains,
            total_found=len(all_results),
            filtered_count=len(all_results) - len(filtered),
            trust_distribution=trust_dist,
        )

from __future__ import annotations

from pathlib import Path
from typing import Any

from hermes_prime.contracts import MemoryClaim, MemoryTier, TrustState
from hermes_prime.memory.base import MemoryBackend, MemorySearchResult
from hermes_prime.memory.graphify_bridge import GraphifyBridge
from hermes_prime.utils import utc_now_iso


class GraphifyBackend(MemoryBackend):
    """MemoryBackend that combines claim storage with graphify knowledge graph.

    Uses SQLite for claim persistence and graphify for codebase knowledge
    graph construction and entity-aware search.

    Features:
    - Claim storage via internal SQLite backend
    - Codebase knowledge graph via graphify extract-build pipeline
    - Entity-boosted search using graphify's graph relationships
    - Subgraph extraction for context-aware retrieval
    """

    def __init__(
        self,
        workspace_path: str | Path | None = None,
        db_path: str | Path | None = None,
    ) -> None:
        self.workspace_path = Path(workspace_path).resolve() if workspace_path else Path.cwd().resolve()
        self.bridge = GraphifyBridge(workspace_path=self.workspace_path)

        db = db_path or self.workspace_path / ".hermes-prime" / "graphify_memory.db"
        from hermes_prime.memory.backends.sqlite_backend import SQLiteMemoryBackend
        self._store = SQLiteMemoryBackend(db)

        self._graph_built = False

    @property
    def available(self) -> bool:
        return self.bridge.available

    def build_graph(self, target_path: str | Path | None = None) -> dict[str, Any]:
        """Run graphify extraction and build the knowledge graph."""
        result = self.bridge.extract(target_path=target_path)
        self._graph_built = True
        return result

    def load_existing_graph(self, graph_path: str | Path | None = None) -> bool:
        """Load an existing graph.json file."""
        data = self.bridge.load_graph(graph_path=graph_path)
        self._graph_built = data is not None
        return self._graph_built

    def store(self, claim: MemoryClaim) -> None:
        self._store.store(claim)

    def get(self, fact_id: str) -> MemoryClaim | None:
        return self._store.get(fact_id)

    def search(self, query: str, limit: int = 10) -> list[MemorySearchResult]:
        base_results = self._store.search(query, limit=limit * 2)
        if not base_results or not self._graph_built:
            return base_results[:limit] if base_results else []

        graph_nodes = self.bridge.search_nodes(query, limit=10)
        if not graph_nodes:
            return base_results[:limit]

        graph_labels: set[str] = set()
        for n in graph_nodes:
            label = str(n.get("label", n.get("name", n.get("id", "")))).lower()
            if label:
                graph_labels.update(label.split("_"))

        if not graph_labels:
            return base_results[:limit]

        query_words = set(query.lower().split())
        for r in base_results:
            claim_lower = r.claim.lower()
            overlap = len(graph_labels & set(claim_lower.split()))
            if overlap > 0:
                boost = min(0.3, overlap * 0.05)
                r.similarity = min(r.similarity + boost, 1.0)

        base_results.sort(key=lambda r: r.similarity, reverse=True)
        return base_results[:limit]

    def list_all(self) -> list[MemoryClaim]:
        return self._store.list_all()

    def delete(self, fact_id: str) -> bool:
        return self._store.delete(fact_id)

    def count(self) -> int:
        return self._store.count()

    def gc(self, before_timestamp: str) -> int:
        return self._store.gc(before_timestamp)

    def query_subgraph(self, query: str, depth: int = 2) -> dict[str, Any]:
        """Query the graphify knowledge graph for a subgraph around a topic."""
        return self.bridge.query_subgraph(query, depth=depth)

    def import_edges_to_graph(self, knowledge_graph) -> int:
        """Import graphify edges into a KnowledgeGraph instance."""
        return self.bridge.import_to_knowledge_graph(knowledge_graph)

    def get_graph_nodes(self) -> list[dict[str, Any]]:
        return self.bridge.get_nodes()

    def get_graph_edges(self) -> list[dict[str, Any]]:
        return self.bridge.get_edges()

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

from hermes_prime.memory.graph import KnowledgeGraph


class GraphifyBridge:
    """Bridge between the graphify knowledge graph tool and Hermes Prime.

    Wraps graphify's Python API to:
    - Run codebase extraction and graph building
    - Load graphify-out/graph.json
    - Query the graph for relationships
    - Import nodes/edges into our KnowledgeGraph
    """

    def __init__(self, workspace_path: str | Path | None = None) -> None:
        self.workspace_path = (
            Path(workspace_path).resolve() if workspace_path else Path.cwd().resolve()
        )
        self.graph_out_dir = self.workspace_path / "graphify-out"
        self.graph_path = self.graph_out_dir / "graph.json"
        self._graph: Any | None = None

    @property
    def available(self) -> bool:
        return importlib.util.find_spec("graphify") is not None

    def extract(self, target_path: str | Path | None = None) -> dict[str, Any]:
        """Run graphify extract-build pipeline on the workspace.

        Returns the graph structure as a dict with nodes/edges.
        """
        if not self.available:
            raise RuntimeError("graphify is not installed. Install with: pip install graphifyy")

        import graphify

        target = Path(target_path).resolve() if target_path else self.workspace_path
        if not target.is_dir():
            raise ValueError(f"Target path does not exist: {target}")

        files = graphify.collect_files(str(target))
        extracted = graphify.extract(files, root=str(target))
        G = graphify.build(extracted["nodes"], extracted["edges"])
        self._graph = G
        return {"nodes": extracted.get("nodes", []), "edges": extracted.get("edges", [])}

    def load_graph(self, graph_path: str | Path | None = None) -> dict[str, Any] | None:
        """Load a graphify graph.json file."""
        path = Path(graph_path) if graph_path else self.graph_path
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self._graph = data
        return data

    def get_nodes(self) -> list[dict[str, Any]]:
        """Get all nodes from the loaded graph."""
        if not self._graph:
            return []
        nodes = self._graph.get("nodes") or self._graph.get("elements", {}).get("nodes", [])
        if not nodes and isinstance(self._graph, dict):
            for key in ("nodes",):
                if key in self._graph:
                    nodes = self._graph[key]
                    break
        return nodes

    def get_edges(self) -> list[dict[str, Any]]:
        """Get all edges from the loaded graph."""
        if not self._graph:
            return []
        edges = (
            self._graph.get("edges")
            or self._graph.get("links")
            or self._graph.get("elements", {}).get("edges", [])
        )
        return edges

    def search_nodes(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Search graph nodes by label/name matching the query."""
        nodes = self.get_nodes()
        query_lower = query.lower()
        words = query_lower.split()

        scored: list[tuple[dict[str, Any], int]] = []
        for node in nodes:
            label = str(node.get("label", node.get("name", node.get("id", "")))).lower()
            score = sum(1 for w in words if w in label)
            if score > 0:
                scored.append((node, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [n for n, _ in scored[:limit]]

    def get_neighbors(self, node_id: str) -> list[dict[str, Any]]:
        """Get neighbors of a node from the graph edges."""
        edges = self.get_edges()
        neighbors: list[dict[str, Any]] = []
        seen: set[str] = set()

        for edge in edges:
            source = edge.get("source") or edge.get("from") or edge.get("u", "")
            target = edge.get("target") or edge.get("to") or edge.get("v", "")
            rel = edge.get("relation") or edge.get("label", "related_to")

            if source == node_id and target not in seen:
                seen.add(target)
                neighbors.append({"node_id": target, "relation": rel, "direction": "outgoing"})
            elif target == node_id and source not in seen:
                seen.add(source)
                neighbors.append({"node_id": source, "relation": rel, "direction": "incoming"})

        return neighbors

    def import_to_knowledge_graph(self, kg: KnowledgeGraph) -> int:
        """Import graphify edges into our KnowledgeGraph as causal parent relationships.

        Returns the number of edges imported.
        """
        edges = self.get_edges()
        count = 0
        for edge in edges:
            source = edge.get("source") or edge.get("from") or edge.get("u", "")
            target = edge.get("target") or edge.get("to") or edge.get("v", "")
            if source and target and source != target:
                try:
                    kg.add_edge(source, target)
                    count += 1
                except (ValueError, KeyError):
                    continue
        return count

    def query_subgraph(self, query: str, depth: int = 2) -> dict[str, Any]:
        """Extract a subgraph centered on nodes matching the query.

        Returns BFS-expanded subgraph up to `depth` hops.
        """
        matched = self.search_nodes(query, limit=5)
        if not matched:
            return {"nodes": [], "edges": []}

        center_ids = {n.get("id") or n.get("name", "") for n in matched}
        all_ids: set[str] = set(center_ids)
        frontier: set[str] = set(center_ids)
        edges = self.get_edges()

        sub_edges: list[dict[str, Any]] = []
        for _ in range(depth):
            new_ids: set[str] = set()
            for edge in edges:
                source = edge.get("source") or edge.get("from") or edge.get("u", "")
                target = edge.get("target") or edge.get("to") or edge.get("v", "")
                if source in frontier and target not in all_ids:
                    new_ids.add(target)
                    sub_edges.append(edge)
                elif target in frontier and source not in all_ids:
                    new_ids.add(source)
                    sub_edges.append(edge)
            all_ids.update(new_ids)
            frontier = new_ids
            if not frontier:
                break

        sub_nodes = [n for n in self.get_nodes() if n.get("id") or n.get("name", "") in all_ids]
        return {"nodes": sub_nodes, "edges": sub_edges}

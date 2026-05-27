from __future__ import annotations

from typing import Any

from hermes_prime.brain.neural_graph import NeuralGraph, BrainNode, NodeType
from hermes_prime.brain.linker import AutoLinker


class BrainMaintenanceAgent:
    """Daily maintenance agent that traverses the brain, removes bloat, and consolidates.

    Runs these operations:
    1. Prune low-value nodes (low confidence, low access, old)
    2. Merge duplicate/similar nodes
    3. Consolidate orphaned nodes into summaries
    4. Prune dead edges
    5. Report brain health metrics
    """

    def __init__(
        self,
        graph: NeuralGraph,
        linker: AutoLinker | None = None,
    ):
        self.graph = graph
        self.linker = linker or AutoLinker(graph)

    def run_maintenance(
        self,
        dry_run: bool = False,
        max_age_days: float = 90.0,
        min_confidence: float = 0.2,
        min_access: int = 0,
    ) -> dict[str, Any]:
        """Run full maintenance cycle. Returns report of actions taken."""
        report: dict[str, Any] = {
            "pruned_nodes": 0,
            "merged_nodes": 0,
            "consolidated_orphans": 0,
            "pruned_edges": 0,
            "errors": [],
        }

        prune_result = self._prune_low_value_nodes(
            dry_run,
            max_age_days,
            min_confidence,
            min_access,
        )
        report["pruned_nodes"] = prune_result

        merge_result = self._merge_duplicates(dry_run)
        report["merged_nodes"] = merge_result

        consolidate_result = self._consolidate_orphans(dry_run)
        report["consolidated_orphans"] = consolidate_result

        edge_result = self._prune_dead_edges(dry_run)
        report["pruned_edges"] = edge_result

        report["remaining_nodes"] = self.graph.count_nodes()
        report["remaining_edges"] = self.graph.count_edges()
        report["dry_run"] = dry_run

        return report

    def _prune_low_value_nodes(
        self,
        dry_run: bool,
        max_age_days: float,
        min_confidence: float,
        min_access: int,
    ) -> int:
        """Remove nodes that are old, rarely accessed, and low confidence."""
        pruned = 0
        nodes = self.graph.get_all_nodes()
        for node in nodes:
            if node.node_type in (NodeType.DECISION, NodeType.PATTERN):
                if node.confidence >= 0.6:
                    continue
            if node.confidence >= min_confidence and node.access_count >= min_access:
                continue
            if node.age_days < max_age_days:
                continue
            if not dry_run:
                try:
                    self.graph.delete_node(node.node_id)
                except Exception:
                    pass
            pruned += 1
        return pruned

    def _merge_duplicates(self, dry_run: bool) -> int:
        """Merge nodes with similar titles and content."""
        nodes = self.graph.get_all_nodes()
        merged = 0
        visited: set[str] = set()

        for i, a in enumerate(nodes):
            if a.node_id in visited:
                continue
            for b in nodes[i + 1 :]:
                if b.node_id in visited:
                    continue
                if a.node_type != b.node_type:
                    continue
                similarity = self._compute_similarity(a, b)
                if similarity < 0.7:
                    continue
                if not dry_run:
                    try:
                        keep_id = a.node_id if a.confidence >= b.confidence else b.node_id
                        remove_id = b.node_id if keep_id == a.node_id else a.node_id

                        keep_title = a.title if a.node_id == keep_id else b.title
                        merged_content = f"{a.content}\n\n---\n\n{b.content}"
                        keep_tags = list(set(a.tags + b.tags))
                        merged_confidence = max(a.confidence, b.confidence)

                        self.graph.update_node(
                            keep_id,
                            title=keep_title,
                            content=merged_content,
                            tags=keep_tags,
                            confidence=merged_confidence,
                        )

                        edges_a = self.graph.get_node_edges(remove_id)
                        for edge in edges_a:
                            other_id = (
                                edge.target_id if edge.source_id == remove_id else edge.source_id
                            )
                            if other_id != keep_id:
                                self.graph.add_edge(
                                    source_id=keep_id,
                                    target_id=other_id,
                                    edge_type=edge.edge_type,
                                    weight=edge.weight,
                                )

                        self.graph.delete_node(remove_id)
                        visited.add(remove_id)
                        merged += 1
                    except Exception:
                        pass
            visited.add(a.node_id)

        return merged

    def _consolidate_orphans(self, dry_run: bool) -> int:
        """Link orphaned nodes (no edges) to related nodes."""
        consolidated = 0
        nodes = self.graph.get_all_nodes()
        for node in nodes:
            edges = self.graph.get_node_edges(node.node_id)
            if len(edges) > 0:
                continue
            if not dry_run:
                links = self.linker.link_new_node(node.node_id)
                if links > 0:
                    consolidated += 1
        return consolidated

    def _prune_dead_edges(self, dry_run: bool) -> int:
        """Remove edges that reference deleted nodes or have very low weight."""
        pruned = 0
        edges = self.graph.get_all_edges()
        for edge in edges:
            source = self.graph.get_node(edge.source_id)
            target = self.graph.get_node(edge.target_id)
            if source is None or target is None:
                pruned += 1
                if not dry_run:
                    try:
                        c = self.graph._conn
                        c.execute("DELETE FROM brain_edges WHERE edge_id = ?", (edge.edge_id,))
                        c.commit()
                    except Exception:
                        pass
                continue
            if edge.weight < 0.1:
                pruned += 1
                if not dry_run:
                    try:
                        c = self.graph._conn
                        c.execute("DELETE FROM brain_edges WHERE edge_id = ?", (edge.edge_id,))
                        c.commit()
                    except Exception:
                        pass
        return pruned

    def _compute_similarity(self, a: BrainNode, b: BrainNode) -> float:
        import re

        def tokenize(text: str) -> set[str]:
            words = re.findall(r"[a-zA-Z_]\w{2,}", text.lower())
            return {w for w in words if len(w) > 2}

        a_tokens = tokenize(f"{a.title} {a.content}")
        b_tokens = tokenize(f"{b.title} {b.content}")
        if not a_tokens or not b_tokens:
            return 0.0
        intersection = a_tokens & b_tokens
        union = a_tokens | b_tokens

        tag_overlap = len(set(a.tags) & set(b.tags))
        tag_bonus = 0.1 * tag_overlap

        return min(len(intersection) / len(union) + tag_bonus, 1.0)

    def get_health_report(self) -> dict[str, Any]:
        """Get brain health metrics for monitoring."""
        metrics = self.graph.get_metrics()
        all_nodes = self.graph.get_all_nodes()

        orphaned = 0
        for node in all_nodes:
            edges = self.graph.get_node_edges(node.node_id)
            if len(edges) == 0:
                orphaned += 1

        low_conf = sum(1 for n in all_nodes if n.confidence < 0.3)
        old_unused = sum(1 for n in all_nodes if n.age_days > 30 and n.access_count == 0)

        unsolved = sum(
            1
            for n in all_nodes
            if n.node_type == NodeType.PROBLEM and not n.metadata.get("solved", False)
        )

        return {
            "total_nodes": metrics["total_nodes"],
            "total_edges": metrics["total_edges"],
            "orphaned_nodes": orphaned,
            "low_confidence_nodes": low_conf,
            "old_unused_nodes": old_unused,
            "unsolved_problems": unsolved,
            "by_type": metrics["by_node_type"],
            "health_score": self._compute_health_score(
                metrics["total_nodes"],
                orphaned,
                low_conf,
                old_unused,
            ),
        }

    def _compute_health_score(
        self,
        total: int,
        orphaned: int,
        low_conf: int,
        old_unused: int,
    ) -> float:
        if total == 0:
            return 1.0
        score = 1.0
        score -= 0.3 * (orphaned / max(total, 1))
        score -= 0.3 * (low_conf / max(total, 1))
        score -= 0.2 * (old_unused / max(total, 1))
        return max(0.0, round(score, 3))

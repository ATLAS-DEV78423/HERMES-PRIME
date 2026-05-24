from __future__ import annotations

import re
from collections import Counter

from hermes_prime.brain.neural_graph import NeuralGraph, BrainNode, NodeType, EdgeType


class AutoLinker:
    """Automatically creates links between related brain nodes.

    Uses keyword overlap, tag matching, and title/content similarity
    to connect nodes into an Obsidian-like neural network.
    """

    def __init__(self, graph: NeuralGraph):
        self.graph = graph
        self._stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "shall", "can",
            "to", "of", "in", "for", "on", "with", "at", "by", "from",
            "as", "into", "through", "during", "before", "after", "above",
            "below", "between", "out", "off", "over", "under", "again",
            "further", "then", "once", "here", "there", "when", "where",
            "why", "how", "all", "each", "every", "both", "few", "more",
            "most", "other", "some", "such", "no", "nor", "not", "only",
            "own", "same", "so", "than", "too", "very", "just", "it",
        }

    def link_new_node(self, node_id: str) -> int:
        """Scan all existing nodes and create links to the new node where relevant.

        Returns the number of links created.
        """
        new_node = self.graph.get_node(node_id)
        if not new_node:
            return 0

        existing = self.graph.get_all_nodes()
        existing = [n for n in existing if n.node_id != node_id]

        links_created = 0
        new_tokens = self._extract_keywords(f"{new_node.title} {new_node.content}")

        for existing_node in existing:
            existing_tokens = self._extract_keywords(f"{existing_node.title} {existing_node.content}")
            overlap = new_tokens & existing_tokens
            if len(overlap) < 2:
                continue

            score = len(overlap) / max(len(new_tokens | existing_tokens), 1)
            if score < 0.1:
                continue

            tag_overlap = set(new_node.tags) & set(existing_node.tags)
            tag_boost = 0.2 * len(tag_overlap)
            final_score = min(score + tag_boost, 1.0)

            edge_type = self._infer_edge_type(new_node, existing_node, overlap)
            existing_edges = self.graph.get_node_edges(node_id)
            already = any(
                e.source_id == existing_node.node_id or e.target_id == existing_node.node_id
                for e in existing_edges
            )
            if not already:
                self.graph.add_edge(
                    source_id=node_id,
                    target_id=existing_node.node_id,
                    edge_type=edge_type,
                    weight=final_score,
                )
                links_created += 1

        return links_created

    def link_problem_to_solution(
        self,
        problem_id: str,
        solution_id: str,
        outcome: str = "unknown",
    ) -> bool:
        """Create a solves edge between a problem and solution node."""
        edge = self.graph.add_edge(
            source_id=solution_id,
            target_id=problem_id,
            edge_type=EdgeType.SOLVES,
            weight=1.0 if outcome == "success" else 0.5,
            metadata={"outcome": outcome},
        )
        return edge is not None

    def find_related(self, node_id: str, min_weight: float = 0.3, limit: int = 10) -> list[BrainNode]:
        """Find nodes related to the given node via keyword overlap."""
        node = self.graph.get_node(node_id)
        if not node:
            return []
        all_nodes = self.graph.get_all_nodes()
        all_nodes = [n for n in all_nodes if n.node_id != node_id]
        node_tokens = self._extract_keywords(f"{node.title} {node.content}")
        node_tags = set(node.tags)

        scored: list[tuple[BrainNode, float]] = []
        for candidate in all_nodes:
            cand_tokens = self._extract_keywords(f"{candidate.title} {candidate.content}")
            overlap = node_tokens & cand_tokens
            if len(overlap) < 2:
                continue
            score = len(overlap) / max(len(node_tokens | cand_tokens), 1)
            tag_boost = 0.2 * len(node_tags & set(candidate.tags))
            final = min(score + tag_boost, 1.0)
            if final >= min_weight:
                scored.append((candidate, final))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [n for n, _ in scored[:limit]]

    def suggest_tags(self, content: str) -> list[str]:
        """Suggest tags for new content based on existing brain vocabulary."""
        tokens = self._extract_keywords(content)
        all_nodes = self.graph.get_all_nodes()
        tag_counter: Counter = Counter()
        for token in tokens:
            for node in all_nodes:
                node_tokens = self._extract_keywords(f"{node.title} {node.content}")
                if token in node_tokens:
                    for tag in node.tags:
                        tag_counter[tag] += 1
                if token.lower() in [t.lower() for t in node.tags]:
                    tag_counter[token] += 3
        return [tag for tag, _ in tag_counter.most_common(10)]

    def _extract_keywords(self, text: str) -> set[str]:
        words = re.findall(r"[a-zA-Z_]\w{2,}", text.lower())
        return {w for w in words if w not in self._stop_words}

    def _infer_edge_type(self, a: BrainNode, b: BrainNode, overlap: set[str]) -> EdgeType:
        if a.node_type == NodeType.PROBLEM and b.node_type == NodeType.SOLUTION:
            return EdgeType.SOLVES
        if a.node_type == NodeType.SOLUTION and b.node_type == NodeType.PROBLEM:
            return EdgeType.SOLVES
        if a.node_type == NodeType.TOPIC and b.node_type == NodeType.TOPIC:
            return EdgeType.EXTENDS
        if a.node_type == NodeType.DECISION and b.node_type in (NodeType.PROBLEM, NodeType.OBSERVATION):
            return EdgeType.PRODUCES
        return EdgeType.RELATES_TO

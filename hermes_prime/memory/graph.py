from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
from typing import Optional


class KnowledgeGraph:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self._edges: dict[str, str] = {}
        self._children: dict[str, list[str]] = defaultdict(list)
        self._db_path: str | None = None
        if db_path is not None:
            self._db_path = str(Path(db_path).expanduser().resolve())
            self._init_db()

    def _init_db(self) -> None:
        import sqlite3
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_graph (
                child_id TEXT PRIMARY KEY,
                parent_id TEXT NOT NULL
            )
        """)
        self._conn.commit()
        self._load_from_db()

    def _load_from_db(self) -> None:
        import sqlite3
        for row in self._conn.execute("SELECT child_id, parent_id FROM memory_graph"):
            child, parent = row
            self._edges[child] = parent
            self._children[parent].append(child)

    def _persist_edge(self, child_id: str, parent_id: str) -> None:
        if self._db_path is None:
            return
        self._conn.execute(
            "INSERT OR REPLACE INTO memory_graph (child_id, parent_id) VALUES (?, ?)",
            (child_id, parent_id),
        )
        self._conn.commit()

    def _persist_remove(self, node_id: str) -> None:
        if self._db_path is None:
            return
        self._conn.execute(
            "DELETE FROM memory_graph WHERE child_id = ? OR parent_id = ?",
            (node_id, node_id),
        )
        self._conn.commit()

    def add_edge(self, child_id: str, parent_id: str) -> None:
        if child_id == parent_id:
            raise ValueError("cannot add self-referential edge")
        if parent_id in self._ancestors_set(parent_id):
            raise ValueError("adding this edge would create a cycle")
        self._edges[child_id] = parent_id
        self._children[parent_id].append(child_id)
        self._persist_edge(child_id, parent_id)

    def _ancestors_set(self, fact_id: str) -> set[str]:
        ancestors: set[str] = set()
        current = fact_id
        while current in self._edges:
            parent = self._edges[current]
            if parent in ancestors:
                break
            ancestors.add(parent)
            current = parent
        return ancestors

    def get_lineage(self, fact_id: str) -> list[str]:
        lineage: list[str] = []
        current = fact_id
        while current in self._edges:
            parent = self._edges[current]
            lineage.append(parent)
            current = parent
        return lineage

    def get_ancestors(self, fact_id: str) -> list[str]:
        return self.get_lineage(fact_id)

    def get_descendants(self, fact_id: str) -> list[str]:
        result: list[str] = []
        queue: deque[str] = deque([fact_id])
        while queue:
            current = queue.popleft()
            for child in self._children.get(current, []):
                result.append(child)
                queue.append(child)
        return result

    def get_path(self, from_id: str, to_id: str) -> list[str] | None:
        if from_id == to_id:
            return [from_id]
        visited: set[str] = set()
        queue: deque[tuple[str, list[str]]] = deque([(from_id, [from_id])])
        while queue:
            current, path = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            for child in self._children.get(current, []):
                new_path = path + [child]
                if child == to_id:
                    return new_path
                queue.append((child, new_path))
        return None

    def remove_node(self, fact_id: str) -> None:
        if fact_id in self._edges:
            parent = self._edges.pop(fact_id)
            if parent in self._children and fact_id in self._children[parent]:
                self._children[parent].remove(fact_id)
        if fact_id in self._children:
            for child in list(self._children[fact_id]):
                self._edges.pop(child, None)
            del self._children[fact_id]
        self._persist_remove(fact_id)

    def has_node(self, fact_id: str) -> bool:
        return fact_id in self._edges or fact_id in self._children

    def edge_count(self) -> int:
        return len(self._edges)

    def clear(self) -> None:
        self._edges.clear()
        self._children.clear()
        if self._db_path is not None:
            self._conn.execute("DELETE FROM memory_graph")
            self._conn.commit()

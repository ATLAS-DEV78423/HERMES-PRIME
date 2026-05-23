from __future__ import annotations

from typing import TYPE_CHECKING

from ..contracts import AgentStatus

if TYPE_CHECKING:
    from .mesh import AgentMesh


class RecursionWatchdog:
    def __init__(self, mesh: AgentMesh, max_depth: int | None = None) -> None:
        self._mesh = mesh
        self._max_depth = max_depth

    def check_spawn(self, parent_id: str | None) -> int:
        if parent_id is None:
            return 0
        parent = self._mesh.get(parent_id)
        if parent is None:
            return 0
        child_depth = parent.depth + 1
        limit = self._max_depth if self._max_depth is not None else self._mesh.max_depth
        if child_depth > limit:
            from .mesh import DepthLimitError
            raise DepthLimitError(
                f"RecursionWatchdog: spawn at depth {child_depth} exceeds limit {limit} "
                f"(parent={parent_id})"
            )
        return child_depth

    def prune_overdepth(self, max_depth: int | None = None) -> int:
        limit = max_depth if max_depth is not None else self._mesh.max_depth
        pruned = 0
        for node in self._mesh.list_all():
            if node.depth > limit and node.status in (
                AgentStatus.PENDING,
                AgentStatus.RUNNING,
                AgentStatus.IDLE,
            ):
                self._mesh.transition(node.agent_id, AgentStatus.KILLED)
                pruned += 1
        return pruned

    def runaway_chain_detected(self, agent_id: str, max_consecutive_depth: int = 10) -> bool:
        nodes = self._mesh.subgraph(agent_id)
        if not nodes:
            return False
        max_depth = max(n.depth for n in nodes)
        return max_depth >= max_consecutive_depth

    def terminate_chain(self, agent_id: str) -> int:
        killed = 0
        for node in self._mesh.subgraph(agent_id):
            if node.status in (AgentStatus.PENDING, AgentStatus.RUNNING):
                self._mesh.transition(node.agent_id, AgentStatus.KILLED)
                killed += 1
        return killed

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable

from ..contracts import (
    ActionType,
    AgentSpawnRequest,
    AgentStatus,
    CapabilityToken,
    RiskTier,
)
from ..utils import new_urn_uuid
from .mesh import AgentMesh, DepthLimitError
from .watchdog import RecursionWatchdog

logger = logging.getLogger(__name__)


class DispatchError(Exception):
    pass


AgentRunner = Callable[[str, str, CapabilityToken], dict[str, Any]]


class Dispatcher:
    def __init__(
        self,
        mesh: AgentMesh,
        watchdog: RecursionWatchdog,
        runner: AgentRunner | None = None,
        default_risk_tier_ceiling: RiskTier = RiskTier.T2,
    ) -> None:
        self._mesh = mesh
        self._watchdog = watchdog
        self._runner = runner
        self._default_risk_ceiling = default_risk_tier_ceiling

    def spawn(
        self,
        request: AgentSpawnRequest,
        spawned_by: str | None = None,
        runner: AgentRunner | None = None,
    ) -> str:
        try:
            self._watchdog.check_spawn(request.parent_agent_id)
        except DepthLimitError:
            raise

        scope = request.scope
        intent_root = new_urn_uuid()

        actions = request.capability_actions or [
            ActionType.FILESYSTEM_READ,
            ActionType.MEMORY_WRITE,
        ]

        now = datetime.now(timezone.utc).isoformat()
        cap_token = CapabilityToken(
            token_id=new_urn_uuid(),
            capability="agent.spawn",
            scope=scope,
            actions=[a.value for a in actions],
            risk_tier_ceiling=request.risk_tier_ceiling,
            expires_at=now,
            intent_root=intent_root,
            issued_to=spawned_by or "system",
            issued_at=now,
            nonce=new_urn_uuid(),
            signature="temporary",
        )

        node = self._mesh.register_agent(
            task_description=request.task_description,
            capability_scope=scope,
            capability_token=cap_token.token_id,
            parent_id=request.parent_agent_id,
            intent_root=intent_root,
            spawned_by=spawned_by,
        )

        spawner_id = request.parent_agent_id or new_urn_uuid()
        self._mesh.attach_attestation(
            agent_id=node.agent_id,
            spawned_by=spawner_id,
            intent_root=intent_root,
            capability_token_id=cap_token.token_id,
        )

        self._mesh.transition(node.agent_id, AgentStatus.RUNNING)

        effective_runner = runner or self._runner
        if effective_runner:
            try:
                result = effective_runner(request.task_description, scope, cap_token)
                self._mesh.store_result(node.agent_id, result)
                self._mesh.transition(node.agent_id, AgentStatus.COMPLETED)
            except Exception as exc:
                logger.exception("Agent %s failed: %s", node.agent_id, exc)
                self._mesh.store_result(node.agent_id, {"error": str(exc)})
                self._mesh.transition(node.agent_id, AgentStatus.FAILED)

        return node.agent_id

    def kill(self, agent_id: str) -> None:
        node = self._mesh.get(agent_id)
        if not node:
            raise DispatchError(f"Agent {agent_id} not found")
        killed = self._watchdog.terminate_chain(agent_id)
        logger.info("Killed agent %s and %d descendants", agent_id, killed - 1 if killed else 0)

    def list_agents(
        self, status: AgentStatus | None = None
    ) -> list[dict[str, Any]]:
        return [n.to_dict() for n in self._mesh.list_all(status=status)]

    def get_status(self, agent_id: str) -> dict[str, Any] | None:
        node = self._mesh.get(agent_id)
        return node.to_dict() if node else None

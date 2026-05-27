from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from hermes_prime.contracts import ActionProposal, ActionType, RiskTier
from hermes_prime.utils import new_urn_uuid, utc_now_iso


class GovernedToolDispatcher:
    """Dispatches tool calls through Sentinel governance before execution."""

    def __init__(
        self,
        sentinel: Any,
        vault: Any,
        trust_store: Any = None,
        workspace_root: str | Path = ".",
    ):
        self._sentinel = sentinel
        self._vault = vault
        self._trust_store = trust_store
        self._workspace_root = str(Path(workspace_root).resolve())

    def dispatch(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        tool_fn: Callable[..., str],
        risk_tier: RiskTier = RiskTier.T1,
    ) -> str:
        action_type = self._map_tool_to_action(tool_name)

        intent = self._vault.register_intent_root(
            scope=self._workspace_root,
            issued_to=f"hermes:agent:{tool_name}",
        )
        self._sentinel.register_intent_root(intent)

        token = self._vault.mint_capability(
            capability=f"tool:{tool_name}",
            scope=self._workspace_root,
            actions=[action_type.value],
            risk_tier_ceiling=risk_tier,
            intent_root=intent.intent_root,
            issued_to=f"hermes:agent:{tool_name}",
        )

        proposal = ActionProposal(
            action_id=new_urn_uuid(),
            action_type=action_type,
            scope=self._workspace_root,
            risk_tier=risk_tier,
            intent_root=intent.intent_root,
            capability=token.capability,
            proposed_at=utc_now_iso(),
            parameters=arguments,
        )

        evaluation = self._sentinel.evaluate(proposal, capability=token)
        decision = evaluation.decision if hasattr(evaluation, "decision") else evaluation

        if not decision.permitted:
            return f"Action rejected by Sentinel: {decision.denial_reason}"

        result = tool_fn(**arguments)

        if self._trust_store:
            from hermes_prime.contracts import AuditTrace

            trace = AuditTrace(
                trace_id=new_urn_uuid(),
                trace_type="governed_tool_dispatch",
                created_at=utc_now_iso(),
                workspace_root=self._workspace_root,
                intent_root=intent.intent_root,
                action=proposal.to_dict(),
                decision=decision.to_dict(),
                mutation={"tool": tool_name, "arguments": arguments, "result": result},
                summary=f"Governed tool: {tool_name} executed",
            )
            self._trust_store.store_audit_trace(trace)

        return result

    def _map_tool_to_action(self, tool_name: str) -> ActionType:
        mapping = {
            "web_search": ActionType.FILESYSTEM_READ,
            "web_fetch": ActionType.FILESYSTEM_READ,
            "web_extract": ActionType.FILESYSTEM_READ,
            "read_file": ActionType.FILESYSTEM_READ,
            "write_file": ActionType.FILESYSTEM_WRITE,
            "patch": ActionType.FILESYSTEM_WRITE,
            "terminal": ActionType.EXECUTION_COMMAND,
            "execute_code": ActionType.EXECUTION_COMMAND,
            "delegate_task": ActionType.AGENT_SPAWN,
            "browser_navigate": ActionType.FILESYSTEM_READ,
            "browser_click": ActionType.FILESYSTEM_WRITE,
            "memory": ActionType.MEMORY_WRITE,
            "skills_list": ActionType.FILESYSTEM_READ,
            "skill_manage": ActionType.CONFIG_WRITE,
            "cronjob": ActionType.SCHEDULING,
            "kanban_create": ActionType.FILESYSTEM_WRITE,
            "kanban_list": ActionType.FILESYSTEM_READ,
            "todo": ActionType.FILESYSTEM_WRITE,
        }
        return mapping.get(tool_name, ActionType.FILESYSTEM_READ)

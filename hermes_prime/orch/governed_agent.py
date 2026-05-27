"""Governed agent wrapper — monkey-patches upstream handle_function_call
to route every tool execution through Sentinel policy evaluation."""

from __future__ import annotations

import json
from typing import Any, Optional

try:
    import run_agent as upstream_agent
except ImportError:
    upstream_agent = None  # type: ignore

from hermes_prime.contracts import ActionProposal, ActionType, RiskTier
from hermes_prime.secrets import get_signer
from hermes_prime.signing import HMACSigner
from hermes_prime.utils import new_urn_uuid, utc_now_iso


class GovernedAgentWrapper:
    def __init__(
        self,
        sentinel: Any,
        vault: Any,
        forge: Any,
        trust_store: Any,
        workspace_root: str = ".",
        signer: Optional[HMACSigner] = None,
    ):
        self._sentinel = sentinel
        self._vault = vault
        self._forge = forge
        self._trust_store = trust_store
        self._workspace_root = workspace_root
        self._signer = signer or get_signer("governed-agent")

    def create_governed_agent(self, **kwargs):
        self._patch_handle_function_call()
        if upstream_agent is None:
            raise RuntimeError(
                "upstream_agent (run_agent) is not available. "
                "Ensure external/hermes-agent is on sys.path or install the package."
            )
        return upstream_agent.AIAgent(**kwargs)

    def _patch_handle_function_call(self) -> None:
        if upstream_agent is None:
            raise RuntimeError(
                "upstream_agent (run_agent) is not available. "
                "Ensure external/hermes-agent is on sys.path or install the package."
            )
        original = upstream_agent.handle_function_call

        def governed(
            function_name: str,
            function_args: dict[str, Any],
            **kwargs,
        ) -> str:
            decision = self._evaluate_action(function_name, function_args)
            if not decision.get("permitted", False):
                return json.dumps(
                    {
                        "error": f"Action rejected by Sentinel: {decision.get('denial_reason', 'unknown')}",
                    }
                )
            result = original(function_name, function_args, **kwargs)
            self._post_execution_audit(function_name, function_args, decision, result)
            return result

        upstream_agent.handle_function_call = governed

    def _evaluate_action(self, function_name: str, function_args: dict) -> dict:
        intent_root = new_urn_uuid()
        action_id = new_urn_uuid()
        action_type = self._map_tool_to_action_type(function_name)
        token = self._vault.mint_capability(
            capability=f"tool:{function_name}",
            scope=self._workspace_root,
            actions=[action_type.value],
            risk_tier_ceiling=RiskTier.T2,
            intent_root=intent_root,
            issued_to="hermes:governed-agent",
        )
        token_cap = token.token_id if hasattr(token, "token_id") else str(token)
        proposal = ActionProposal(
            action_id=action_id,
            action_type=action_type,
            scope=self._workspace_root,
            risk_tier=RiskTier.T2,
            intent_root=intent_root,
            capability=token_cap,
            proposed_at=utc_now_iso(),
            parameters=function_args,
        )
        evaluation = self._sentinel.evaluate(proposal, capability=token)
        if hasattr(evaluation, "decision"):
            return evaluation.decision.to_dict()
        return {"permitted": True, "blocking_layer": None, "denial_reason": None}

    def _map_tool_to_action_type(self, tool_name: str) -> ActionType:
        mapping = {
            "read": ActionType.FILESYSTEM_READ,
            "read_file": ActionType.FILESYSTEM_READ,
            "write": ActionType.FILESYSTEM_WRITE,
            "write_file": ActionType.FILESYSTEM_WRITE,
            "patch": ActionType.FILESYSTEM_WRITE,
            "edit": ActionType.FILESYSTEM_WRITE,
            "execute": ActionType.EXECUTION_COMMAND,
            "execute_code": ActionType.EXECUTION_COMMAND,
            "terminal": ActionType.EXECUTION_COMMAND,
            "delegate_task": ActionType.AGENT_SPAWN,
            "web_search": ActionType.FILESYSTEM_READ,
            "web_fetch": ActionType.FILESYSTEM_READ,
        }
        return mapping.get(tool_name, ActionType.FILESYSTEM_READ)

    def _post_execution_audit(self, function_name, function_args, decision, result) -> None:
        if not self._trust_store:
            return
        trace_id = new_urn_uuid()
        trace = {
            "trace_id": trace_id,
            "trace_type": "governed_tool_call",
            "created_at": utc_now_iso(),
            "workspace_root": self._workspace_root,
            "action": {
                "tool": function_name,
                "args": function_args,
                "decision": decision,
                "result": result,
            },
        }
        self._trust_store.store_audit_trace(trace)

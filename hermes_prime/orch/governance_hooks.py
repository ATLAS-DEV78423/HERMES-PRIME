"""Sentinel governance hooks for upstream CLI commands (cron, tools, skills)."""

from __future__ import annotations

from typing import Any, Callable

from hermes_prime.contracts import ActionProposal, ActionType, RiskTier
from hermes_prime.secrets import get_signer
from hermes_prime.signing import HMACSigner
from hermes_prime.utils import new_urn_uuid, utc_now_iso


class GovernanceHooks:
    """Wraps upstream CLI command functions with Sentinel evaluation.

    Usage:
        hooks = GovernanceHooks(sentinel, vault, trust_store, workspace_root)
        wrapped_add_job = hooks.wrap("cron", upstream_cron_module.add_job)
    """

    def __init__(
        self,
        sentinel: Any,
        vault: Any,
        trust_store: Any,
        workspace_root: str,
        signer: HMACSigner | None = None,
    ):
        self._sentinel = sentinel
        self._vault = vault
        self._trust_store = trust_store
        self._workspace_root = workspace_root
        self._signer = signer or get_signer("governance-hooks")

    def wrap(self, action_type_label: str, func: Callable) -> Callable:
        """Wrap a function with Sentinel evaluation.

        Args:
            action_type_label: One of "cron", "tools", "skills", "model".
            func: The upstream function to wrap.

        Returns:
            Wrapped function that evaluates through Sentinel before executing.
        """
        action_type = self._label_to_action_type(action_type_label)

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            intent_root = new_urn_uuid()
            action_id = new_urn_uuid()
            params = {"args": str(args), "kwargs": str(kwargs)}
            proposal = ActionProposal(
                action_id=action_id,
                intent_root=intent_root,
                action_type=action_type,
                scope=self._workspace_root,
                parameters=params,
                risk_tier=RiskTier.T2,
                capability=f"cmd:{action_type_label}",
                proposed_at=utc_now_iso(),
            )
            token = self._vault.mint_capability(
                capability=f"cmd:{action_type_label}",
                scope=self._workspace_root,
                actions=[action_type.value],
                risk_tier_ceiling=RiskTier.T2,
                intent_root=intent_root,
                issued_to="hermes:governed-upstream",
            )
            evaluation = self._sentinel.evaluate(proposal, capability=token)
            decision = (
                evaluation.decision.to_dict()
                if hasattr(evaluation, "decision")
                else {
                    "permitted": True,
                    "blocking_layer": None,
                    "denial_reason": None,
                }
            )

            if not decision.get("permitted", True):
                msg = f"Action rejected by Sentinel: {decision.get('denial_reason', 'unknown')}"
                print(msg)
                return 1

            result = func(*args, **kwargs)

            if self._trust_store:
                trace = {
                    "trace_id": new_urn_uuid(),
                    "trace_type": "governed_upstream_cmd",
                    "created_at": utc_now_iso(),
                    "workspace_root": self._workspace_root,
                    "action": {
                        "action_type_label": action_type_label,
                        "params": params,
                        "decision": decision,
                    },
                }
                self._trust_store.store_audit_trace(trace)

            return result

        return wrapper

    def apply_cron_hook(self, cron_module: Any) -> None:
        """Patch an upstream cron module's add_job with Sentinel governance."""
        if hasattr(cron_module, "add_job"):
            original = cron_module.add_job
            cron_module.add_job = self.wrap("cron", original)

    @staticmethod
    def _label_to_action_type(label: str) -> ActionType:
        mapping = {
            "cron": ActionType.SCHEDULING,
            "tools": ActionType.CONFIG_WRITE,
            "skills": ActionType.CONFIG_WRITE,
            "model": ActionType.CONFIG_WRITE,
        }
        return mapping.get(label, ActionType.CONFIG_WRITE)


__all__ = ["GovernanceHooks"]

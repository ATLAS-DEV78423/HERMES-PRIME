from __future__ import annotations

from typing import Any

from ..contracts import ActionType, CapabilityToken, RiskTier
from ..utils import new_urn_uuid


class ScopeViolation(Exception):
    pass


class CapabilityScoper:
    def __init__(self, workspace_root: str) -> None:
        self._workspace_root = workspace_root

    def scope_for_subagent(
        self,
        parent_token: CapabilityToken,
        sub_scope: str | None = None,
        risk_downgrade: int = 1,
    ) -> CapabilityToken:
        scope = sub_scope or parent_token.scope
        if not scope.startswith(self._workspace_root):
            raise ScopeViolation(f"Scope {scope} is outside workspace root {self._workspace_root}")
        if not scope.startswith(parent_token.scope):
            raise ScopeViolation(
                f"Sub-agent scope {scope} exceeds parent scope {parent_token.scope}"
            )

        parent_ceiling = parent_token.risk_tier_ceiling
        if isinstance(parent_ceiling, str):
            parent_ceiling = RiskTier(parent_ceiling)
        parent_level = parent_ceiling.level
        new_level = max(RiskTier.T0.level, parent_level - risk_downgrade)
        new_ceiling = RiskTier(f"T{new_level}")

        return CapabilityToken(
            token_id=new_urn_uuid(),
            capability=parent_token.capability,
            scope=scope,
            actions=list(parent_token.actions),
            risk_tier_ceiling=new_ceiling,
            expires_at=parent_token.expires_at,
            intent_root=parent_token.intent_root,
            issued_to=parent_token.issued_to,
            issued_at=parent_token.issued_at,
            nonce=parent_token.nonce,
            signature=parent_token.signature,
        )

    def verify_action_allowed(
        self,
        token: CapabilityToken,
        action: ActionType,
        target_scope: str,
    ) -> None:
        action_str = action.value if isinstance(action, ActionType) else action
        if action_str not in token.actions:
            raise ScopeViolation(
                f"Action {action_str} not in token capabilities: {list(token.actions)}"
            )
        if not target_scope.startswith(token.scope):
            raise ScopeViolation(f"Target scope {target_scope} outside token scope {token.scope}")

    def restrict_actions(
        self,
        token: CapabilityToken,
        allowed_actions: list[ActionType],
    ) -> CapabilityToken:
        allowed_strs = {a.value if isinstance(a, ActionType) else a for a in allowed_actions}
        restricted = [a for a in token.actions if a in allowed_strs]
        return CapabilityToken(
            token_id=token.token_id,
            capability=token.capability,
            scope=token.scope,
            actions=restricted,
            risk_tier_ceiling=token.risk_tier_ceiling,
            expires_at=token.expires_at,
            intent_root=token.intent_root,
            issued_to=token.issued_to,
            issued_at=token.issued_at,
            nonce=token.nonce,
            signature=token.signature,
        )

    def to_dict(self, token: CapabilityToken) -> dict[str, Any]:
        ceiling = token.risk_tier_ceiling
        if isinstance(ceiling, RiskTier):
            ceiling_val = ceiling.value
        else:
            ceiling_val = ceiling
        return {
            "token_id": token.token_id,
            "capability": token.capability,
            "scope": token.scope,
            "actions": list(token.actions),
            "risk_tier_ceiling": ceiling_val,
            "expires_at": token.expires_at,
        }

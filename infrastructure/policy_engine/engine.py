from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from hermes_prime.contracts import (
    ActionProposal,
    ActionType,
    CapabilityToken,
    IntentRoot,
    MemoryTier,
    RiskTier,
    SentinelDecision,
)
from hermes_prime.signing import HMACSigner
from hermes_prime.utils import (
    contains_null_byte,
    contains_shell_meta,
    parse_iso8601,
    path_subscope,
    scope_prefix,
    new_urn_uuid,
    utc_now_iso,
)


@dataclass
class PolicyContext:
    workspace_root: str
    max_dispatches_per_turn: int = 12
    max_tokens_per_turn: int = 25_000
    max_chain_depth: int = 5
    max_context_bytes: int = 1_000_000
    max_memory_claims: int = 10000
    max_memory_claim_length: int = 10000


@dataclass
class ScopePolicy:
    root: str

    def contains(self, path_or_scope: str) -> bool:
        return path_subscope(path_or_scope, self.root)


class PolicyEngine:
    """Deterministic Sentinel core."""

    def __init__(
        self,
        context: PolicyContext,
        signer: Optional[HMACSigner] = None,
    ) -> None:
        self.context = context
        self.signer = signer or HMACSigner(
            identity="sentinel:policy-kernel", secret=b"hermes-prime-policy-secret"
        )
        self.intent_roots: dict[str, IntentRoot] = {}
        self.turn_dispatches = 0
        self.turn_tokens = 0
        self.audit_log: list[dict[str, Any]] = []

    def register_intent_root(self, intent_root: IntentRoot) -> None:
        self.intent_roots[intent_root.intent_root] = intent_root

    def begin_turn(self) -> None:
        self.turn_dispatches = 0
        self.turn_tokens = 0

    def evaluate(
        self,
        action: ActionProposal,
        capability: CapabilityToken | None = None,
        advisory_signals: Optional[list[str]] = None,
    ) -> SentinelDecision:
        advisory_signals = list(advisory_signals or [])
        timestamp = utc_now_iso()
        decision_id = new_urn_uuid()

        # Layer 1: schema / action validity is handled by ActionProposal itself.
        # Layer 2: capability validation.
        if capability is not None:
            cap_error = self._validate_capability(action, capability)
            if cap_error is not None:
                return self._deny(
                    decision_id,
                    timestamp,
                    action.action_id,
                    2,
                    cap_error,
                    advisory_signals,
                )

        # Layer 3: intent root verification.
        intent_error = self._validate_intent(action)
        if intent_error is not None:
            return self._deny(
                decision_id,
                timestamp,
                action.action_id,
                3,
                intent_error,
                advisory_signals,
            )

        # Layer 4: deterministic policy rules.
        policy_rule, policy_error = self._evaluate_policy(action, capability)
        if policy_error is not None:
            return self._deny(
                decision_id,
                timestamp,
                action.action_id,
                4,
                policy_error,
                advisory_signals,
            )

        # Layer 5: injection firewall.
        firewall_error = self._firewall_check(action)
        if firewall_error is not None:
            return self._deny(
                decision_id,
                timestamp,
                action.action_id,
                5,
                firewall_error,
                advisory_signals,
            )

        # Layer 6: resource ceiling.
        resource_error = self._resource_check(action)
        if resource_error is not None:
            return self._deny(
                decision_id,
                timestamp,
                action.action_id,
                6,
                resource_error,
                advisory_signals,
            )

        risk_tier = self._assign_risk_tier(action)
        consent_required = risk_tier.level >= 2
        decision = SentinelDecision(
            decision_id=decision_id,
            timestamp=timestamp,
            action_id=action.action_id,
            permitted=True,
            risk_tier=risk_tier,
            policy_rule=policy_rule,
            blocking_layer=None,
            denial_reason=None,
            advisory_signals=advisory_signals,
            consent_required=consent_required,
            audit_written=True,
        )
        self._record(decision)
        return decision

    def _validate_capability(
        self, action: ActionProposal, capability: CapabilityToken
    ) -> Optional[str]:
        if capability.intent_root != action.intent_root:
            return "intent_root_mismatch"
        if capability.capability != action.capability:
            return "capability_mismatch"
        if not capability.actions:
            return "capability_has_no_actions"
        permitted_actions = {self._normalize_capability_action(item) for item in capability.actions}
        if action.action_type.value not in permitted_actions:
            return "action_not_permitted_by_token"
        if not capability.risk_tier_ceiling:
            return "missing_risk_tier_ceiling"
        if self._assign_risk_tier(action).level > capability.risk_tier_ceiling.level:
            return "risk_tier_exceeds_token_ceiling"
        if not path_subscope(action.scope, capability.scope):
            return "scope_exceeds_token"
        if action.intent_root not in self.intent_roots:
            return "unknown_intent_root"
        token_intent = self.intent_roots[action.intent_root]
        if not path_subscope(action.scope, token_intent.scope):
            return "scope_exceeds_intent_root"
        if action.proposed_at == "":
            return "missing_proposed_at"
        return None

    def _normalize_capability_action(self, action_name: str) -> str:
        mapping = {
            "read": ActionType.FILESYSTEM_READ.value,
            "write": ActionType.FILESYSTEM_WRITE.value,
            "commit": ActionType.FILESYSTEM_COMMIT.value,
            "command": ActionType.EXECUTION_COMMAND.value,
            "mine": ActionType.MINER_DISPATCH.value,
            "memory": ActionType.MEMORY_WRITE.value,
            "capability": ActionType.CAPABILITY_REQUEST.value,
        }
        return mapping.get(action_name, action_name)

    def _validate_intent(self, action: ActionProposal) -> Optional[str]:
        intent = self.intent_roots.get(action.intent_root)
        if intent is None:
            return "unknown_intent_root"
        proposed = parse_iso8601(action.proposed_at)
        issued = parse_iso8601(intent.issued_at)
        expires = parse_iso8601(intent.expires_at)
        if proposed < issued:
            return "proposal_precedes_intent_root"
        if proposed > expires:
            return "intent_root_expired"
        if not path_subscope(action.scope, intent.scope):
            return "scope_exceeds_intent_root"
        if not path_subscope(action.scope, self.context.workspace_root):
            return "scope_outside_workspace"
        return None

    def _evaluate_policy(
        self, action: ActionProposal, capability: CapabilityToken | None
    ) -> tuple[str, Optional[str]]:
        rule = f"{action.action_type.value}.workspace_scoped"
        if action.action_type == ActionType.FILESYSTEM_READ:
            return rule, None
        if action.action_type == ActionType.FILESYSTEM_WRITE:
            return rule, None
        if action.action_type == ActionType.FILESYSTEM_COMMIT:
            return rule, None
        if action.action_type == ActionType.EXECUTION_COMMAND:
            return rule, "execution_command_blocked_until_forge_mvp"
        if action.action_type == ActionType.MINER_DISPATCH:
            return rule, None
        if action.action_type == ActionType.MEMORY_WRITE:
            tier = action.parameters.get("tier", "quarantine")
            if tier == MemoryTier.QUARANTINE.value:
                return rule, None
            return rule, "authoritative_memory_writes_require_promotion"
        if action.action_type == ActionType.CAPABILITY_REQUEST:
            return rule, None
        return rule, "unknown_action_type"

    def _firewall_check(self, action: ActionProposal) -> Optional[str]:
        raw_scope = action.scope
        if contains_null_byte(raw_scope):
            return "null_byte_in_scope"
        if contains_shell_meta(raw_scope):
            return "shell_metacharacter_in_scope"
        decoded = scope_prefix(raw_scope)
        if ".." in decoded:
            return "path_traversal_attempt"
        for key, value in action.parameters.items():
            if isinstance(value, str) and (contains_null_byte(value) or contains_shell_meta(value)):
                return f"injection_signature_in_parameter:{key}"
        return None

    def _resource_check(self, action: ActionProposal) -> Optional[str]:
        self.turn_dispatches += 1
        if self.turn_dispatches > self.context.max_dispatches_per_turn:
            return "dispatch_quota_exceeded"
        estimated_tokens = 50 + len(action.parameters) * 10
        self.turn_tokens += estimated_tokens
        if self.turn_tokens > self.context.max_tokens_per_turn:
            return "token_budget_exceeded"
        if len(action.scope.encode("utf-8")) > self.context.max_context_bytes:
            return "scope_payload_too_large"
        if action.action_type == ActionType.MEMORY_WRITE:
            claim_text = action.parameters.get("claim", "")
            if len(claim_text) > self.context.max_memory_claim_length:
                return "memory_claim_exceeds_max_length"
        return None

    def _assign_risk_tier(self, action: ActionProposal) -> RiskTier:
        if action.action_type == ActionType.FILESYSTEM_READ:
            return RiskTier.T0
        if action.action_type == ActionType.MINER_DISPATCH:
            return RiskTier.T0
        if action.action_type == ActionType.FILESYSTEM_WRITE:
            return RiskTier.T1
        if action.action_type == ActionType.FILESYSTEM_COMMIT:
            return RiskTier.T2
        if action.action_type == ActionType.CAPABILITY_REQUEST:
            return RiskTier.T1
        if action.action_type == ActionType.MEMORY_WRITE:
            return RiskTier.T2
        if action.action_type == ActionType.EXECUTION_COMMAND:
            return RiskTier.T2
        if action.action_type == ActionType.AGENT_SPAWN:
            return RiskTier.T3
        if action.action_type == ActionType.AGENT_KILL:
            return RiskTier.T3
        return action.risk_tier

    def _deny(
        self,
        decision_id: str,
        timestamp: str,
        action_id: str,
        blocking_layer: int,
        reason: str,
        advisory_signals: list[str],
    ) -> SentinelDecision:
        decision = SentinelDecision(
            decision_id=decision_id,
            timestamp=timestamp,
            action_id=action_id,
            permitted=False,
            risk_tier=None,
            policy_rule=None,
            blocking_layer=blocking_layer,
            denial_reason=reason,
            advisory_signals=advisory_signals,
            consent_required=None,
            audit_written=True,
        )
        self._record(decision)
        return decision

    def _record(self, decision: SentinelDecision) -> None:
        self.audit_log.append(decision.to_dict())

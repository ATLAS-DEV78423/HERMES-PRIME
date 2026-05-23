from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from hermes_prime.contracts import (
    ActionProposal,
    CapabilityToken,
    IntentRoot,
    SentinelDecision,
)

from .bundle import PolicyBundle
from .engine import PolicyContext, PolicyEngine
from .opa_adapter import OpaPolicyAdapter, OpaUnavailableError
from infrastructure.trust_store import TrustStore


@dataclass
class SentinelEvaluation:
    decision: SentinelDecision
    source: str
    bundle_manifest: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.to_dict(),
            "source": self.source,
            "bundle_manifest": self.bundle_manifest,
        }


class SentinelService:
    def __init__(
        self,
        workspace_root: str | Path,
        policy_root: str | Path,
        trust_store: TrustStore | None = None,
        policy_engine: Optional[PolicyEngine] = None,
    ) -> None:
        self.bundle = PolicyBundle(policy_root)
        self.policy_engine = policy_engine or PolicyEngine(
            PolicyContext(workspace_root=str(Path(workspace_root).resolve()))
        )
        self.trust_store = trust_store
        self.opa = OpaPolicyAdapter(policy_root)

    def register_intent_root(self, intent_root: IntentRoot) -> None:
        self.policy_engine.register_intent_root(intent_root)
        if self.trust_store is not None:
            self.trust_store.store_intent_root(intent_root)

    def evaluate(
        self,
        action: ActionProposal,
        capability: CapabilityToken | None = None,
        advisory_signals: Optional[list[str]] = None,
    ) -> SentinelEvaluation:
        intent_root = self.policy_engine.intent_roots.get(action.intent_root)
        if intent_root is None:
            raise ValueError("unknown intent root")
        try:
            decision = self.opa.evaluate(
                action=action,
                capability=capability,
                intent_root=intent_root,
                advisory_signals=advisory_signals,
            )
            source = "opa"
        except OpaUnavailableError:
            decision = self.policy_engine.evaluate(
                action=action,
                capability=capability,
                advisory_signals=advisory_signals,
            )
            source = "python-deterministic"
        if self.trust_store is not None:
            self.trust_store.store_decision(decision)
        return SentinelEvaluation(
            decision=decision,
            source=source,
            bundle_manifest=self.bundle.manifest(),
        )

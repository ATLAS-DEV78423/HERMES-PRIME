from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from hermes_prime.contracts import ActionProposal, ActionType, AuditTrace, RiskTier
from hermes_prime.utils import new_urn_uuid, utc_now_iso
from infrastructure.policy_engine.engine import PolicyEngine
from infrastructure.sandboxed_forge.forge import SandboxedForge
from infrastructure.trust_store import TrustStore
from infrastructure.vault.capabilities import CapabilityVault
from miners.ast_miner.miner import AstMiner
from miners.fabric_miners.miners import (
    FabricPatternCatalog,
    PatternClassificationMiner,
    PatternInjectionMiner,
    PatternMiner,
)
from miners.file_miner.miner import FileMiner


@dataclass
class OrchestrationResult:
    trace_id: str
    prompt: str
    classification: dict[str, Any]
    pattern_matches: list[dict[str, Any]]
    augmentation: dict[str, Any]
    action: dict[str, Any]
    decision: dict[str, Any]
    retrieval: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""


class HermesPrimeOrchestrator:
    def __init__(
        self,
        workspace_root: str | Path,
        fabric_root: str | Path,
        policy: PolicyEngine,
        vault: CapabilityVault,
        trust_store: Optional[TrustStore] = None,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.fabric_root = Path(fabric_root).resolve()
        self.policy = policy
        self.vault = vault
        self.trust_store = trust_store
        self.forge = SandboxedForge(self.workspace_root)
        self.file_miner = FileMiner(self.workspace_root, trust_store=trust_store)
        self.ast_miner = AstMiner(self.workspace_root, trust_store=trust_store)
        self.classifier = PatternClassificationMiner()
        self.pattern_miner = PatternMiner(FabricPatternCatalog(self.fabric_root))
        self.pattern_injector = PatternInjectionMiner()
        self.recursion_ceiling = 1
        self._depth = 0

    def run(self, prompt: str, scope: str | None = None) -> OrchestrationResult:
        if self._depth >= self.recursion_ceiling:
            raise RuntimeError("recursion ceiling exceeded")
        self._depth += 1
        scope = scope or str(self.workspace_root)
        try:
            self.policy.begin_turn()
            classification = self.classifier.classify(prompt)
            matches = self.pattern_miner.match(classification)
            augmentation = self.pattern_injector.inject(matches[:3])

            search_pattern = re.escape(prompt.split()[0]) if prompt.split() else ".*"
            retrieval = [
                self.file_miner.search_text(pattern=search_pattern, scope=scope).to_dict(),
                self.ast_miner.extract_symbols(scope=scope).to_dict(),
            ]

            intent = self.vault.register_intent_root(
                scope=scope, issued_to="hermes:session:local"
            )
            self.policy.register_intent_root(intent)

            action_type = self._infer_action(prompt)
            action = ActionProposal(
                action_id=new_urn_uuid(),
                action_type=action_type,
                scope=scope,
                risk_tier=RiskTier.T0
                if action_type == ActionType.FILESYSTEM_READ
                else RiskTier.T1,
                intent_root=intent.intent_root,
                capability="cap:file-read:scoped"
                if action_type == ActionType.FILESYSTEM_READ
                else "cap:general:scoped",
                proposed_at=utc_now_iso(),
                parameters={"prompt": prompt},
            )
            decision = self.policy.evaluate(action)
            summary = self._summarize(
                prompt, classification.to_dict(), augmentation.to_dict(), decision.to_dict()
            )
            trace_id = new_urn_uuid()
            if self.trust_store is not None:
                self.trust_store.store_audit_trace(
                    AuditTrace(
                        trace_id=trace_id,
                        trace_type="prompt_flow",
                        created_at=utc_now_iso(),
                        workspace_root=str(self.workspace_root),
                        intent_root=intent.intent_root,
                        prompt=prompt,
                        classification=classification.to_dict(),
                        pattern_matches=[match.to_dict() for match in matches],
                        augmentation=augmentation.to_dict(),
                        retrieval=retrieval,
                        action=action.to_dict(),
                        decision=decision.to_dict(),
                        mutation={},
                        summary=summary,
                        replayable=True,
                    )
                )
            return OrchestrationResult(
                trace_id=trace_id,
                prompt=prompt,
                classification=classification.to_dict(),
                pattern_matches=[match.to_dict() for match in matches],
                augmentation=augmentation.to_dict(),
                action=action.to_dict(),
                decision=decision.to_dict(),
                retrieval=retrieval,
                summary=summary,
            )
        finally:
            self._depth -= 1

    def _infer_action(self, prompt: str) -> ActionType:
        text = prompt.lower()
        if any(k in text for k in ("write", "patch", "fix", "implement", "change")):
            return ActionType.FILESYSTEM_WRITE
        if any(k in text for k in ("run", "execute", "command")):
            return ActionType.EXECUTION_COMMAND
        if any(k in text for k in ("memory", "remember")):
            return ActionType.MEMORY_WRITE
        if any(k in text for k in ("token", "capability")):
            return ActionType.CAPABILITY_REQUEST
        if any(k in text for k in ("mine", "search", "find", "retrieve", "read")):
            return ActionType.FILESYSTEM_READ
        return ActionType.FILESYSTEM_READ

    def _summarize(self, prompt: str, classification: dict[str, Any], augmentation: dict[str, Any], decision: dict[str, Any]) -> str:
        return (
            f"Prompt classified as {classification['task_types']} in domain {classification['domain']}. "
            f"Pattern guidance: {', '.join(augmentation['reasoning_style']) or 'n/a'}. "
            f"Sentinel {'permitted' if decision['permitted'] else 'denied'} action {decision['action_id']}."
        )

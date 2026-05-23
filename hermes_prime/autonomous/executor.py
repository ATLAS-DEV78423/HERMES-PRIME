from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

from hermes_prime.autonomous.inference_logger import InferenceLogger, InferenceAttestation
from hermes_prime.autonomous.proposal_parser import ProposalParser, ProposalParsingError
from hermes_prime.contracts import (
    ActionProposal,
    ActionType,
    AuditTrace,
    IntentRoot,
    LifecycleState,
    RiskTier,
    TrustState,
)
from hermes_prime.memory import MemoryStore, DepthPolicy
from hermes_prime.memory.backends.sqlite_backend import SQLiteMemoryBackend
from hermes_prime.llm.prompt_builder import PromptBuilder
from hermes_prime.signing import HMACSigner
from hermes_prime.utils import new_urn_uuid, utc_now_iso, sha256_bytes
from infrastructure.policy_engine.sentinel_service import SentinelService
from infrastructure.sandboxed_forge.forge import SandboxedForge
from infrastructure.trust_store import TrustStore
from infrastructure.vault.capabilities import CapabilityVault
from pathlib import Path


@dataclass
class AutonomousExecutionResult:
    """Result of autonomous execution."""
    execution_id: str
    task_prompt: str
    trace_id: str
    inference_attestation: Optional[InferenceAttestation]
    proposal: Optional[ActionProposal]
    sentinel_decision: Optional[dict[str, Any]]
    execution_status: str  # "success", "proposal_rejected", "parse_error", "inference_error"
    error_message: Optional[str]
    summary: str


class AutonomousExecutor:
    """Orchestrates autonomous LLM-driven execution with Sentinel governance."""

    def __init__(
        self,
        llm_client: LLMClient,
        sentinel: SentinelService,
        vault: CapabilityVault,
        trust_store: Optional[TrustStore] = None,
        forge: Optional[SandboxedForge] = None,
        workspace_root: str | Path = ".",
        signer: Optional[HMACSigner] = None,
    ):
        self.llm_client = llm_client
        self.sentinel = sentinel
        self.vault = vault
        self.trust_store = trust_store
        self.forge = forge or SandboxedForge(workspace_root)
        self.workspace_root = Path(workspace_root).resolve()
        self.signer = signer or HMACSigner()
        self.prompt_builder = PromptBuilder(str(self.workspace_root))
        self.memory_store = MemoryStore(
            backend=SQLiteMemoryBackend(self.workspace_root / ".hermes-prime" / "memory.db"),
            depth_policy=DepthPolicy(max_claims_per_intent=100, max_total_claims=10000),
        )

    def execute(
        self,
        task_prompt: str,
        model: str,
        scope: Optional[str] = None,
        file_context: Optional[list[str]] = None,
    ) -> AutonomousExecutionResult:
        """Execute full autonomous loop: prompt → LLM → parse → Sentinel → audit."""
        execution_id = new_urn_uuid()
        scope = scope or str(self.workspace_root)

        try:
            # Step 1: Register intent root
            intent = self.vault.register_intent_root(
                scope=scope,
                issued_to=f"hermes:autonomous:{execution_id}",
            )
            self.sentinel.register_intent_root(intent)

            # Step 2: Call LLM
            messages = self.prompt_builder.build_messages(
                task=task_prompt,
                file_context=file_context,
            )
            llm_request = LLMRequest(
                model=model,
                messages=messages,
                temperature=0.7,
                max_tokens=1024,
            )
            llm_response = self.llm_client.infer(llm_request)

            # Create signed inference attestation
            inference_signature = self.signer.sign(llm_response.message_content)
            inference_attestation = InferenceLogger.create_attestation(
                llm_request,
                llm_response,
                signature=inference_signature,
            )

            # Step 3: Parse LLM output into ActionProposal
            try:
                proposal = ProposalParser.parse(
                    llm_response.message_content,
                    intent_root_id=intent.intent_root,
                    workspace_root=str(self.workspace_root),
                )
            except ProposalParsingError as e:
                trace_id = new_urn_uuid()
                return AutonomousExecutionResult(
                    execution_id=execution_id,
                    task_prompt=task_prompt,
                    trace_id=trace_id,
                    inference_attestation=inference_attestation,
                    proposal=None,
                    sentinel_decision=None,
                    execution_status="parse_error",
                    error_message=str(e),
                    summary=f"Failed to parse LLM output: {e}",
                )

            # Step 4: Mint capability for the action
            token = self.vault.mint_capability(
                capability=proposal.capability,
                scope=proposal.scope,
                actions=[proposal.action_type.value],
                risk_tier_ceiling=proposal.risk_tier,
                intent_root=intent.intent_root,
                issued_to=f"hermes:autonomous:{execution_id}",
            )

            # Step 5: Evaluate via Sentinel
            evaluation = self.sentinel.evaluate(proposal, capability=token)

            # Step 6: Log audit trace
            trace_id = new_urn_uuid()
            trace_payload = {
                "execution_id": execution_id,
                "task_prompt": task_prompt,
                "model": model,
                "inference_attestation": inference_attestation.to_dict(),
                "proposal": proposal.to_dict(),
                "token_id": token.token_id,
                "decision": evaluation.to_dict(),
            }
            if self.trust_store:
                trace = AuditTrace(
                    trace_id=trace_id,
                    trace_type="autonomous_execution",
                    created_at=utc_now_iso(),
                    workspace_root=str(self.workspace_root),
                    intent_root=intent.intent_root,
                    action=proposal.to_dict(),
                    decision=evaluation.to_dict(),
                    mutation={
                        "inference_attestation": inference_attestation.to_dict(),
                        "proposal_json": llm_response.message_content,
                    },
                    summary=f"Autonomous execution: {task_prompt} → {proposal.action_type.value} → {'APPROVED' if evaluation.decision.permitted else 'REJECTED'}",
                    replayable=True,
                )
                self.trust_store.store_audit_trace(trace)

            # Build result
            result = AutonomousExecutionResult(
                execution_id=execution_id,
                task_prompt=task_prompt,
                trace_id=trace_id,
                inference_attestation=inference_attestation,
                proposal=proposal,
                sentinel_decision=evaluation.decision.to_dict(),
                execution_status="success" if evaluation.decision.permitted else "proposal_rejected",
                error_message=None if evaluation.decision.permitted else evaluation.decision.denial_reason,
                summary=f"Autonomous execution: {task_prompt} → {proposal.action_type.value} → {'APPROVED' if evaluation.decision.permitted else 'REJECTED'}",
            )

            # Store execution metadata as a memory claim for future reference
            try:
                self.memory_store.write(
                    claim_text=f"Autonomous execution: {task_prompt} → {proposal.action_type.value} → {'SUCCESS' if evaluation.decision.permitted else 'REJECTED'}",
                    source={
                        "component": "autonomous_executor",
                        "execution_id": execution_id,
                        "model": model,
                        "workspace": str(self.workspace_root),
                    },
                    intent_root=intent,
                    epistemic_confidence=0.9 if evaluation.decision.permitted else 0.3,
                    source_trust="system",
                )
            except Exception:
                # Don't let memory storage failures break the execution
                pass

            return result

        except Exception as e:
            trace_id = new_urn_uuid()
            return AutonomousExecutionResult(
                execution_id=execution_id,
                task_prompt=task_prompt,
                trace_id=trace_id,
                inference_attestation=None,
                proposal=None,
                sentinel_decision=None,
                execution_status="inference_error",
                error_message=str(e),
                summary=f"Autonomous execution failed: {e}",
            )

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import logging

from hermes_prime.autonomous.inference_logger import InferenceLogger, InferenceAttestation
from hermes_prime.autonomous.proposal_parser import ProposalParser, ProposalParsingError
from hermes_prime.contracts import (
    ActionProposal,
    AuditTrace,
)
from hermes_prime.learning.outcome import OutcomeTracker, OutcomeStore
from hermes_prime.learning.registry import LearningRegistry
from hermes_prime.learning.augmenter import PromptAugmenter
from hermes_prime.learning.engine import LearningEngine
from hermes_prime.memory import MemoryStore, DepthPolicy
from hermes_prime.memory.backends.sqlite_backend import SQLiteMemoryBackend
from hermes_prime.llm.prompt_builder import PromptBuilder
from hermes_prime.secrets import get_signer
from hermes_prime.signing import HMACSigner
from hermes_prime.utils import new_urn_uuid, utc_now_iso
from infrastructure.policy_engine.sentinel_service import SentinelService
from infrastructure.sandboxed_forge.forge import SandboxedForge
from infrastructure.trust_store import TrustStore
from infrastructure.vault.capabilities import CapabilityVault
from pathlib import Path
from hermes_prime.llm.client import LLMClient, LLMRequest, LLMResponse
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from requests.exceptions import ConnectionError, Timeout


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
    """Orchestrates autonomous LLM-driven execution with Sentinel governance and learning loop."""

    def __init__(
        self,
        llm_client: LLMClient,
        sentinel: SentinelService,
        vault: CapabilityVault,
        trust_store: Optional[TrustStore] = None,
        forge: Optional[SandboxedForge] = None,
        workspace_root: str | Path = ".",
        signer: Optional[HMACSigner] = None,
        enable_learning: bool = True,
        outcome_store: Optional[OutcomeStore] = None,
        learning_registry: Optional[LearningRegistry] = None,
    ):
        self.llm_client = llm_client
        self.sentinel = sentinel
        self.vault = vault
        self.trust_store = trust_store
        self.forge = forge or SandboxedForge(workspace_root)
        self.workspace_root = Path(workspace_root).resolve()
        self.signer = signer or get_signer("autonomous")
        self.prompt_builder = PromptBuilder(str(self.workspace_root))
        self.memory_store = MemoryStore(
            backend=SQLiteMemoryBackend(self.workspace_root / ".hermes-prime" / "memory.db"),
            depth_policy=DepthPolicy(max_claims_per_intent=100, max_total_claims=10000),
        )

        hermes_dir = self.workspace_root / ".hermes-prime"
        outcome_db = outcome_store or OutcomeStore(hermes_dir / "outcomes.db")
        self.outcome_tracker = OutcomeTracker(outcome_db) if enable_learning else None
        self.learning_registry = learning_registry or (
            LearningRegistry(hermes_dir / "learned_patterns.json") if enable_learning else None
        )
        self.prompt_augmenter = PromptAugmenter(self.learning_registry) if (enable_learning and self.learning_registry) else None
        self.learning_engine = LearningEngine(
            outcome_store=outcome_db,
            registry=self.learning_registry,
            memory_store=self.memory_store,
        ) if (enable_learning and self.learning_registry) else None
        self._execution_count = 0

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

        # Get learned guidance from learning loop if available
        learned_guidance = None
        if self.prompt_augmenter:
            try:
                learned_guidance = self.prompt_augmenter.build_augmentation_block(task_prompt)
            except Exception as lg_e:
                logging.warning("failed to build learned guidance: %s", lg_e)

        try:
            # Step 1: Register intent root
            intent = self.vault.register_intent_root(
                scope=scope,
                issued_to=f"hermes:autonomous:{execution_id}",
            )
            self.sentinel.register_intent_root(intent)

            # Step 2: Gather relevant memory context and build prompt
            try:
                recall_result = self.memory_store.recall(task_prompt, limit=5)
                recent_actions = [
                    {
                        "fact_id": r.fact_id,
                        "claim": r.claim,
                        "source": r.source,
                        "action_type": "memory.write",
                        "scope": r.claim,
                    }
                    for r in (recall_result.results or [])
                ]
            except Exception as mem_e:
                logging.warning("memory recall failed: %s", mem_e)
                recent_actions = None

            messages = self.prompt_builder.build_messages(
                task=task_prompt,
                file_context=file_context,
                recent_actions=recent_actions,
                learned_guidance=learned_guidance,
            )

            llm_request = LLMRequest(
                model=model,
                messages=messages,
                temperature=0.7,
                max_tokens=1024,
            )
            try:
                llm_response = self._infer_with_retry(llm_request)
            except (ConnectionError, Timeout) as retry_err:
                trace_id = new_urn_uuid()
                result = AutonomousExecutionResult(
                    execution_id=execution_id,
                    task_prompt=task_prompt,
                    trace_id=trace_id,
                    inference_attestation=None,
                    proposal=None,
                    sentinel_decision=None,
                    execution_status="inference_error",
                    error_message=f"LLM inference failed after retries: {retry_err}",
                    summary=f"Autonomous execution failed after 3 retries: {retry_err}",
                )
                self._record_outcome(task_prompt, "", "", False, False, 0, 0, model, utc_now_iso())
                return result

            # Create signed inference attestation
            inference_signature = self.signer.sign(llm_response.message_content.encode("utf-8"))
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
                result = AutonomousExecutionResult(
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
                self._record_outcome(task_prompt, "", "", False, False,
                                      inference_attestation.latency_ms,
                                      inference_attestation.tokens_used, model, utc_now_iso())
                return result

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
                mem_result = self.memory_store.write(
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
                if mem_result and mem_result.success and mem_result.attestation is not None:
                    trace_payload["memory_attestation"] = mem_result.attestation.to_dict()
                    if self.trust_store:
                        trace.mutation["memory_attestation"] = mem_result.attestation.to_dict()
                        self.trust_store.store_audit_trace(trace)
            except Exception as mem_e:
                logging.warning("memory write failed: %s", mem_e)

            # Record outcome for learning loop
            self._record_outcome(
                task_prompt=task_prompt,
                action_type=proposal.action_type.value,
                action_scope=proposal.scope,
                approved=evaluation.decision.permitted,
                parseable=True,
                latency_ms=inference_attestation.latency_ms,
                tokens_used=inference_attestation.tokens_used,
                model=model,
                timestamp=utc_now_iso(),
                blocking_layer=evaluation.decision.blocking_layer,
                denial_reason=evaluation.decision.denial_reason,
            )

            # Apply prompt augmentation feedback for success/failure
            if self.prompt_augmenter and learned_guidance:
                self.prompt_augmenter.record_application_result(
                    [p.pattern_id for p in self.learning_registry.list_patterns(limit=5)],
                    success=evaluation.decision.permitted,
                )

            return result

        except Exception as e:
            trace_id = new_urn_uuid()
            result = AutonomousExecutionResult(
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

            self._record_outcome(task_prompt, "", "", False, False, 0, 0, model, utc_now_iso())
            return result

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)))
    def _infer_with_retry(self, request: LLMRequest) -> LLMResponse:
        return self.llm_client.infer(request)

    def _record_outcome(
        self,
        task_prompt: str,
        action_type: str,
        action_scope: str,
        approved: bool,
        parseable: bool,
        latency_ms: float,
        tokens_used: int,
        model: str,
        timestamp: str,
        blocking_layer: int | None = None,
        denial_reason: str | None = None,
    ) -> None:
        if not self.outcome_tracker:
            return
        try:
            self.outcome_tracker.record(
                execution_id=new_urn_uuid(),
                task_prompt=task_prompt,
                action_type=action_type,
                action_scope=action_scope,
                approved=approved,
                parseable=parseable,
                latency_ms=latency_ms,
                tokens_used=tokens_used,
                model=model,
                timestamp=timestamp,
                blocking_layer=blocking_layer,
                denial_reason=denial_reason,
            )
            self._execution_count += 1

            if self.learning_engine and self._execution_count % 10 == 0:
                reflection = self.learning_engine.reflect(min_outcomes=5)
                if reflection.get("reflected"):
                    logging.info(
                        "learning loop reflected: %d patterns created",
                        reflection.get("patterns_created", 0),
                    )
        except Exception as oe:
            logging.warning("failed to record outcome: %s", oe)

"""
ArtifactPresenter: assemble what the reviewer sees.

For each artifact, the reviewer needs:
  - Artifact identity and tier
  - Generation attestation (model, prompt_hash, predecessor retrievals)
  - Input retrievals with summaries
  - Validation results
  - Trust chain status (for transparency)
  - Any injection / probabilistic_input warnings

The presenter assembles this from the lineage store and the verifier.
Output is a structured ArtifactView the UI renders.

The presenter does NOT pull artifact content directly into reviewer
context unless the reviewer explicitly requests it. This is the "report,
never raw dump" pattern (fabric REPORTS.md) applied to review UX.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from cogtrust.attestations import Attestation, AttestationType
from cogtrust.lineage import LineageStore
from cogtrust.verification import TrustState, Verifier


@dataclass
class PredecessorSummary:
    attestation_id: str
    type: str
    summary: str  # one-line human-readable
    trust_state: str
    has_warnings: bool


@dataclass
class ArtifactView:
    artifact_attestation_id: str
    artifact_class: str
    tier: int
    model_identity: Optional[str]
    model_version: Optional[str]
    issued_at: str
    expires_at: Optional[str]
    intent_root_id: Optional[str]
    intent_description: Optional[str]
    trust_state: str  # current chain status
    trust_chain_length: int
    predecessor_summaries: list[PredecessorSummary] = field(default_factory=list)
    validation_summary: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    content_hashes: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "artifact_attestation_id": self.artifact_attestation_id,
            "artifact_class": self.artifact_class,
            "tier": self.tier,
            "model": {
                "identity": self.model_identity,
                "version": self.model_version,
            },
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "intent_root_id": self.intent_root_id,
            "intent_description": self.intent_description,
            "trust_state": self.trust_state,
            "trust_chain_length": self.trust_chain_length,
            "predecessors": [
                {
                    "attestation_id": p.attestation_id,
                    "type": p.type,
                    "summary": p.summary,
                    "trust_state": p.trust_state,
                    "has_warnings": p.has_warnings,
                }
                for p in self.predecessor_summaries
            ],
            "validation_summary": self.validation_summary,
            "warnings": list(self.warnings),
            "content_hashes": dict(self.content_hashes),
        }


class ArtifactPresenter:
    """
    Assembles ArtifactView for a generation attestation.

    Reads from the lineage store and the verifier. Does not directly
    fetch artifact bytes — those are available on demand by the UI.
    """

    def __init__(self, lineage: LineageStore, verifier: Verifier) -> None:
        self._lineage = lineage
        self._verifier = verifier

    def present(self, artifact_attestation_id: str) -> ArtifactView:
        att = self._lineage.get(artifact_attestation_id)
        if att is None:
            raise ValueError(
                f"attestation {artifact_attestation_id} not found"
            )
        if att.type != AttestationType.GENERATION:
            raise ValueError(
                f"presenter expects generation attestation; "
                f"got {att.type.value}"
            )

        # Verify chain to surface current trust state.
        chain_status = self._verifier.verify(artifact_attestation_id)

        # Resolve intent root.
        intent_desc = None
        if att.intent_root_ref:
            intent_att = self._lineage.get(att.intent_root_ref)
            if intent_att:
                intent_desc = intent_att.subject.get("intent_description")

        # Predecessor summaries.
        predecessor_summaries = []
        for pred_id in att.predecessor_refs:
            pred = self._lineage.get(pred_id)
            if pred is None:
                continue
            pred_status = self._verifier.verify(pred_id)
            summary = self._summarize_predecessor(pred)
            has_warnings = self._predecessor_has_warnings(pred)
            predecessor_summaries.append(
                PredecessorSummary(
                    attestation_id=pred_id,
                    type=pred.type.value,
                    summary=summary,
                    trust_state=pred_status.state.value,
                    has_warnings=has_warnings,
                )
            )

        # Validation summary (count passes/fails among descendants).
        validation_summary = self._collect_validations(artifact_attestation_id)

        # Warnings.
        warnings: list[str] = []
        if chain_status.state != TrustState.VALID:
            warnings.append(
                f"trust chain is in state {chain_status.state.value}: "
                f"{chain_status.reason}"
            )
        for ps in predecessor_summaries:
            if ps.has_warnings:
                warnings.append(
                    f"predecessor {ps.attestation_id} ({ps.type}) has warnings"
                )

        model_identity = att.subject.get("model", {}).get("name") or None
        model_version = att.subject.get("model", {}).get("version") or None

        return ArtifactView(
            artifact_attestation_id=artifact_attestation_id,
            artifact_class=att.artifact_class,
            tier=att.tier,
            model_identity=model_identity,
            model_version=model_version,
            issued_at=att.issued_at,
            expires_at=att.expires_at,
            intent_root_id=att.intent_root_ref,
            intent_description=intent_desc,
            trust_state=chain_status.state.value,
            trust_chain_length=chain_status.chain_length,
            predecessor_summaries=predecessor_summaries,
            validation_summary=validation_summary,
            warnings=warnings,
            content_hashes=dict(att.subject_hashes),
        )

    # --- helpers ---

    @staticmethod
    def _summarize_predecessor(pred: Attestation) -> str:
        if pred.type == AttestationType.RETRIEVAL:
            miner = pred.subject.get("miner", "?")
            task = pred.subject.get("task", "?")
            llm = " [LLM]" if pred.subject.get("llm_used") else ""
            returned = pred.subject.get("returned", "?")
            return f"{miner}.{task}{llm} returned {returned}"
        if pred.type == AttestationType.VALIDATION:
            validator = pred.subject.get("validator", "?")
            result = pred.subject.get("result", "?")
            return f"{validator}: {result}"
        if pred.type == AttestationType.GENERATION:
            cls = pred.artifact_class
            return f"generated artifact class={cls}"
        if pred.type == AttestationType.INTENT_ROOT:
            desc = pred.subject.get("intent_description", "?")
            return f"intent_root: {desc}"
        return pred.type.value

    @staticmethod
    def _predecessor_has_warnings(pred: Attestation) -> bool:
        if pred.type == AttestationType.RETRIEVAL:
            if pred.subject.get("llm_used"):
                return True
            # Injection-flag pattern (the value if any miner sets it).
            if pred.subject.get("injection_check") == "flagged":
                return True
        if pred.type == AttestationType.VALIDATION:
            if pred.subject.get("result") == "fail":
                return True
        return False

    def _collect_validations(self, artifact_id: str) -> dict:
        """Walk descendants for validation attestations."""
        result = {"passed": 0, "failed": 0, "details": []}
        for desc_id in self._lineage.descendants(artifact_id):
            desc = self._lineage.get(desc_id)
            if desc is None or desc.type != AttestationType.VALIDATION:
                continue
            validator = desc.subject.get("validator", "?")
            outcome = desc.subject.get("result", "?")
            if outcome == "pass":
                result["passed"] += 1
            elif outcome == "fail":
                result["failed"] += 1
            result["details"].append({
                "validator": validator,
                "result": outcome,
                "attestation_id": desc_id,
            })
        return result

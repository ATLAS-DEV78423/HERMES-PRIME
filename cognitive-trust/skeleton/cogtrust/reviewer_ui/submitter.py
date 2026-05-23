"""
ReviewSubmitter: convert a reviewer's decision into a review attestation.

This is the integration point between the UI session and the Attestation
Service. The submitter:

  - Validates the session state (authenticated, not expired, not revoked)
  - For T5 artifacts, verifies fresh authentication
  - Checks fatigue score and refuses if too high (CT-T5 mitigation)
  - Constructs an AttestationRequest with the reviewer's personal signer
  - Requests the attestation via the AttestationService

The submitter does NOT directly sign. It uses the personal signer via
the AttestationService, ensuring all signatures go through the audited
trust spine.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from cogtrust.attestations import (
    Attestation,
    AttestationRequest,
    AttestationType,
)
from cogtrust.lineage import LineageStore
from cogtrust.reviewer_ui.session import ReviewerSession, SessionState
from cogtrust.service import AttestationService, AttestationServiceError
from cogtrust.tiers import TierRegistry


class Verdict(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_CHANGES = "needs_changes"


@dataclass
class ReviewDecision:
    target_artifact_id: str
    verdict: Verdict
    comments: str  # may be empty; hashed before persistence
    items_inspected: list[str]
    decision_started_at: float
    decision_completed_at: float


@dataclass
class SubmissionResult:
    success: bool
    attestation: Optional[Attestation]
    refusal_reason: Optional[str]
    fatigue_score: float
    review_duration_ms: float


# Per CT-T5 — refuse if fatigue too high.
FATIGUE_REFUSAL_THRESHOLD = 0.7


class ReviewSubmitter:
    """
    Validates and submits a reviewer's decision as a personal-signed
    review attestation.

    Note: this submitter uses a *per-review* AttestationService instance
    constructed with the reviewer's personal signer. In production, the
    AttestationService for personal-signing is a separate deployment
    from the service-signing instance; pass it in here.
    """

    def __init__(
        self,
        lineage: LineageStore,
        tier_registry: TierRegistry,
        # Factory that builds an AttestationService with a given signer.
        # In production, this is the personal-signing service endpoint
        # that authenticates the reviewer and uses their key.
        service_factory,
    ) -> None:
        self._lineage = lineage
        self._tier_registry = tier_registry
        self._service_factory = service_factory

    def submit(
        self,
        session: ReviewerSession,
        decision: ReviewDecision,
    ) -> SubmissionResult:
        review_duration_ms = (
            (decision.decision_completed_at - decision.decision_started_at)
            * 1000.0
        )
        fatigue = session.fatigue_score()

        # 1. Session state check.
        if session.state == SessionState.REVOKED:
            return SubmissionResult(
                success=False,
                attestation=None,
                refusal_reason="session_revoked",
                fatigue_score=fatigue,
                review_duration_ms=review_duration_ms,
            )
        if session.state == SessionState.EXPIRED:
            return SubmissionResult(
                success=False,
                attestation=None,
                refusal_reason="session_expired",
                fatigue_score=fatigue,
                review_duration_ms=review_duration_ms,
            )

        # 2. Target artifact must exist and be a generation attestation.
        target = self._lineage.get(decision.target_artifact_id)
        if target is None:
            return SubmissionResult(
                success=False,
                attestation=None,
                refusal_reason="target_artifact_not_found",
                fatigue_score=fatigue,
                review_duration_ms=review_duration_ms,
            )
        if target.type != AttestationType.GENERATION:
            return SubmissionResult(
                success=False,
                attestation=None,
                refusal_reason="target_is_not_generation",
                fatigue_score=fatigue,
                review_duration_ms=review_duration_ms,
            )

        tier_req = self._tier_registry.requirements_for(target.tier)

        # 3. Tier-required authentication recency.
        if tier_req.reviewer_auth_kind == "personal_fresh":
            if not session.is_fresh_authenticated():
                return SubmissionResult(
                    success=False,
                    attestation=None,
                    refusal_reason="reauth_required_for_tier_5",
                    fatigue_score=fatigue,
                    review_duration_ms=review_duration_ms,
                )

        # 4. Fatigue check (CT-T5 mitigation).
        if fatigue >= FATIGUE_REFUSAL_THRESHOLD:
            return SubmissionResult(
                success=False,
                attestation=None,
                refusal_reason=f"fatigue_score_too_high:{fatigue:.2f}",
                fatigue_score=fatigue,
                review_duration_ms=review_duration_ms,
            )

        # 5. Build and submit the attestation request.
        comments_hash = (
            "sha256:" + hashlib.sha256(decision.comments.encode("utf-8")).hexdigest()
            if decision.comments
            else "sha256:" + "0" * 64
        )

        request = AttestationRequest(
            type=AttestationType.REVIEW,
            subject={
                "reviewer_id": session.reviewer_id,
                "target_artifact": decision.target_artifact_id,
                "verdict": decision.verdict.value,
                "comments_hash": comments_hash,
                "review_duration_ms": review_duration_ms,
                "items_inspected": list(decision.items_inspected),
            },
            artifact_class=target.artifact_class,
            intent_root_ref=target.intent_root_ref,
            predecessor_refs=[decision.target_artifact_id],
        )

        # The service is constructed with the reviewer's personal signer.
        service = self._service_factory(session.personal_signer)

        try:
            att = service.issue(request)
        except AttestationServiceError as exc:
            return SubmissionResult(
                success=False,
                attestation=None,
                refusal_reason=f"service_denied:{exc}",
                fatigue_score=fatigue,
                review_duration_ms=review_duration_ms,
            )

        # Record on session.
        session.record_review(review_duration_ms)

        return SubmissionResult(
            success=True,
            attestation=att,
            refusal_reason=None,
            fatigue_score=fatigue,
            review_duration_ms=review_duration_ms,
        )

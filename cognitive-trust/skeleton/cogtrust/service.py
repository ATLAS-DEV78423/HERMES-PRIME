"""
Attestation Service: the one entry point for issuing attestations.

Deterministic. No LLM in critical path (CT-I7).
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Optional

from cogtrust.attestations import (
    Attestation,
    AttestationRequest,
    AttestationType,
    canonical_payload_for_signing,
    new_attestation_id,
    utc_now_iso,
)
from cogtrust.lineage import LineageStore
from cogtrust.signing import Signer
from cogtrust.tiers import TierRegistry

logger = logging.getLogger("cogtrust.service")


class AttestationServiceError(Exception):
    """Service-level error (policy denial, malformed request, etc.)."""


class AttestationService:
    """
    The single signing oracle. Validates requests, calls the signer,
    records in lineage. All in a deterministic critical path.
    """

    def __init__(
        self,
        signer: Signer,
        lineage: LineageStore,
        tier_registry: TierRegistry,
        policy_version: str = "1.0",
        schema_version: str = "1.0",
    ) -> None:
        self._signer = signer
        self._lineage = lineage
        self._tier_registry = tier_registry
        self._policy_version = policy_version
        self._schema_version = schema_version
        self._lock = threading.Lock()

    def issue(self, request: AttestationRequest) -> Attestation:
        """
        Issue an attestation in response to a validated request.
        Raises AttestationServiceError on policy violation.
        """
        # Determine tier.
        tier = self._tier_registry.tier_of(request.artifact_class)
        tier_req = self._tier_registry.requirements_for(tier)

        # Validate intent root for non-root types.
        if request.type != AttestationType.INTENT_ROOT:
            if not request.intent_root_ref:
                raise AttestationServiceError(
                    "intent_root_ref is required for non-root attestations"
                )
            intent = self._lineage.get(request.intent_root_ref)
            if intent is None:
                raise AttestationServiceError(
                    f"intent_root {request.intent_root_ref} not found"
                )
            if intent.type != AttestationType.INTENT_ROOT:
                raise AttestationServiceError(
                    f"reference {request.intent_root_ref} is not an intent_root"
                )
            # Intent root freshness for high tiers.
            if tier >= 4 and intent.issued_at:
                intent_age_seconds = (
                    datetime.now(timezone.utc)
                    - datetime.fromisoformat(intent.issued_at)
                ).total_seconds()
                if intent_age_seconds > tier_req.intent_root_max_age_seconds:
                    raise AttestationServiceError(
                        f"intent_root too old for tier {tier}: "
                        f"{intent_age_seconds:.0f}s > "
                        f"{tier_req.intent_root_max_age_seconds}s"
                    )

        # Validate predecessors exist.
        for pred_id in request.predecessor_refs:
            if self._lineage.get(pred_id) is None:
                raise AttestationServiceError(
                    f"predecessor {pred_id} not in lineage"
                )

        # Tier-specific ceremony validation (per attestation type).
        self._validate_ceremony(request, tier, tier_req)

        # Construct attestation.
        att_id = new_attestation_id()
        issued_at = utc_now_iso()

        att_dict = {
            "attestation_id": att_id,
            "type": request.type.value,
            "schema_version": self._schema_version,
            "issuer": {
                "identity": self._signer.identity,
                "kind": self._signer.kind,
                "cert_chain": self._signer.cert_chain,
            },
            "subject": request.subject,
            "context": {
                "intent_root_ref": request.intent_root_ref,
                "predecessor_refs": list(request.predecessor_refs),
                "artifact_class": request.artifact_class,
                "tier": tier,
            },
            "subject_hashes": dict(request.subject_hashes),
            "issued_at": issued_at,
            "expires_at": request.expires_at,
            "not_before": request.not_before,
            "policy_assertion": {
                "policies_satisfied": ["schema", "predecessors_exist", "tier_match"],
                "policy_version": self._policy_version,
            },
            # signature placeholder; computed next
            "signature": {"algorithm": self._signer.algorithm, "value": ""},
        }

        payload = canonical_payload_for_signing(att_dict)
        signature_value = self._signer.sign(payload)
        att_dict["signature"]["value"] = signature_value

        att = Attestation(
            attestation_id=att_id,
            type=request.type,
            schema_version=self._schema_version,
            issuer_identity=self._signer.identity,
            issuer_kind=self._signer.kind,
            issuer_cert_chain=list(self._signer.cert_chain),
            subject=dict(request.subject),
            artifact_class=request.artifact_class,
            intent_root_ref=request.intent_root_ref,
            predecessor_refs=list(request.predecessor_refs),
            subject_hashes=dict(request.subject_hashes),
            issued_at=issued_at,
            expires_at=request.expires_at,
            not_before=request.not_before,
            policies_satisfied=["schema", "predecessors_exist", "tier_match"],
            policy_version=self._policy_version,
            tier=tier,
            signature_algorithm=self._signer.algorithm,
            signature_value=signature_value,
        )

        # Atomically append to lineage.
        with self._lock:
            self._lineage.append(att)

        logger.info(
            "issued %s attestation %s (tier %d) for class %s",
            request.type.value,
            att_id,
            tier,
            request.artifact_class,
        )
        return att

    def _validate_ceremony(
        self,
        request: AttestationRequest,
        tier: int,
        tier_req,
    ) -> None:
        """
        Enforce that ceremony requirements are met for tier-specific
        attestation types (review/approval/execution).
        """
        # For approval attestations, check tier-specific requirements.
        if request.type == AttestationType.APPROVAL:
            # Count review attestations among predecessors.
            review_count = 0
            reviewer_ids: set[str] = set()
            for pred_id in request.predecessor_refs:
                pred = self._lineage.get(pred_id)
                if pred and pred.type == AttestationType.REVIEW:
                    review_count += 1
                    reviewer_ids.add(pred.subject.get("reviewer_id", ""))

            if tier_req.review_required and review_count < tier_req.min_reviewers:
                raise AttestationServiceError(
                    f"tier {tier} requires {tier_req.min_reviewers} "
                    f"reviewer attestations; got {review_count}"
                )

            if (
                tier_req.approver_distinct_from_reviewer
                and request.subject.get("approver_id") in reviewer_ids
            ):
                raise AttestationServiceError(
                    f"tier {tier} requires approver distinct from reviewers"
                )

        # For review attestations at high tier, check issuer kind.
        if request.type == AttestationType.REVIEW:
            if tier_req.reviewer_auth_kind == "personal" and self._signer.kind != "personal":
                raise AttestationServiceError(
                    f"tier {tier} requires personal-key reviewer attestation"
                )
            if tier_req.reviewer_auth_kind == "personal_fresh" and self._signer.kind != "personal":
                raise AttestationServiceError(
                    f"tier {tier} requires personal-fresh-key reviewer attestation"
                )

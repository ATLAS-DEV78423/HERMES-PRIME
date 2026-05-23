"""
Attestation envelope, types, and canonical-form serialization.

The envelope is fixed across all attestation types. Type-specific payload
sits in `subject`. Canonical serialization is what gets signed.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class AttestationType(str, Enum):
    INTENT_ROOT = "intent_root"
    RETRIEVAL = "retrieval"
    GENERATION = "generation"
    VALIDATION = "validation"
    REVIEW = "review"
    APPROVAL = "approval"
    EXECUTION = "execution"
    REVOCATION = "revocation"
    DERIVATIVE_REVOCATION = "derivative_revocation"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_attestation_id() -> str:
    return f"att_{uuid.uuid4().hex[:16]}"


@dataclass
class AttestationRequest:
    """A request to issue an attestation. Validated by the service."""

    type: AttestationType
    subject: dict[str, Any]
    artifact_class: str
    intent_root_ref: Optional[str]
    predecessor_refs: list[str] = field(default_factory=list)
    subject_hashes: dict[str, str] = field(default_factory=dict)
    expires_at: Optional[str] = None
    not_before: Optional[str] = None
    requester_identity: str = ""  # set by service from client auth

    def __post_init__(self) -> None:
        if not isinstance(self.type, AttestationType):
            raise ValueError(f"type must be AttestationType, got {type(self.type)}")
        # Intent root has no intent_root_ref; everything else must have one.
        if self.type == AttestationType.INTENT_ROOT:
            if self.intent_root_ref is not None:
                raise ValueError("intent_root attestation may not reference intent root")
        else:
            if not self.intent_root_ref:
                raise ValueError(
                    f"{self.type.value} attestation requires intent_root_ref"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "subject": self.subject,
            "artifact_class": self.artifact_class,
            "intent_root_ref": self.intent_root_ref,
            "predecessor_refs": list(self.predecessor_refs),
            "subject_hashes": dict(self.subject_hashes),
            "expires_at": self.expires_at,
            "not_before": self.not_before,
            "requester_identity": self.requester_identity,
        }


@dataclass
class Attestation:
    """A signed attestation."""

    attestation_id: str
    type: AttestationType
    schema_version: str
    issuer_identity: str
    issuer_kind: str  # "service" | "personal"
    issuer_cert_chain: list[str]
    subject: dict[str, Any]
    artifact_class: str
    intent_root_ref: Optional[str]
    predecessor_refs: list[str]
    subject_hashes: dict[str, str]
    issued_at: str
    expires_at: Optional[str]
    not_before: Optional[str]
    policies_satisfied: list[str]
    policy_version: str
    tier: int
    signature_algorithm: str
    signature_value: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "attestation_id": self.attestation_id,
            "type": self.type.value,
            "schema_version": self.schema_version,
            "issuer": {
                "identity": self.issuer_identity,
                "kind": self.issuer_kind,
                "cert_chain": list(self.issuer_cert_chain),
            },
            "subject": self.subject,
            "context": {
                "intent_root_ref": self.intent_root_ref,
                "predecessor_refs": list(self.predecessor_refs),
                "artifact_class": self.artifact_class,
                "tier": self.tier,
            },
            "subject_hashes": dict(self.subject_hashes),
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "not_before": self.not_before,
            "policy_assertion": {
                "policies_satisfied": list(self.policies_satisfied),
                "policy_version": self.policy_version,
            },
            "signature": {
                "algorithm": self.signature_algorithm,
                "value": self.signature_value,
            },
        }


def canonical_payload_for_signing(att_dict: dict[str, Any]) -> bytes:
    """
    Produce the canonical-form bytes that get signed.

    Rules:
      - JSON, sorted keys, no whitespace
      - Signature field is omitted (it's what we're computing)
      - All other fields included (attestation_id is part of the signed payload)
    """
    payload = {k: v for k, v in att_dict.items() if k != "signature"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def hash_payload(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()

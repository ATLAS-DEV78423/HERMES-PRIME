"""
Cognitive Trust reference implementation.

The deliberately-small set of primitives needed to build provenance into
an AI agent system. Most of the value is in the conventions; the code
is just enough to make the conventions executable.
"""

from cogtrust.attestations import (
    Attestation,
    AttestationType,
    AttestationRequest,
)
from cogtrust.lineage import LineageStore
from cogtrust.revocation import RevocationIndex, RevocationCascade
from cogtrust.service import AttestationService
from cogtrust.signing import Ed25519Signer, Signer
from cogtrust.tiers import TierRegistry, TierRequirements
from cogtrust.verification import TrustStatus, Verifier

__version__ = "0.1.0"

__all__ = [
    "Attestation",
    "AttestationType",
    "AttestationRequest",
    "AttestationService",
    "Ed25519Signer",
    "LineageStore",
    "RevocationCascade",
    "RevocationIndex",
    "Signer",
    "TierRegistry",
    "TierRequirements",
    "TrustStatus",
    "Verifier",
]

"""
Reviewer UI: operator-facing component where humans attest to artifacts.

This is the only place in Cognitive Trust where a human cryptographic
signature is produced. WebAuthn / hardware token / personal-KMS-key
authentication is required for tier 4+ per CT-I10.

The skeleton here provides:
  - ReviewerSession: server-side state for a reviewer's authenticated session
  - ArtifactPresenter: assembles the data shown to the reviewer
  - ReviewDecision: the structured input the reviewer produces
  - ReviewSubmitter: validates the decision, requests the attestation

A web framework wires these into HTTP endpoints. WebAuthn-specific code
is left as a deployment concern.
"""

from cogtrust.reviewer_ui.presenter import ArtifactPresenter, ArtifactView
from cogtrust.reviewer_ui.session import ReviewerSession, SessionState
from cogtrust.reviewer_ui.submitter import (
    ReviewDecision,
    ReviewSubmitter,
    SubmissionResult,
    Verdict,
)

__all__ = [
    "ArtifactPresenter",
    "ArtifactView",
    "ReviewDecision",
    "ReviewerSession",
    "ReviewSubmitter",
    "SessionState",
    "SubmissionResult",
    "Verdict",
]

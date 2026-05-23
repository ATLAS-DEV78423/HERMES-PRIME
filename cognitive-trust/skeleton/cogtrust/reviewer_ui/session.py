"""
Reviewer session state.

A session represents an authenticated reviewer in the UI. Tracks:
  - The reviewer's identity
  - Authentication recency (per CT-I10, T5 requires recent auth)
  - The signer the reviewer attests with (their personal key)
  - Anti-fatigue counters

The web framework owns transport (HTTPS, cookies/JWT). This class is the
business object.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from cogtrust.signing import Signer


class SessionState(str, Enum):
    AUTHENTICATED = "authenticated"
    EXPIRED = "expired"
    REVOKED = "revoked"
    REAUTH_REQUIRED = "reauth_required"


@dataclass
class ReviewerSession:
    """
    Authenticated reviewer session.

    The personal Signer represents the reviewer's hardware token / WebAuthn
    credential / personal KMS key. It must be a 'personal' kind signer
    (per CT-I10).
    """

    reviewer_id: str
    personal_signer: Signer
    authenticated_at: float
    session_ttl_seconds: int = 3600
    fresh_auth_window_seconds: int = 300  # for tier 5 "personal_fresh"

    # Anti-fatigue tracking
    review_count: int = 0
    last_review_at: Optional[float] = None
    decision_latencies_ms: list[float] = field(default_factory=list)
    revoked: bool = False

    def __post_init__(self) -> None:
        if self.personal_signer.kind != "personal":
            raise ValueError(
                "ReviewerSession requires a personal-kind signer "
                f"(got kind={self.personal_signer.kind!r})"
            )

    @property
    def state(self) -> SessionState:
        if self.revoked:
            return SessionState.REVOKED
        age = time.time() - self.authenticated_at
        if age > self.session_ttl_seconds:
            return SessionState.EXPIRED
        return SessionState.AUTHENTICATED

    def is_fresh_authenticated(self) -> bool:
        """True if the reviewer authenticated within the fresh-auth window."""
        if self.state != SessionState.AUTHENTICATED:
            return False
        return (time.time() - self.authenticated_at) <= self.fresh_auth_window_seconds

    def record_review(self, decision_latency_ms: float) -> None:
        self.review_count += 1
        self.last_review_at = time.time()
        self.decision_latencies_ms.append(decision_latency_ms)
        # Keep last 50 samples.
        if len(self.decision_latencies_ms) > 50:
            self.decision_latencies_ms = self.decision_latencies_ms[-50:]

    def fatigue_score(self) -> float:
        """
        Heuristic 0.0..1.0 score. Higher = more fatigued.
        Based on recent decision latency and review density.

        Per CT-T5 mitigation: if score is high, the UI should refuse
        further reviews until cooldown.
        """
        if not self.decision_latencies_ms:
            return 0.0
        recent = self.decision_latencies_ms[-10:]
        avg_ms = sum(recent) / len(recent)
        # < 5s average for a review is suspiciously fast.
        latency_score = max(0.0, min(1.0, (5000.0 - avg_ms) / 5000.0))
        # > 20 reviews per session is suspicious volume.
        volume_score = max(0.0, min(1.0, (self.review_count - 5) / 20.0))
        return max(latency_score, volume_score)

    def revoke(self) -> None:
        self.revoked = True

    def reauthenticate(self) -> None:
        """Refresh authentication time (called after re-auth ceremony)."""
        if self.revoked:
            raise ValueError("cannot re-authenticate a revoked session")
        self.authenticated_at = time.time()

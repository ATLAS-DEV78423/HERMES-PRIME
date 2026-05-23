from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class DepthPolicy:
    max_claims_per_intent: int = 100
    max_total_claims: int = 10000
    max_claim_length: int = 10000
    max_depth_level: int = 3
    gc_retention_days: int = 90
    quarantine_promotion_required: bool = True
    authoritative_only_corroborated: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_claims_per_intent": self.max_claims_per_intent,
            "max_total_claims": self.max_total_claims,
            "max_claim_length": self.max_claim_length,
            "max_depth_level": self.max_depth_level,
            "gc_retention_days": self.gc_retention_days,
            "quarantine_promotion_required": self.quarantine_promotion_required,
            "authoritative_only_corroborated": self.authoritative_only_corroborated,
        }

    def check_claim_allowed(
        self,
        claim_text: str,
        current_claims_for_intent: int,
        total_claims: int,
    ) -> tuple[bool, str]:
        if len(claim_text) > self.max_claim_length:
            return False, f"claim exceeds max length of {self.max_claim_length}"
        if current_claims_for_intent >= self.max_claims_per_intent:
            return False, f"intent root exceeds max claims of {self.max_claims_per_intent}"
        if total_claims >= self.max_total_claims:
            return False, f"total claims exceeds max of {self.max_total_claims}"
        return True, ""

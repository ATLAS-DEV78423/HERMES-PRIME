"""
Tier registry: which artifact class is which tier, what ceremony each requires.

This is policy data, not request data. Per CT-I8 and CT-T9 defense:
requests cannot self-classify; classification is derived from registry.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TierRequirements:
    """The ceremony required for an attestation at this tier."""

    tier: int
    min_validations: int
    review_required: bool
    min_reviewers: int  # 0 unless review_required
    approver_distinct_from_reviewer: bool
    multi_party_approval: bool  # True for tier 5
    approval_window_seconds: int
    cooldown_seconds: int  # between approval and execution
    intent_root_max_age_seconds: int
    reviewer_auth_kind: str  # "session" | "personal" | "personal_fresh"


# Default tier definitions per TRUST_TIERS.md
DEFAULT_TIER_REQUIREMENTS: dict[int, TierRequirements] = {
    0: TierRequirements(
        tier=0,
        min_validations=0,
        review_required=False,
        min_reviewers=0,
        approver_distinct_from_reviewer=False,
        multi_party_approval=False,
        approval_window_seconds=10**9,  # effectively unbounded
        cooldown_seconds=0,
        intent_root_max_age_seconds=10**9,
        reviewer_auth_kind="session",
    ),
    1: TierRequirements(
        tier=1,
        min_validations=0,
        review_required=False,
        min_reviewers=0,
        approver_distinct_from_reviewer=False,
        multi_party_approval=False,
        approval_window_seconds=10**9,
        cooldown_seconds=0,
        intent_root_max_age_seconds=8 * 3600,
        reviewer_auth_kind="session",
    ),
    2: TierRequirements(
        tier=2,
        min_validations=2,  # typecheck + lint
        review_required=False,
        min_reviewers=0,
        approver_distinct_from_reviewer=False,
        multi_party_approval=False,
        approval_window_seconds=8 * 3600,
        cooldown_seconds=0,
        intent_root_max_age_seconds=8 * 3600,
        reviewer_auth_kind="session",
    ),
    3: TierRequirements(
        tier=3,
        min_validations=3,
        review_required=True,
        min_reviewers=1,
        approver_distinct_from_reviewer=False,
        multi_party_approval=False,
        approval_window_seconds=3600,
        cooldown_seconds=0,
        intent_root_max_age_seconds=3600,
        reviewer_auth_kind="session",
    ),
    4: TierRequirements(
        tier=4,
        min_validations=5,
        review_required=True,
        min_reviewers=1,
        approver_distinct_from_reviewer=True,
        multi_party_approval=False,
        approval_window_seconds=1800,
        cooldown_seconds=30,
        intent_root_max_age_seconds=1800,
        reviewer_auth_kind="personal",
    ),
    5: TierRequirements(
        tier=5,
        min_validations=7,
        review_required=True,
        min_reviewers=2,
        approver_distinct_from_reviewer=True,
        multi_party_approval=True,
        approval_window_seconds=600,
        cooldown_seconds=300,
        intent_root_max_age_seconds=60,  # the INC-010 lesson
        reviewer_auth_kind="personal_fresh",
    ),
}


@dataclass
class TierRegistry:
    """Maps artifact classes to tiers. Policy data."""

    _class_to_tier: dict[str, int] = field(default_factory=dict)
    _requirements: dict[int, TierRequirements] = field(
        default_factory=lambda: dict(DEFAULT_TIER_REQUIREMENTS)
    )

    def register(self, artifact_class: str, tier: int) -> None:
        if tier not in self._requirements:
            raise ValueError(f"unknown tier {tier}")
        if artifact_class in self._class_to_tier:
            existing = self._class_to_tier[artifact_class]
            if existing != tier:
                raise ValueError(
                    f"artifact_class '{artifact_class}' already registered "
                    f"at tier {existing}; refusing to silently change to {tier}"
                )
            return  # idempotent
        self._class_to_tier[artifact_class] = tier

    def tier_of(self, artifact_class: str) -> int:
        if artifact_class not in self._class_to_tier:
            raise ValueError(
                f"unknown artifact_class '{artifact_class}'. "
                f"Register it explicitly; classes must not be inferred."
            )
        return self._class_to_tier[artifact_class]

    def requirements_for(self, tier: int) -> TierRequirements:
        return self._requirements[tier]

    def requirements_for_class(self, artifact_class: str) -> TierRequirements:
        return self.requirements_for(self.tier_of(artifact_class))


def default_registry_for_examples() -> TierRegistry:
    """A registry pre-loaded with the example classes from TRUST_TIERS.md."""
    reg = TierRegistry()
    examples = {
        "scratch_note": 0,
        "research_summary": 1,
        "code_explanation": 1,
        "refactor_proposal": 1,
        "code_patch_local": 2,
        "test_addition": 2,
        "git_commit": 3,
        "git_branch_push": 3,
        "pull_request_create": 3,
        "deployment_config_staging": 4,
        "schema_migration_staging": 4,
        "dependency_upgrade": 4,
        "deployment_config_production": 5,
        "schema_migration_production": 5,
        "financial_transaction": 5,
        "outbound_email_external": 5,
        "secrets_rotation": 5,
        # Internal classes used by the system itself:
        "retrieval_report": 1,
        "code_review_summary": 1,
    }
    for cls, tier in examples.items():
        reg.register(cls, tier)
    return reg

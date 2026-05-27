from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from .utils import (
    contains_null_byte,
    contains_shell_meta,
    decode_percent,
    hash_struct,
    is_urn_uuid,
    parse_iso8601,
)
from .utils import scope_prefix


class ActionType(str, Enum):
    FILESYSTEM_READ = "filesystem.read"
    FILESYSTEM_WRITE = "filesystem.write"
    FILESYSTEM_COMMIT = "filesystem.commit"
    EXECUTION_COMMAND = "execution.command"
    MINER_DISPATCH = "miner.dispatch"
    MEMORY_WRITE = "memory.write"
    AGENT_SPAWN = "agent.spawn"
    AGENT_KILL = "agent.kill"
    CAPABILITY_REQUEST = "capability.request"
    SCHEDULING = "scheduling"
    CONFIG_WRITE = "config.write"
    WEB_SEARCH = "web.search"
    WEB_FETCH = "web.fetch"
    BROWSER_NAVIGATE = "browser.navigate"
    BROWSER_CLICK = "browser.click"
    BROWSER_SCROLL = "browser.scroll"
    BROWSER_READ = "browser.read"
    VOICE_SPEAK = "voice.speak"
    VISION_ANALYZE = "vision.analyze"
    IMAGE_GENERATE = "image.generate"
    CODE_EXECUTE = "code.execute"
    SKILLS_READ = "skills.read"
    SKILLS_WRITE = "skills.write"
    KANBAN_READ = "kanban.read"
    KANBAN_WRITE = "kanban.write"
    MCP_CALL = "mcp.call"
    ACP_CONNECT = "acp.connect"
    PLUGIN_MANAGE = "plugin.manage"
    SMART_HOME = "smart.home"
    SPOTIFY_CONTROL = "spotify.control"
    SESSION_SEARCH = "session.search"
    CONTEXT_READ = "context.read"
    MODEL_SWITCH = "model.switch"


class RiskTier(str, Enum):
    T0 = "T0"
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"
    T4 = "T4"
    T5 = "T5"

    @property
    def level(self) -> int:
        return int(self.value[1:])

    @classmethod
    def from_level(cls, level: int) -> "RiskTier":
        return cls(f"T{level}")


class TrustState(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    OBSERVED = "OBSERVED"
    ATTESTED = "ATTESTED"
    VALIDATED = "VALIDATED"
    EXECUTABLE = "EXECUTABLE"
    QUARANTINED = "QUARANTINED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class LifecycleState(str, Enum):
    GENERATED = "generated"
    REVIEWED = "reviewed"
    COMMITTED = "committed"
    REVOKED = "revoked"


class MemoryTier(str, Enum):
    QUARANTINE = "quarantine"
    AUTHORITATIVE = "authoritative"


class MemoryOperation(str, Enum):
    WRITE = "memory.write"
    READ = "memory.read"
    LIST = "memory.list"
    RECALL = "memory.recall"
    REVOKE = "memory.revoke"
    GC = "memory.gc"


def _require_urn_uuid(value: str, field_name: str) -> None:
    if not is_urn_uuid(value):
        raise ValueError(f"{field_name} must be a valid urn:uuid value")


def _validate_scope_text(value: str, field_name: str = "scope") -> None:
    if contains_null_byte(value):
        raise ValueError(f"{field_name} must not contain null bytes")
    if contains_shell_meta(value):
        raise ValueError(f"{field_name} must not contain shell metacharacters")
    if ".." in decode_percent(value):
        raise ValueError(f"{field_name} must not contain traversal sequences")


def _ensure_future_iso(value: str, field_name: str) -> None:
    parse_iso8601(value)


@dataclass(frozen=True)
class IntentRoot:
    intent_root: str
    scope: str
    issued_to: str
    issued_at: str
    expires_at: str
    signature: str

    def __post_init__(self) -> None:
        if not self.intent_root:
            raise ValueError("intent_root must not be empty")
        _require_urn_uuid(self.intent_root, "intent_root")
        _validate_scope_text(self.scope, "scope")
        _ensure_future_iso(self.issued_at, "issued_at")
        _ensure_future_iso(self.expires_at, "expires_at")
        if not self.signature:
            raise ValueError("signature must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent_root": self.intent_root,
            "scope": self.scope,
            "issued_to": self.issued_to,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "signature": self.signature,
        }


@dataclass
class ActionProposal:
    action_id: str
    action_type: ActionType | str
    scope: str
    risk_tier: RiskTier | str
    intent_root: str
    capability: str
    proposed_at: str
    parameters: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.action_id:
            raise ValueError("action_id must not be empty")
        _require_urn_uuid(self.action_id, "action_id")
        if not isinstance(self.action_type, ActionType):
            self.action_type = ActionType(self.action_type)
        if not isinstance(self.risk_tier, RiskTier):
            self.risk_tier = RiskTier(self.risk_tier)
        _validate_scope_text(self.scope)
        _require_urn_uuid(self.intent_root, "intent_root")
        if not self.capability:
            raise ValueError("capability must not be empty")
        _ensure_future_iso(self.proposed_at, "proposed_at")

    def normalized_scope(self) -> str:
        return str(Path(scope_prefix(self.scope)).resolve())

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action_type": self.action_type.value,
            "scope": self.scope,
            "risk_tier": self.risk_tier.value,
            "intent_root": self.intent_root,
            "capability": self.capability,
            "proposed_at": self.proposed_at,
            "parameters": self.parameters,
        }


@dataclass
class SentinelDecision:
    decision_id: str
    timestamp: str
    action_id: str
    permitted: bool
    risk_tier: Optional[RiskTier | str]
    policy_rule: Optional[str]
    blocking_layer: Optional[int]
    denial_reason: Optional[str]
    advisory_signals: list[str] = field(default_factory=list)
    consent_required: Optional[bool] = None
    audit_written: bool = True

    def __post_init__(self) -> None:
        if not self.decision_id:
            raise ValueError("decision_id must not be empty")
        _require_urn_uuid(self.decision_id, "decision_id")
        _ensure_future_iso(self.timestamp, "timestamp")
        _require_urn_uuid(self.action_id, "action_id")
        if self.risk_tier is not None and not isinstance(self.risk_tier, RiskTier):
            self.risk_tier = RiskTier(self.risk_tier)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "timestamp": self.timestamp,
            "action_id": self.action_id,
            "permitted": self.permitted,
            "risk_tier": None if self.risk_tier is None else self.risk_tier.value,
            "policy_rule": self.policy_rule,
            "blocking_layer": self.blocking_layer,
            "denial_reason": self.denial_reason,
            "advisory_signals": list(self.advisory_signals),
            "consent_required": self.consent_required,
            "audit_written": self.audit_written,
        }


@dataclass
class CapabilityToken:
    token_id: str
    capability: str
    scope: str
    actions: list[str]
    risk_tier_ceiling: RiskTier | str
    expires_at: str
    intent_root: str
    issued_to: str
    issued_at: str
    nonce: str
    signature: str

    def __post_init__(self) -> None:
        if not self.token_id:
            raise ValueError("token_id must not be empty")
        _require_urn_uuid(self.token_id, "token_id")
        _validate_scope_text(self.scope)
        if not isinstance(self.risk_tier_ceiling, RiskTier):
            self.risk_tier_ceiling = RiskTier(self.risk_tier_ceiling)
        _ensure_future_iso(self.expires_at, "expires_at")
        _require_urn_uuid(self.intent_root, "intent_root")
        _ensure_future_iso(self.issued_at, "issued_at")
        if not self.nonce:
            raise ValueError("nonce must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "token_id": self.token_id,
            "capability": self.capability,
            "scope": self.scope,
            "actions": list(self.actions),
            "risk_tier_ceiling": self.risk_tier_ceiling.value,
            "expires_at": self.expires_at,
            "intent_root": self.intent_root,
            "issued_to": self.issued_to,
            "issued_at": self.issued_at,
            "nonce": self.nonce,
            "signature": self.signature,
        }


@dataclass
class ExaminedFile:
    path: str
    hash: str
    size_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "hash": self.hash, "size_bytes": self.size_bytes}


@dataclass
class MinerAttestation:
    attestation_id: str
    miner_id: str
    miner_type: str
    miner_version: str
    scan_scope: str
    scan_time: str
    duration_ms: int
    files_examined: list[ExaminedFile] = field(default_factory=list)
    results: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    content_summary_hash: str = ""
    signature: str = ""
    parser_backend: str = "fallback"

    def __post_init__(self) -> None:
        if not self.attestation_id:
            raise ValueError("attestation_id must not be empty")
        _require_urn_uuid(self.attestation_id, "attestation_id")
        _validate_scope_text(self.scan_scope)
        _ensure_future_iso(self.scan_time, "scan_time")
        if not self.content_summary_hash:
            self.content_summary_hash = hash_struct(self.results)
        if not self.signature:
            raise ValueError("signature must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "attestation_id": self.attestation_id,
            "miner_id": self.miner_id,
            "miner_type": self.miner_type,
            "miner_version": self.miner_version,
            "parser_backend": self.parser_backend,
            "scan_scope": self.scan_scope,
            "scan_time": self.scan_time,
            "duration_ms": self.duration_ms,
            "files_examined": [file.to_dict() for file in self.files_examined],
            "results": list(self.results),
            "confidence": self.confidence,
            "content_summary_hash": self.content_summary_hash,
            "signature": self.signature,
        }


@dataclass
class MemoryClaim:
    fact_id: str
    claim: str
    source: dict[str, Any]
    epistemic_confidence: float
    verification_status: str
    source_trust: str
    timestamp: str
    trust_state: TrustState | str = TrustState.UNVERIFIED
    tier: MemoryTier | str = MemoryTier.QUARANTINE
    contradictions: list[dict[str, Any]] = field(default_factory=list)
    intent_root: str = ""

    def __post_init__(self) -> None:
        if not self.fact_id:
            raise ValueError("fact_id must not be empty")
        _require_urn_uuid(self.fact_id, "fact_id")
        _ensure_future_iso(self.timestamp, "timestamp")
        if not isinstance(self.trust_state, TrustState):
            self.trust_state = TrustState(self.trust_state)
        if not isinstance(self.tier, MemoryTier):
            self.tier = MemoryTier(self.tier)
        if self.intent_root:
            _require_urn_uuid(self.intent_root, "intent_root")

    def to_dict(self) -> dict[str, Any]:
        return {
            "fact_id": self.fact_id,
            "claim": self.claim,
            "source": self.source,
            "epistemic_confidence": self.epistemic_confidence,
            "verification_status": self.verification_status,
            "source_trust": self.source_trust,
            "timestamp": self.timestamp,
            "trust_state": self.trust_state.value,
            "tier": self.tier.value,
            "contradictions": list(self.contradictions),
            "intent_root": self.intent_root,
        }


@dataclass
class ProvenanceAttestation:
    attestation_id: str
    artifact_hash: str
    artifact_type: str
    generated_by: str
    model_id: str
    intent_root: str
    parent_attestation_ids: list[str]
    input_attestation_ids: list[str]
    generated_at: str
    lifecycle_state: LifecycleState | str
    signature: str

    def __post_init__(self) -> None:
        if not self.attestation_id:
            raise ValueError("attestation_id must not be empty")
        _require_urn_uuid(self.attestation_id, "attestation_id")
        _require_urn_uuid(self.intent_root, "intent_root")
        _ensure_future_iso(self.generated_at, "generated_at")
        if not isinstance(self.lifecycle_state, LifecycleState):
            self.lifecycle_state = LifecycleState(self.lifecycle_state)

    def to_dict(self) -> dict[str, Any]:
        return {
            "attestation_id": self.attestation_id,
            "artifact_hash": self.artifact_hash,
            "artifact_type": self.artifact_type,
            "generated_by": self.generated_by,
            "model_id": self.model_id,
            "intent_root": self.intent_root,
            "parent_attestation_ids": list(self.parent_attestation_ids),
            "input_attestation_ids": list(self.input_attestation_ids),
            "generated_at": self.generated_at,
            "lifecycle_state": self.lifecycle_state.value,
            "signature": self.signature,
        }


@dataclass
class InferenceAttestation:
    """Attestation of an LLM inference call for auditability."""

    attestation_id: str
    model: str
    timestamp: str
    request_hash: str  # Hash of the full request
    response_hash: str  # Hash of the response
    tokens_used: int
    latency_ms: float
    finish_reason: str
    prompt_hash: str  # Hash of system + user prompt
    signature: str = ""

    def __post_init__(self) -> None:
        if not self.attestation_id:
            raise ValueError("attestation_id must not be empty")
        _require_urn_uuid(self.attestation_id, "attestation_id")
        _ensure_future_iso(self.timestamp, "timestamp")
        if not self.signature:
            raise ValueError("signature must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "attestation_id": self.attestation_id,
            "model": self.model,
            "timestamp": self.timestamp,
            "request_hash": self.request_hash,
            "response_hash": self.response_hash,
            "tokens_used": self.tokens_used,
            "latency_ms": self.latency_ms,
            "finish_reason": self.finish_reason,
            "prompt_hash": self.prompt_hash,
            "signature": self.signature,
        }


@dataclass
class MemoryAttestation:
    attestation_id: str
    fact_id: str
    intent_root: str
    claim_hash: str
    source: str
    generated_at: str
    signature: str

    def __post_init__(self) -> None:
        _require_urn_uuid(self.attestation_id, "attestation_id")
        _require_urn_uuid(self.fact_id, "fact_id")
        _require_urn_uuid(self.intent_root, "intent_root")

    def to_dict(self) -> dict[str, Any]:
        return {
            "attestation_id": self.attestation_id,
            "fact_id": self.fact_id,
            "intent_root": self.intent_root,
            "claim_hash": self.claim_hash,
            "source": self.source,
            "generated_at": self.generated_at,
            "signature": self.signature,
        }


@dataclass
class AuditTrace:
    trace_id: str
    trace_type: str
    created_at: str
    workspace_root: str
    intent_root: str = ""
    prompt: str = ""
    classification: dict[str, Any] = field(default_factory=dict)
    pattern_matches: list[dict[str, Any]] = field(default_factory=list)
    augmentation: dict[str, Any] = field(default_factory=dict)
    retrieval: list[dict[str, Any]] = field(default_factory=list)
    action: dict[str, Any] = field(default_factory=dict)
    decision: dict[str, Any] = field(default_factory=dict)
    mutation: dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    replayable: bool = True

    def __post_init__(self) -> None:
        if not self.trace_id:
            raise ValueError("trace_id must not be empty")
        _require_urn_uuid(self.trace_id, "trace_id")
        _ensure_future_iso(self.created_at, "created_at")
        if self.intent_root:
            _require_urn_uuid(self.intent_root, "intent_root")

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "trace_type": self.trace_type,
            "created_at": self.created_at,
            "workspace_root": self.workspace_root,
            "intent_root": self.intent_root,
            "prompt": self.prompt,
            "classification": self.classification,
            "pattern_matches": list(self.pattern_matches),
            "augmentation": self.augmentation,
            "retrieval": list(self.retrieval),
            "action": self.action,
            "decision": self.decision,
            "mutation": self.mutation,
            "summary": self.summary,
            "replayable": self.replayable,
        }


@dataclass
class PatternClassification:
    classification_id: str
    task_types: list[str]
    domain: str
    recommended_pattern_tags: list[str]
    confidence: float
    classified_at: str

    def __post_init__(self) -> None:
        if not self.classification_id:
            raise ValueError("classification_id must not be empty")
        _require_urn_uuid(self.classification_id, "classification_id")
        _ensure_future_iso(self.classified_at, "classified_at")

    def to_dict(self) -> dict[str, Any]:
        return {
            "classification_id": self.classification_id,
            "task_types": list(self.task_types),
            "domain": self.domain,
            "recommended_pattern_tags": list(self.recommended_pattern_tags),
            "confidence": self.confidence,
            "classified_at": self.classified_at,
        }


@dataclass
class FabricPatternMatch:
    match_id: str
    pattern_name: str
    pattern_hash: str
    fabric_version: str
    retrieval_time: str
    confidence: float
    reasoning_style: list[str]
    required_checks: list[str]
    output_structure: list[str] | dict[str, Any]
    tags: list[str]
    authority: str = "heuristic_guidance_only"

    def __post_init__(self) -> None:
        if not self.match_id:
            raise ValueError("match_id must not be empty")
        _require_urn_uuid(self.match_id, "match_id")
        _ensure_future_iso(self.retrieval_time, "retrieval_time")
        if self.authority != "heuristic_guidance_only":
            raise ValueError("authority must be heuristic_guidance_only")

    def to_dict(self) -> dict[str, Any]:
        return {
            "match_id": self.match_id,
            "pattern_name": self.pattern_name,
            "pattern_hash": self.pattern_hash,
            "fabric_version": self.fabric_version,
            "retrieval_time": self.retrieval_time,
            "confidence": self.confidence,
            "reasoning_style": list(self.reasoning_style),
            "required_checks": list(self.required_checks),
            "output_structure": self.output_structure,
            "tags": list(self.tags),
            "authority": self.authority,
        }


@dataclass
class FabricAugmentation:
    augmentation_id: str
    source_patterns: list[str]
    reasoning_style: list[str]
    required_checks: list[str]
    output_structure: dict[str, Any]
    constraints: list[str]
    authority: str
    generated_at: str
    pattern_hashes: dict[str, str]

    def __post_init__(self) -> None:
        if not self.augmentation_id:
            raise ValueError("augmentation_id must not be empty")
        _require_urn_uuid(self.augmentation_id, "augmentation_id")
        _ensure_future_iso(self.generated_at, "generated_at")
        if self.authority != "heuristic_guidance_only":
            raise ValueError("authority must be heuristic_guidance_only")

    def to_dict(self) -> dict[str, Any]:
        return {
            "augmentation_id": self.augmentation_id,
            "source_patterns": list(self.source_patterns),
            "reasoning_style": list(self.reasoning_style),
            "required_checks": list(self.required_checks),
            "output_structure": self.output_structure,
            "constraints": list(self.constraints),
            "authority": self.authority,
            "generated_at": self.generated_at,
            "pattern_hashes": dict(self.pattern_hashes),
        }


class AgentStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"
    PENDING = "pending"


@dataclass
class AgentNode:
    agent_id: str
    parent_id: str | None
    intent_root: str
    capability_scope: str
    capability_token: str | None
    spawned_by: str | None
    spawned_at: str
    completed_at: str | None
    status: AgentStatus
    depth: int
    task_description: str
    result: dict[str, Any] | None
    attestation: "AgentSpawnAttestation | None"

    def __post_init__(self) -> None:
        _require_urn_uuid(self.agent_id, "agent_id")
        if self.parent_id is not None:
            _require_urn_uuid(self.parent_id, "parent_id")
        _require_urn_uuid(self.intent_root, "intent_root")
        _ensure_future_iso(self.spawned_at, "spawned_at")

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "parent_id": self.parent_id,
            "intent_root": self.intent_root,
            "capability_scope": self.capability_scope,
            "capability_token": self.capability_token,
            "spawned_by": self.spawned_by,
            "spawned_at": self.spawned_at,
            "completed_at": self.completed_at,
            "status": self.status.value,
            "depth": self.depth,
            "task_description": self.task_description,
            "result": self.result,
            "attestation": self.attestation.to_dict() if self.attestation else None,
        }


@dataclass
class AgentSpawnRequest:
    task_description: str
    scope: str
    risk_tier_ceiling: RiskTier
    parent_agent_id: str | None
    max_depth: int
    capability_actions: list[ActionType]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentSpawnAttestation:
    attestation_id: str
    agent_id: str
    spawned_by: str
    intent_root: str
    capability_token_id: str
    spawned_at: str
    policy_hash: str
    signature: str

    def __post_init__(self) -> None:
        _require_urn_uuid(self.attestation_id, "attestation_id")
        _require_urn_uuid(self.agent_id, "agent_id")
        _require_urn_uuid(self.spawned_by, "spawned_by")
        _require_urn_uuid(self.intent_root, "intent_root")
        _ensure_future_iso(self.spawned_at, "spawned_at")

    def to_dict(self) -> dict[str, Any]:
        return {
            "attestation_id": self.attestation_id,
            "agent_id": self.agent_id,
            "spawned_by": self.spawned_by,
            "intent_root": self.intent_root,
            "capability_token_id": self.capability_token_id,
            "spawned_at": self.spawned_at,
            "policy_hash": self.policy_hash,
            "signature": self.signature,
        }


@dataclass
class ExecutionOutcome:
    """Record of an autonomous execution outcome for learning loop."""

    execution_id: str
    task_prompt: str
    action_type: str
    action_scope: str
    approved: bool
    blocking_layer: int | None
    denial_reason: str | None
    parseable: bool
    latency_ms: float
    tokens_used: int
    model: str
    timestamp: str
    outcome_labels: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        _require_urn_uuid(self.execution_id, "execution_id")
        _ensure_future_iso(self.timestamp, "timestamp")

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "task_prompt": self.task_prompt,
            "action_type": self.action_type,
            "action_scope": self.action_scope,
            "approved": self.approved,
            "blocking_layer": self.blocking_layer,
            "denial_reason": self.denial_reason,
            "parseable": self.parseable,
            "latency_ms": self.latency_ms,
            "tokens_used": self.tokens_used,
            "model": self.model,
            "timestamp": self.timestamp,
            "outcome_labels": list(self.outcome_labels),
        }


@dataclass
class LearnedPattern:
    """A pattern extracted by the learning loop from past outcomes."""

    pattern_id: str
    pattern_type: (
        str  # "prompt_instruction", "action_heuristic", "policy_suggestion", "task_pattern"
    )
    content: str
    confidence: float
    source_outcomes: list[str]
    action_types: list[str]
    tags: list[str]
    created_at: str
    last_applied_at: str | None = None
    application_count: int = 0
    success_rate: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "pattern_type": self.pattern_type,
            "content": self.content,
            "confidence": self.confidence,
            "source_outcomes": list(self.source_outcomes),
            "action_types": list(self.action_types),
            "tags": list(self.tags),
            "created_at": self.created_at,
            "last_applied_at": self.last_applied_at,
            "application_count": self.application_count,
            "success_rate": self.success_rate,
        }


def trust_transition_allowed(current: TrustState, nxt: TrustState) -> bool:
    if current == nxt:
        return True
    graph = {
        TrustState.UNVERIFIED: {TrustState.OBSERVED, TrustState.QUARANTINED},
        TrustState.OBSERVED: {TrustState.ATTESTED, TrustState.QUARANTINED},
        TrustState.ATTESTED: {TrustState.VALIDATED, TrustState.QUARANTINED},
        TrustState.VALIDATED: {TrustState.EXECUTABLE, TrustState.QUARANTINED},
        TrustState.EXECUTABLE: {TrustState.REVOKED, TrustState.EXPIRED},
        TrustState.QUARANTINED: {TrustState.REVOKED, TrustState.EXPIRED},
        TrustState.REVOKED: set(),
        TrustState.EXPIRED: set(),
    }
    return nxt in graph[current]

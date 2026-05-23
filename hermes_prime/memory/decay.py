from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from hermes_prime.contracts import MemoryClaim, TrustState
from hermes_prime.memory.base import MemoryBackend, MemorySearchResult

_DEFAULT_RETENTION_DAYS: dict[str, int] = {
    "working": 1,
    "reflective": 30,
    "episodic": 90,
    "semantic": 365,
    "strategic": 0,
    "governance": 0,
}

_TRUST_ORDER: dict[str, int] = {
    "UNVERIFIED": 0,
    "OBSERVED": 1,
    "ATTESTED": 2,
    "VALIDATED": 3,
    "EXECUTABLE": 4,
}


def _trust_score(state: str | TrustState) -> int:
    if isinstance(state, TrustState):
        return _TRUST_ORDER.get(state.value, -1)
    return _TRUST_ORDER.get(state.upper(), -1)


def _memory_type_from_claim(claim: MemoryClaim) -> str:
    if isinstance(claim.source, dict):
        return claim.source.get("memory_type", "episodic")
    return "episodic"


@dataclass
class DecayPolicy:
    retention_days: dict[str, int] = field(default_factory=lambda: dict(_DEFAULT_RETENTION_DAYS))
    unverified_decay_factor: float = 2.0
    immutable_decay_exempt: bool = True
    access_decay_half_life_days: int = 30

    def retention_for(self, memory_type: str) -> int:
        return self.retention_days.get(memory_type, 90)

    def is_exempt(self, claim: MemoryClaim) -> bool:
        if self.immutable_decay_exempt:
            ts = claim.trust_state if isinstance(claim.trust_state, TrustState) else TrustState(claim.trust_state.upper())
            if ts == TrustState.EXECUTABLE:
                return True
            mt = _memory_type_from_claim(claim)
            if mt in ("strategic", "governance"):
                return True
        return False

    def effective_age_ratio(self, claim: MemoryClaim, access_days_since: Optional[int] = None) -> float:
        if self.is_exempt(claim):
            return 0.0
        memory_type = _memory_type_from_claim(claim)
        retention = self.retention_for(memory_type)
        if retention <= 0:
            return 0.0

        now = dt.datetime.now(dt.timezone.utc)
        created = _parse_timestamp(claim.timestamp)
        age_days = (now - created).total_seconds() / 86400.0

        ratio = age_days / retention

        trust_score = _trust_score(claim.trust_state)
        if trust_score == 0:
            ratio *= self.unverified_decay_factor

        if access_days_since is not None and self.access_decay_half_life_days > 0:
            access_ratio = access_days_since / self.access_decay_half_life_days
            ratio *= (1.0 + access_ratio * 0.5)

        return ratio


@dataclass
class DecayResult:
    expired_count: int = 0
    demoted_count: int = 0
    deleted_count: int = 0
    exempt_count: int = 0
    errors: list[str] = field(default_factory=list)


class AccessTracker:
    def __init__(self) -> None:
        self._access_log: dict[str, list[str]] = {}

    def record_access(self, fact_id: str) -> None:
        now = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        if fact_id not in self._access_log:
            self._access_log[fact_id] = []
        self._access_log[fact_id].append(now)

    def get_last_access(self, fact_id: str) -> Optional[str]:
        log = self._access_log.get(fact_id)
        if log:
            return log[-1]
        return None

    def get_access_count(self, fact_id: str, since: Optional[str] = None) -> int:
        log = self._access_log.get(fact_id)
        if not log:
            return 0
        if since is None:
            return len(log)
        since_dt = _parse_timestamp(since)
        return sum(1 for ts in log if _parse_timestamp(ts) >= since_dt)

    def days_since_last_access(self, fact_id: str) -> Optional[int]:
        last = self.get_last_access(fact_id)
        if last is None:
            return None
        last_dt = _parse_timestamp(last)
        now = dt.datetime.now(dt.timezone.utc)
        return int((now - last_dt).total_seconds() / 86400.0)

    def clear(self) -> None:
        self._access_log.clear()


class DecayScheduler:
    def __init__(
        self,
        backend: MemoryBackend,
        policy: Optional[DecayPolicy] = None,
        access_tracker: Optional[AccessTracker] = None,
    ) -> None:
        self.backend = backend
        self.policy = policy or DecayPolicy()
        self.access_tracker = access_tracker

    def run_cycle(self) -> DecayResult:
        result = DecayResult()
        claims = self.backend.list_all()

        for claim in claims:
            try:
                self._process_claim(claim, result)
            except Exception as e:
                result.errors.append(f"error processing {claim.fact_id}: {e}")

        return result

    def _process_claim(self, claim: MemoryClaim, result: DecayResult) -> None:
        if self.policy.is_exempt(claim):
            result.exempt_count += 1
            return

        memory_type = _memory_type_from_claim(claim)
        retention = self.policy.retention_for(memory_type)
        if retention <= 0:
            result.exempt_count += 1
            return

        access_days = None
        if self.access_tracker is not None:
            access_days = self.access_tracker.days_since_last_access(claim.fact_id)

        ratio = self.policy.effective_age_ratio(claim, access_days_since=access_days)

        if ratio < 0.8:
            return

        if ratio >= 1.5 and memory_type in ("working", "reflective"):
            self.backend.delete(claim.fact_id)
            result.deleted_count += 1
            result.expired_count += 1
            return

        if ratio >= 1.0:
            if memory_type in ("episodic", "semantic"):
                current_trust = claim.trust_state if isinstance(claim.trust_state, TrustState) else TrustState(claim.trust_state.upper())
                if current_trust == TrustState.VALIDATED:
                    claim.trust_state = TrustState.OBSERVED
                    self.backend.store(claim)
                    result.demoted_count += 1
                    result.expired_count += 1
                    return

                if current_trust in (TrustState.UNVERIFIED, TrustState.OBSERVED):
                    self.backend.delete(claim.fact_id)
                    result.deleted_count += 1
                    result.expired_count += 1
                    return

            self.backend.delete(claim.fact_id)
            result.deleted_count += 1
            result.expired_count += 1
            return

        if ratio >= 0.8 and memory_type in ("working",):
            current_trust = claim.trust_state if isinstance(claim.trust_state, TrustState) else TrustState(claim.trust_state.upper())
            if current_trust in (TrustState.UNVERIFIED, TrustState.OBSERVED):
                self.backend.delete(claim.fact_id)
                result.deleted_count += 1
                result.expired_count += 1
                return


def _parse_timestamp(ts: str) -> dt.datetime:
    try:
        return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return dt.datetime.now(dt.timezone.utc)

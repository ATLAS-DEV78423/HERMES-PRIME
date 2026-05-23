from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Iterable, Optional, TypeVar

from hermes_prime.contracts import (
    AuditTrace,
    CapabilityToken,
    IntentRoot,
    MemoryClaim,
    MinerAttestation,
    ProvenanceAttestation,
    SentinelDecision,
    TrustState,
    trust_transition_allowed,
)
from hermes_prime.utils import canonical_json, parse_iso8601, utc_now_iso


class TrustStoreError(RuntimeError):
    pass


def _payload(value: Any) -> str:
    if is_dataclass(value):
        value = asdict(value)
    return canonical_json(value)


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True)


def _load(value: str) -> Any:
    return json.loads(value)


class TrustStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self.conn.close()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS intent_roots (
                intent_root TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS capability_tokens (
                token_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS sentinel_decisions (
                decision_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS miner_attestations (
                attestation_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS provenance_attestations (
                attestation_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_traces (
                trace_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS memory_claims (
                fact_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                trust_state TEXT NOT NULL,
                contradiction_payload TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        self.conn.commit()

    def store_intent_root(self, intent_root: IntentRoot) -> None:
        now = utc_now_iso()
        payload = _payload(intent_root)
        self.conn.execute(
            """
            INSERT INTO intent_roots(intent_root, payload, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(intent_root) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at
            """,
            (intent_root.intent_root, payload, now, now),
        )
        self.conn.commit()

    def get_intent_root(self, intent_root_id: str) -> IntentRoot | None:
        row = self.conn.execute(
            "SELECT payload FROM intent_roots WHERE intent_root = ?",
            (intent_root_id,),
        ).fetchone()
        if row is None:
            return None
        data = _load(row["payload"])
        return IntentRoot(**data)

    def store_capability_token(self, token: CapabilityToken) -> None:
        now = utc_now_iso()
        payload = _payload(token)
        self.conn.execute(
            """
            INSERT INTO capability_tokens(token_id, payload, created_at, updated_at, revoked)
            VALUES (?, ?, ?, ?, COALESCE((SELECT revoked FROM capability_tokens WHERE token_id = ?), 0))
            ON CONFLICT(token_id) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at
            """,
            (token.token_id, payload, now, now, token.token_id),
        )
        self.conn.commit()

    def get_capability_token(self, token_id: str) -> CapabilityToken | None:
        row = self.conn.execute(
            "SELECT payload, revoked FROM capability_tokens WHERE token_id = ?",
            (token_id,),
        ).fetchone()
        if row is None or int(row["revoked"]) == 1:
            return None
        return CapabilityToken(**_load(row["payload"]))

    def revoke_capability_token(self, token_id: str) -> None:
        self.conn.execute(
            "UPDATE capability_tokens SET revoked = 1, updated_at = ? WHERE token_id = ?",
            (utc_now_iso(), token_id),
        )
        self.conn.commit()

    def store_decision(self, decision: SentinelDecision) -> None:
        now = utc_now_iso()
        self.conn.execute(
            """
            INSERT INTO sentinel_decisions(decision_id, payload, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(decision_id) DO UPDATE SET payload=excluded.payload
            """,
            (decision.decision_id, _payload(decision), now),
        )
        self.conn.commit()

    def store_miner_attestation(self, attestation: MinerAttestation) -> None:
        now = utc_now_iso()
        self.conn.execute(
            """
            INSERT INTO miner_attestations(attestation_id, payload, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(attestation_id) DO UPDATE SET payload=excluded.payload
            """,
            (attestation.attestation_id, _payload(attestation), now),
        )
        self.conn.commit()

    def store_provenance_attestation(self, attestation: ProvenanceAttestation) -> None:
        now = utc_now_iso()
        self.conn.execute(
            """
            INSERT INTO provenance_attestations(attestation_id, payload, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(attestation_id) DO UPDATE SET payload=excluded.payload
            """,
            (attestation.attestation_id, _payload(attestation), now),
        )
        self.conn.commit()

    def store_audit_trace(self, trace: AuditTrace) -> None:
        self.conn.execute(
            """
            INSERT INTO audit_traces(trace_id, payload, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(trace_id) DO UPDATE SET payload=excluded.payload
            """,
            (trace.trace_id, _payload(trace), trace.created_at),
        )
        self.conn.commit()

    def get_audit_trace(self, trace_id: str) -> AuditTrace | None:
        row = self.conn.execute(
            "SELECT payload FROM audit_traces WHERE trace_id = ?",
            (trace_id,),
        ).fetchone()
        if row is None:
            return None
        return AuditTrace(**_load(row["payload"]))

    def list_audit_traces(self, limit: int = 20) -> list[AuditTrace]:
        rows = self.conn.execute(
            "SELECT payload FROM audit_traces ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [AuditTrace(**_load(row["payload"])) for row in rows]

    def store_memory_claim(self, claim: MemoryClaim) -> None:
        now = utc_now_iso()
        contradictions = _json(claim.contradictions)
        claim_state = claim.trust_state if isinstance(claim.trust_state, TrustState) else TrustState(claim.trust_state)
        if claim.contradictions and claim_state in {TrustState.VALIDATED, TrustState.EXECUTABLE}:
            raise TrustStoreError("contradictory memory claims cannot be promoted")
        existing = self.get_memory_claim(claim.fact_id)
        if existing is not None:
            current_state = existing.trust_state if isinstance(existing.trust_state, TrustState) else TrustState(existing.trust_state)
            next_state = claim_state
            if not trust_transition_allowed(current_state, next_state):
                raise TrustStoreError(
                    f"invalid trust transition {current_state.value} -> {next_state.value}"
                )
        self.conn.execute(
            """
            INSERT INTO memory_claims(fact_id, payload, trust_state, contradiction_payload, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(fact_id) DO UPDATE SET payload=excluded.payload, trust_state=excluded.trust_state, contradiction_payload=excluded.contradiction_payload, updated_at=excluded.updated_at
            """,
            (
                claim.fact_id,
                _payload(claim),
                claim_state.value,
                contradictions,
                now,
                now,
            ),
        )
        self.conn.commit()

    def get_memory_claim(self, fact_id: str) -> MemoryClaim | None:
        row = self.conn.execute(
            "SELECT payload FROM memory_claims WHERE fact_id = ?",
            (fact_id,),
        ).fetchone()
        if row is None:
            return None
        return MemoryClaim(**_load(row["payload"]))

    def promote_memory_claim(self, fact_id: str, trust_state: TrustState) -> MemoryClaim:
        claim = self.get_memory_claim(fact_id)
        if claim is None:
            raise TrustStoreError("memory claim not found")
        current = claim.trust_state if isinstance(claim.trust_state, TrustState) else TrustState(claim.trust_state)
        if not trust_transition_allowed(current, trust_state):
            raise TrustStoreError(f"invalid trust transition {current.value} -> {trust_state.value}")
        claim.trust_state = trust_state
        self.store_memory_claim(claim)
        return claim

    def list_memory_claims(self) -> list[MemoryClaim]:
        rows = self.conn.execute("SELECT payload FROM memory_claims ORDER BY created_at ASC").fetchall()
        return [MemoryClaim(**_load(row["payload"])) for row in rows]

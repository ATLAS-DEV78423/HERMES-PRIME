"""
SQLite-backed lineage store.

Production-grade replacement for the in-memory reference. Append-only,
hash-chained, DAG-validated. Uses SQLite triggers to enforce
immutability at the storage layer (defense in depth beyond app-level
checks).

Tradeoffs vs in-memory:
  + Persistent across restarts
  + Multi-process safe (via SQLite WAL mode)
  + Storage-layer immutability triggers
  - Slower (~100us per append vs ~1us)
  - Single-writer (use Postgres for higher write throughput)

For repos producing > 100 attestations/sec sustained, migrate to
Postgres with append-only constraint + tamper-evident extensions.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from cogtrust.attestations import Attestation, AttestationType
from cogtrust.lineage import LineageError


SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS attestations (
    attestation_id      TEXT PRIMARY KEY,
    type                TEXT NOT NULL,
    schema_version      TEXT NOT NULL,
    issuer_identity     TEXT NOT NULL,
    issuer_kind         TEXT NOT NULL,
    issuer_cert_chain   TEXT NOT NULL,  -- JSON array
    subject             TEXT NOT NULL,  -- JSON object
    artifact_class      TEXT NOT NULL,
    intent_root_ref     TEXT,
    predecessor_refs    TEXT NOT NULL,  -- JSON array
    subject_hashes      TEXT NOT NULL,  -- JSON object
    issued_at           TEXT NOT NULL,
    expires_at          TEXT,
    not_before          TEXT,
    policies_satisfied  TEXT NOT NULL,  -- JSON array
    policy_version      TEXT NOT NULL,
    tier                INTEGER NOT NULL,
    signature_algorithm TEXT NOT NULL,
    signature_value     TEXT NOT NULL,
    inserted_at         INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE INDEX IF NOT EXISTS idx_intent_root ON attestations(intent_root_ref);
CREATE INDEX IF NOT EXISTS idx_type ON attestations(type);
CREATE INDEX IF NOT EXISTS idx_artifact_class ON attestations(artifact_class);

CREATE TABLE IF NOT EXISTS parent_edges (
    child_id  TEXT NOT NULL,
    parent_id TEXT NOT NULL,
    edge_kind TEXT NOT NULL,  -- 'predecessor' | 'intent_root'
    PRIMARY KEY (child_id, parent_id, edge_kind),
    FOREIGN KEY (child_id)  REFERENCES attestations(attestation_id),
    FOREIGN KEY (parent_id) REFERENCES attestations(attestation_id)
);

CREATE INDEX IF NOT EXISTS idx_parent ON parent_edges(parent_id);
CREATE INDEX IF NOT EXISTS idx_child  ON parent_edges(child_id);

CREATE TABLE IF NOT EXISTS hash_chain (
    seq          INTEGER PRIMARY KEY AUTOINCREMENT,
    attestation_id TEXT NOT NULL UNIQUE,
    link_hash    TEXT NOT NULL,
    prev_hash    TEXT NOT NULL,
    FOREIGN KEY (attestation_id) REFERENCES attestations(attestation_id)
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Tamper-evidence: triggers prevent UPDATE and DELETE on append-only tables.
CREATE TRIGGER IF NOT EXISTS no_update_attestations
BEFORE UPDATE ON attestations
BEGIN
    SELECT RAISE(ABORT, 'attestations table is append-only');
END;

CREATE TRIGGER IF NOT EXISTS no_delete_attestations
BEFORE DELETE ON attestations
BEGIN
    SELECT RAISE(ABORT, 'attestations table is append-only');
END;

CREATE TRIGGER IF NOT EXISTS no_update_chain
BEFORE UPDATE ON hash_chain
BEGIN
    SELECT RAISE(ABORT, 'hash_chain table is append-only');
END;

CREATE TRIGGER IF NOT EXISTS no_delete_chain
BEFORE DELETE ON hash_chain
BEGIN
    SELECT RAISE(ABORT, 'hash_chain table is append-only');
END;

CREATE TRIGGER IF NOT EXISTS no_update_parents
BEFORE UPDATE ON parent_edges
BEGIN
    SELECT RAISE(ABORT, 'parent_edges table is append-only');
END;

CREATE TRIGGER IF NOT EXISTS no_delete_parents
BEFORE DELETE ON parent_edges
BEGIN
    SELECT RAISE(ABORT, 'parent_edges table is append-only');
END;
"""


class SqliteLineageStore:
    """
    SQLite-backed implementation of the LineageStore interface.

    Compatible with cogtrust.lineage.LineageStore as a drop-in (same
    public methods). Use this for any deployment beyond unit tests.
    """

    GENESIS_HASH = "sha256:" + "0" * 64

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._db_path = str(db_path)
        # check_same_thread=False because we serialize via our own lock.
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._lock = threading.Lock()
        with self._conn:
            self._conn.executescript(SCHEMA)
            # Record schema version on first use.
            self._conn.execute(
                "INSERT OR IGNORE INTO meta(key, value) VALUES(?, ?)",
                ("schema_version", str(SCHEMA_VERSION)),
            )

    # --- internal helpers ---

    @staticmethod
    def _parents_of(att: Attestation) -> list[tuple[str, str]]:
        """Return list of (parent_id, edge_kind)."""
        parents: list[tuple[str, str]] = [
            (p, "predecessor") for p in att.predecessor_refs
        ]
        if att.intent_root_ref and att.intent_root_ref not in att.predecessor_refs:
            parents.append((att.intent_root_ref, "intent_root"))
        return parents

    @staticmethod
    def _row_to_attestation(row: sqlite3.Row) -> Attestation:
        return Attestation(
            attestation_id=row["attestation_id"],
            type=AttestationType(row["type"]),
            schema_version=row["schema_version"],
            issuer_identity=row["issuer_identity"],
            issuer_kind=row["issuer_kind"],
            issuer_cert_chain=json.loads(row["issuer_cert_chain"]),
            subject=json.loads(row["subject"]),
            artifact_class=row["artifact_class"],
            intent_root_ref=row["intent_root_ref"],
            predecessor_refs=json.loads(row["predecessor_refs"]),
            subject_hashes=json.loads(row["subject_hashes"]),
            issued_at=row["issued_at"],
            expires_at=row["expires_at"],
            not_before=row["not_before"],
            policies_satisfied=json.loads(row["policies_satisfied"]),
            policy_version=row["policy_version"],
            tier=row["tier"],
            signature_algorithm=row["signature_algorithm"],
            signature_value=row["signature_value"],
        )

    @contextmanager
    def _txn(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    # --- mutation ---

    def append(self, att: Attestation) -> str:
        """Append an attestation. Returns chain link hash."""
        with self._txn() as conn:
            # Duplicate check.
            existing = conn.execute(
                "SELECT 1 FROM attestations WHERE attestation_id = ?",
                (att.attestation_id,),
            ).fetchone()
            if existing:
                raise LineageError(
                    f"attestation {att.attestation_id} already exists; "
                    f"lineage is append-only"
                )

            # Predecessor existence.
            for pred_id in att.predecessor_refs:
                row = conn.execute(
                    "SELECT 1 FROM attestations WHERE attestation_id = ?",
                    (pred_id,),
                ).fetchone()
                if not row:
                    raise LineageError(
                        f"predecessor {pred_id} not found in lineage"
                    )

            # Intent root existence (for non-root types).
            if att.intent_root_ref is not None:
                row = conn.execute(
                    "SELECT type FROM attestations WHERE attestation_id = ?",
                    (att.intent_root_ref,),
                ).fetchone()
                if not row:
                    raise LineageError(
                        f"intent root {att.intent_root_ref} not found"
                    )

            # Insert attestation.
            conn.execute(
                """
                INSERT INTO attestations(
                    attestation_id, type, schema_version,
                    issuer_identity, issuer_kind, issuer_cert_chain,
                    subject, artifact_class, intent_root_ref,
                    predecessor_refs, subject_hashes,
                    issued_at, expires_at, not_before,
                    policies_satisfied, policy_version, tier,
                    signature_algorithm, signature_value
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    att.attestation_id,
                    att.type.value,
                    att.schema_version,
                    att.issuer_identity,
                    att.issuer_kind,
                    json.dumps(att.issuer_cert_chain),
                    json.dumps(att.subject),
                    att.artifact_class,
                    att.intent_root_ref,
                    json.dumps(att.predecessor_refs),
                    json.dumps(att.subject_hashes),
                    att.issued_at,
                    att.expires_at,
                    att.not_before,
                    json.dumps(att.policies_satisfied),
                    att.policy_version,
                    att.tier,
                    att.signature_algorithm,
                    att.signature_value,
                ),
            )

            # Insert parent edges.
            for parent_id, edge_kind in self._parents_of(att):
                conn.execute(
                    "INSERT INTO parent_edges(child_id, parent_id, edge_kind) "
                    "VALUES (?, ?, ?)",
                    (att.attestation_id, parent_id, edge_kind),
                )

            # Compute and insert hash chain link.
            prev_row = conn.execute(
                "SELECT link_hash FROM hash_chain "
                "ORDER BY seq DESC LIMIT 1"
            ).fetchone()
            prev_hash = prev_row["link_hash"] if prev_row else self.GENESIS_HASH

            link_input = (
                f"{prev_hash}|{att.attestation_id}|"
                f"{att.signature_value}".encode("utf-8")
            )
            link_hash = "sha256:" + hashlib.sha256(link_input).hexdigest()

            conn.execute(
                "INSERT INTO hash_chain(attestation_id, link_hash, prev_hash) "
                "VALUES (?, ?, ?)",
                (att.attestation_id, link_hash, prev_hash),
            )

            return link_hash

    # --- queries ---

    def get(self, attestation_id: str) -> Optional[Attestation]:
        row = self._conn.execute(
            "SELECT * FROM attestations WHERE attestation_id = ?",
            (attestation_id,),
        ).fetchone()
        return self._row_to_attestation(row) if row else None

    def descendants(self, attestation_id: str) -> list[str]:
        """Direct children."""
        rows = self._conn.execute(
            "SELECT DISTINCT child_id FROM parent_edges WHERE parent_id = ?",
            (attestation_id,),
        ).fetchall()
        return [r["child_id"] for r in rows]

    def all_descendants(self, attestation_id: str) -> set[str]:
        """All transitive descendants. Implemented as iterative BFS in SQL."""
        seen: set[str] = set()
        frontier: list[str] = self.descendants(attestation_id)
        while frontier:
            current = frontier.pop()
            if current in seen:
                continue
            seen.add(current)
            frontier.extend(self.descendants(current))
        return seen

    def chain_back_to_intent(self, attestation_id: str) -> list[str]:
        att = self.get(attestation_id)
        if att is None:
            raise LineageError(f"attestation {attestation_id} not found")

        chain: list[str] = []
        seen: set[str] = set()
        frontier = [attestation_id]
        while frontier:
            current = frontier.pop()
            if current in seen:
                continue
            seen.add(current)
            chain.append(current)
            current_att = self.get(current)
            if current_att is None:
                continue
            for pred in current_att.predecessor_refs:
                if pred not in seen:
                    frontier.append(pred)
            if current_att.intent_root_ref and current_att.intent_root_ref not in seen:
                frontier.append(current_att.intent_root_ref)
        return chain

    def by_intent_root(self, intent_root_id: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT attestation_id FROM attestations WHERE intent_root_ref = ?",
            (intent_root_id,),
        ).fetchall()
        return [r["attestation_id"] for r in rows]

    # --- audit ---

    def chain_head(self) -> Optional[tuple[str, str]]:
        row = self._conn.execute(
            "SELECT attestation_id, link_hash FROM hash_chain "
            "ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        return (row["attestation_id"], row["link_hash"]) if row else None

    def validate_chain(self) -> bool:
        """Walk the chain; verify each link hash is consistent."""
        prev_hash = self.GENESIS_HASH
        for row in self._conn.execute(
            "SELECT attestation_id, link_hash, prev_hash FROM hash_chain "
            "ORDER BY seq ASC"
        ):
            if row["prev_hash"] != prev_hash:
                return False
            att = self.get(row["attestation_id"])
            if att is None:
                return False
            expected_input = (
                f"{prev_hash}|{att.attestation_id}|"
                f"{att.signature_value}".encode("utf-8")
            )
            expected = "sha256:" + hashlib.sha256(expected_input).hexdigest()
            if expected != row["link_hash"]:
                return False
            prev_hash = row["link_hash"]
        return True

    def size(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM attestations"
        ).fetchone()
        return row["n"]

    def close(self) -> None:
        with self._lock:
            self._conn.close()

"""
Lineage store: append-only DAG of attestations.

Hash-chained for tamper-evidence (CT-I11). DAG-validated on insert (CT-I9).

Parent edges include BOTH explicit predecessor_refs AND the intent_root_ref.
This means revocation cascades correctly propagate from intent roots to all
derived attestations even when the derivation is only via intent_root_ref.
"""

from __future__ import annotations

import hashlib
import threading
from typing import Optional

from cogtrust.attestations import Attestation


class LineageError(Exception):
    """Raised when a lineage operation violates an invariant."""


class LineageStore:
    """
    In-memory reference implementation. Production: back with an
    append-only event store (Postgres + immutable triggers, EventStore,
    etc.) with periodic external attestation of the hash chain head.
    """

    GENESIS_HASH = "sha256:" + "0" * 64

    def __init__(self) -> None:
        self._attestations: dict[str, Attestation] = {}
        # Forward edges: parent_id → [child_ids]
        # Parents are predecessor_refs + intent_root_ref (if present).
        self._children: dict[str, list[str]] = {}
        # Hash chain: ordered list of (att_id, link_hash)
        self._chain: list[tuple[str, str]] = []
        # Index of intent_root → list of derived attestation_ids
        self._by_intent_root: dict[str, list[str]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _parents_of(att: Attestation) -> list[str]:
        """All upstream attestations: predecessors + intent root."""
        parents: list[str] = list(att.predecessor_refs)
        if att.intent_root_ref and att.intent_root_ref not in parents:
            parents.append(att.intent_root_ref)
        return parents

    # --- mutation ---

    def append(self, att: Attestation) -> str:
        """
        Append an attestation. Returns the chain link hash for this entry.
        Validates DAG property and rejects cycles or mutations.
        """
        with self._lock:
            # Reject duplicate IDs (immutability — CT-I9).
            if att.attestation_id in self._attestations:
                raise LineageError(
                    f"attestation {att.attestation_id} already exists; "
                    f"lineage is append-only"
                )

            # Validate predecessors exist.
            for pred_id in att.predecessor_refs:
                if pred_id not in self._attestations:
                    raise LineageError(
                        f"predecessor {pred_id} not found in lineage"
                    )

            # Validate intent_root_ref exists (except for intent_root type).
            if att.intent_root_ref is not None:
                if att.intent_root_ref not in self._attestations:
                    raise LineageError(
                        f"intent root {att.intent_root_ref} not found"
                    )

            # Store.
            self._attestations[att.attestation_id] = att
            for parent_id in self._parents_of(att):
                self._children.setdefault(parent_id, []).append(att.attestation_id)
            if att.intent_root_ref is not None:
                self._by_intent_root.setdefault(att.intent_root_ref, []).append(
                    att.attestation_id
                )

            # Append to hash chain.
            previous_hash = self._chain[-1][1] if self._chain else self.GENESIS_HASH
            link_input = (
                f"{previous_hash}|{att.attestation_id}|"
                f"{att.signature_value}".encode("utf-8")
            )
            link_hash = "sha256:" + hashlib.sha256(link_input).hexdigest()
            self._chain.append((att.attestation_id, link_hash))

            return link_hash

    # --- queries ---

    def get(self, attestation_id: str) -> Optional[Attestation]:
        return self._attestations.get(attestation_id)

    def descendants(self, attestation_id: str) -> list[str]:
        """Direct children (via predecessor_refs or intent_root_ref)."""
        return list(self._children.get(attestation_id, []))

    def all_descendants(self, attestation_id: str) -> set[str]:
        """All transitive descendants (BFS)."""
        seen: set[str] = set()
        frontier = list(self._children.get(attestation_id, []))
        while frontier:
            current = frontier.pop()
            if current in seen:
                continue
            seen.add(current)
            frontier.extend(self._children.get(current, []))
        return seen

    def chain_back_to_intent(
        self, attestation_id: str
    ) -> list[str]:
        """
        Walk parents back to the intent root.
        Returns the attestation_ids in order from leaf to intent root.
        """
        if attestation_id not in self._attestations:
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
            att = self._attestations.get(current)
            if att is None:
                continue
            for parent in self._parents_of(att):
                if parent not in seen:
                    frontier.append(parent)
        return chain

    def by_intent_root(self, intent_root_id: str) -> list[str]:
        """All attestations derived from a given intent root."""
        return list(self._by_intent_root.get(intent_root_id, []))

    # --- audit ---

    def chain_head(self) -> Optional[tuple[str, str]]:
        """Return (latest_attestation_id, latest_chain_hash) or None."""
        if not self._chain:
            return None
        return self._chain[-1]

    def validate_chain(self) -> bool:
        """
        Validate the entire hash chain. Returns True if intact.
        Production: also externally attest the chain head periodically.
        """
        prev_hash = self.GENESIS_HASH
        for att_id, link_hash in self._chain:
            att = self._attestations.get(att_id)
            if att is None:
                return False
            expected_input = (
                f"{prev_hash}|{att_id}|{att.signature_value}".encode("utf-8")
            )
            expected = "sha256:" + hashlib.sha256(expected_input).hexdigest()
            if expected != link_hash:
                return False
            prev_hash = link_hash
        return True

    def size(self) -> int:
        return len(self._attestations)

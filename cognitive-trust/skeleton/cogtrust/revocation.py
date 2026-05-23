"""
Revocation index and cascade.

The index is monotonically versioned. Verifiers cache results keyed by
the index version; index updates invalidate caches.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from cogtrust.lineage import LineageStore


@dataclass
class RevocationEntry:
    attestation_id: str
    revoked_at_version: int
    revoked_at_timestamp: float
    reason: str
    derivative: bool  # True if propagated via cascade


class RevocationIndex:
    """
    The single source of truth for "is this attestation revoked?"

    Index version increments on every modification. Verifiers compare
    their cached version against current to decide whether to re-check.
    """

    def __init__(self) -> None:
        self._entries: dict[str, RevocationEntry] = {}
        self._version: int = 0
        self._lock = threading.Lock()

    def revoke(
        self,
        attestation_id: str,
        reason: str,
        derivative: bool = False,
    ) -> int:
        """Revoke an attestation. Returns the new index version."""
        with self._lock:
            if attestation_id in self._entries:
                # Already revoked; return current version.
                return self._version
            self._version += 1
            self._entries[attestation_id] = RevocationEntry(
                attestation_id=attestation_id,
                revoked_at_version=self._version,
                revoked_at_timestamp=time.time(),
                reason=reason,
                derivative=derivative,
            )
            return self._version

    def is_revoked(self, attestation_id: str) -> bool:
        return attestation_id in self._entries

    def entry(self, attestation_id: str) -> RevocationEntry | None:
        return self._entries.get(attestation_id)

    def version(self) -> int:
        return self._version

    def all_revoked(self) -> list[str]:
        return list(self._entries.keys())


class RevocationCascade:
    """
    Cascade worker: when an attestation is revoked, mark all derivatives
    as derivative_revoked. SLA target: 60 seconds (CT-I5).

    Reference implementation is synchronous. Production implementations
    should run async with backpressure.
    """

    def __init__(
        self, lineage: LineageStore, index: RevocationIndex
    ) -> None:
        self._lineage = lineage
        self._index = index

    def revoke_with_cascade(self, attestation_id: str, reason: str) -> dict:
        """
        Revoke the root and cascade. Returns a summary.
        """
        start = time.monotonic()
        root_version = self._index.revoke(attestation_id, reason, derivative=False)

        descendants = self._lineage.all_descendants(attestation_id)
        derivative_count = 0
        for desc_id in descendants:
            if not self._index.is_revoked(desc_id):
                self._index.revoke(
                    desc_id,
                    reason=f"derivative_of:{attestation_id}",
                    derivative=True,
                )
                derivative_count += 1

        elapsed_ms = int((time.monotonic() - start) * 1000)
        return {
            "root_attestation_id": attestation_id,
            "root_revocation_version": root_version,
            "derivative_count": derivative_count,
            "elapsed_ms": elapsed_ms,
            "final_index_version": self._index.version(),
        }

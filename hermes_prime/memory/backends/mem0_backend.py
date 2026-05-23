from __future__ import annotations

from typing import Any

from hermes_prime.contracts import MemoryClaim
from hermes_prime.memory.base import MemoryBackend, MemorySearchResult


class Mem0Backend(MemoryBackend):
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self._available = self._check_mem0()

    def _check_mem0(self) -> bool:
        try:
            import mem0
            return True
        except ImportError:
            return False

    def store(self, claim: MemoryClaim) -> None:
        raise NotImplementedError("mem0 backend not yet implemented")

    def get(self, fact_id: str) -> MemoryClaim | None:
        raise NotImplementedError("mem0 backend not yet implemented")

    def search(self, query: str, limit: int = 10) -> list[MemorySearchResult]:
        raise NotImplementedError("mem0 backend not yet implemented")

    def list_all(self) -> list[MemoryClaim]:
        raise NotImplementedError("mem0 backend not yet implemented")

    def delete(self, fact_id: str) -> bool:
        raise NotImplementedError("mem0 backend not yet implemented")

    def count(self) -> int:
        raise NotImplementedError("mem0 backend not yet implemented")

    def gc(self, before_timestamp: str) -> int:
        raise NotImplementedError("mem0 backend not yet implemented")

from __future__ import annotations

import importlib.util

from hermes_prime.contracts import MemoryClaim
from hermes_prime.memory.base import MemoryBackend, MemorySearchResult


class ZepBackend(MemoryBackend):
    def __init__(self, api_url: str = "http://localhost:8000", api_key: str | None = None) -> None:
        self.api_url = api_url
        self.api_key = api_key
        self._available = self._check_zep()

    def _check_zep(self) -> bool:
        return importlib.util.find_spec("zep") is not None

    def store(self, claim: MemoryClaim) -> None:
        raise NotImplementedError("Zep backend not yet implemented")

    def get(self, fact_id: str) -> MemoryClaim | None:
        raise NotImplementedError("Zep backend not yet implemented")

    def search(self, query: str, limit: int = 10) -> list[MemorySearchResult]:
        raise NotImplementedError("Zep backend not yet implemented")

    def list_all(self) -> list[MemoryClaim]:
        raise NotImplementedError("Zep backend not yet implemented")

    def delete(self, fact_id: str) -> bool:
        raise NotImplementedError("Zep backend not yet implemented")

    def count(self) -> int:
        raise NotImplementedError("Zep backend not yet implemented")

    def gc(self, before_timestamp: str) -> int:
        raise NotImplementedError("Zep backend not yet implemented")

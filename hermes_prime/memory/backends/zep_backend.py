from __future__ import annotations

import json
from typing import Any

import requests

from hermes_prime.contracts import MemoryClaim
from hermes_prime.memory.base import MemoryBackend, MemorySearchResult


class ZepBackend(MemoryBackend):
    def __init__(
        self,
        api_url: str = "http://localhost:8000",
        api_key: str | None = None,
        session_id: str = "hermes-prime",
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.session_id = session_id

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Api-Key {self.api_key}"
        return headers

    def _get_all_messages(self) -> list[dict[str, Any]]:
        try:
            response = requests.get(
                f"{self.api_url}/api/v1/sessions/{self.session_id}/memory",
                headers=self._headers(),
                params={"lastn": 10000},
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException:
            return []
        return data.get("messages", data.get("data", []))

    def store(self, claim: MemoryClaim) -> None:
        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": json.dumps(claim.to_dict()),
                    "metadata": {
                        "fact_id": claim.fact_id,
                        "timestamp": claim.timestamp,
                    },
                }
            ],
        }
        response = requests.post(
            f"{self.api_url}/api/v1/sessions/{self.session_id}/memory",
            headers=self._headers(),
            json=payload,
        )
        response.raise_for_status()

    def get(self, fact_id: str) -> MemoryClaim | None:
        for msg in self._get_all_messages():
            metadata = msg.get("metadata", {}) or {}
            if metadata.get("fact_id") == fact_id:
                content = msg.get("content", "")
                try:
                    return MemoryClaim(**json.loads(content))
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass
        return None

    def search(self, query: str, limit: int = 10) -> list[MemorySearchResult]:
        try:
            response = requests.post(
                f"{self.api_url}/api/v1/graph/search",
                headers=self._headers(),
                json={"query": query, "limit": limit},
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException:
            return []

        results: list[MemorySearchResult] = []
        edges = data.get("edges", data.get("results", data.get("data", [])))
        for edge in edges:
            content = edge.get("content", edge.get("fact", ""))
            try:
                claim = MemoryClaim(**json.loads(content))
                score = float(edge.get("score", edge.get("distance", 0.0)))
                results.append(MemorySearchResult.from_claim(claim, similarity=score))
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
        return results[:limit]

    def list_all(self) -> list[MemoryClaim]:
        claims: list[MemoryClaim] = []
        for msg in self._get_all_messages():
            content = msg.get("content", "")
            try:
                claims.append(MemoryClaim(**json.loads(content)))
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
        return claims

    def _replace_all_messages(self, messages: list[dict[str, Any]]) -> bool:
        try:
            requests.delete(
                f"{self.api_url}/api/v1/sessions/{self.session_id}/memory",
                headers=self._headers(),
            ).raise_for_status()
        except requests.RequestException:
            return False
        if messages:
            try:
                requests.post(
                    f"{self.api_url}/api/v1/sessions/{self.session_id}/memory",
                    headers=self._headers(),
                    json={"messages": messages},
                ).raise_for_status()
            except requests.RequestException:
                pass
        return True

    def delete(self, fact_id: str) -> bool:
        messages = self._get_all_messages()
        remaining: list[dict[str, Any]] = []
        found = False
        for msg in messages:
            metadata = msg.get("metadata", {}) or {}
            if metadata.get("fact_id") == fact_id:
                found = True
            else:
                remaining.append(msg)
        if not found:
            return False
        self._replace_all_messages(remaining)
        return True

    def count(self) -> int:
        return len(self._get_all_messages())

    def gc(self, before_timestamp: str) -> int:
        messages = self._get_all_messages()
        remaining: list[dict[str, Any]] = []
        deleted = 0
        for msg in messages:
            metadata = msg.get("metadata", {}) or {}
            ts = metadata.get("timestamp", "")
            if ts and ts < before_timestamp:
                deleted += 1
            else:
                remaining.append(msg)
        if deleted > 0:
            self._replace_all_messages(remaining)
        return deleted

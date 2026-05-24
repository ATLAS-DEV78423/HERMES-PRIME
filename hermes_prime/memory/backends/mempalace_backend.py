from __future__ import annotations

import os
from pathlib import Path

from hermes_prime.contracts import MemoryClaim, MemoryTier, TrustState
from hermes_prime.memory.base import MemoryBackend, MemorySearchResult
from hermes_prime.utils import new_urn_uuid, utc_now_iso


class MemPalaceBackend(MemoryBackend):
    """MemoryBackend implementation using MemPalace as the verbatim store.

    Maps HERMES memory records to MemPalace's wing/room/drawer model:
    - memory_type -> wing
    - source_agent -> room
    - individual record -> drawer
    """

    def __init__(self, palace_path: str | None = None):
        if palace_path is None:
            palace_path = os.path.join(os.path.expanduser("~"), ".hermes-prime", "palace")
        self.palace_path = str(Path(palace_path).expanduser().resolve())
        self._collection = None
        self._initialized = False

    def _ensure_initialized(self):
        if self._initialized:
            return
        os.makedirs(self.palace_path, exist_ok=True)
        self._initialized = True

    def _get_collection(self):
        self._ensure_initialized()
        if self._collection is None:
            from mempalace.palace import get_collection
            self._collection = get_collection(self.palace_path)
        return self._collection

    def _wing_for_claim(self, claim: MemoryClaim) -> str:
        memory_type = "episodic"
        if claim.source and isinstance(claim.source, dict):
            memory_type = claim.source.get("memory_type", "episodic")
        return f"hermes_{memory_type}"

    def _room_for_claim(self, claim: MemoryClaim) -> str:
        agent = "unknown"
        if claim.source and isinstance(claim.source, dict):
            agent = claim.source.get("agent", "unknown")
        return agent

    def store(self, claim: MemoryClaim) -> None:
        self._ensure_initialized()

        wing = self._wing_for_claim(claim)
        room = self._room_for_claim(claim)
        collection = self._get_collection()

        # store fact_id in source_file (mempalace normalizes to basename)
        # and also in a dedicated hermes_id metadata field for reliable lookup
        import hashlib
        drawer_id = (
            f"hermes_{wing}_{room}_"
            + hashlib.sha256(claim.claim.encode("utf-8")).hexdigest()[:24]
        )
        collection.upsert(
            documents=[claim.claim],
            ids=[drawer_id],
            metadatas=[{
                "wing": wing,
                "room": room,
                "source_file": claim.fact_id,
                "hermes_id": claim.fact_id,
                "chunk_index": 0,
                "added_by": "hermes-prime",
                "filed_at": utc_now_iso(),
            }],
        )

    def get(self, fact_id: str) -> MemoryClaim | None:
        self._ensure_initialized()
        try:
            collection = self._get_collection()
            results = collection.get(
                where={"hermes_id": fact_id},
                limit=1,
            )
            if results and results.get("ids") and len(results["ids"]) > 0:
                idx = 0
                metadata = results["metadatas"][idx] if results.get("metadatas") else {}
                documents = results["documents"] if results.get("documents") else []
                content = documents[idx] if idx < len(documents) else ""
                return self._claim_from_mempalace_result(
                    fact_id=fact_id,
                    content=content,
                    metadata=metadata,
                )
            return None
        except Exception:
            return None

    def search(self, query: str, limit: int = 10) -> list[MemorySearchResult]:
        self._ensure_initialized()
        try:
            from mempalace.searcher import search_memories
            result = search_memories(
                query=query,
                palace_path=self.palace_path,
                n_results=limit,
            )
            if isinstance(result, dict) and "results" in result:
                search_results = []
                for r in result["results"]:
                    fact_id = self._fact_id_from_drawer(r)
                    search_results.append(MemorySearchResult(
                        fact_id=fact_id,
                        claim=r.get("text", ""),
                        source={"agent": r.get("room", "unknown")},
                        epistemic_confidence=float(r.get("similarity", 0.0)),
                        verification_status="unverified",
                        source_trust="observed",
                        timestamp=utc_now_iso(),
                        trust_state=TrustState.UNVERIFIED.value,
                        tier=MemoryTier.QUARANTINE.value,
                        contradictions=[],
                        intent_root="",
                        similarity=float(r.get("similarity", 0.0)),
                    ))
                return search_results
            return []
        except Exception:
            return []

    def list_all(self) -> list[MemoryClaim]:
        self._ensure_initialized()
        try:
            collection = self._get_collection()
            results = collection.get(limit=1000)
            claims = []
            if results and results.get("ids"):
                metadatas = results.get("metadatas") or []
                documents = results.get("documents") or []
                for i, doc_id in enumerate(results["ids"]):
                    metadata = metadatas[i] if i < len(metadatas) else {}
                    content = documents[i] if i < len(documents) else ""
                    fact_id = self._fact_id_from_source(metadata)
                    claims.append(self._claim_from_mempalace_result(
                        fact_id=fact_id,
                        content=content,
                        metadata=metadata,
                    ))
            return claims
        except Exception:
            return []

    def delete(self, fact_id: str) -> bool:
        self._ensure_initialized()
        try:
            collection = self._get_collection()
            existing = collection.get(
                where={"hermes_id": fact_id},
                limit=1,
            )
            if existing and existing.get("ids") and len(existing["ids"]) > 0:
                collection.delete(ids=[existing["ids"][0]])
                return True
            return False
        except Exception:
            return False

    def count(self) -> int:
        self._ensure_initialized()
        try:
            collection = self._get_collection()
            return collection.count()
        except Exception:
            return 0

    def gc(self, before_timestamp: str) -> int:
        self._ensure_initialized()
        try:
            collection = self._get_collection()
            all_items = collection.get(limit=10000)
            if not all_items or not all_items.get("ids"):
                return 0
            to_delete = []
            metadatas = all_items.get("metadatas") or []
            ids = all_items["ids"]
            for i, meta in enumerate(metadatas):
                if meta and "filed_at" in meta:
                    if meta["filed_at"] < before_timestamp:
                        to_delete.append(ids[i])
            if to_delete:
                collection.delete(ids=to_delete)
            return len(to_delete)
        except Exception:
            return 0

    def _claim_from_mempalace_result(
        self, fact_id: str, content: str, metadata: dict
    ) -> MemoryClaim:
        agent = metadata.get("room", "unknown") if metadata else "unknown"
        return MemoryClaim(
            fact_id=fact_id,
            claim=content,
            source={"agent": agent, "memory_type": metadata.get("wing", "episodic") if metadata else "episodic"},
            epistemic_confidence=0.5,
            verification_status="unverified",
            source_trust="observed",
            timestamp=metadata.get("filed_at", utc_now_iso()) if metadata else utc_now_iso(),
            trust_state=TrustState.UNVERIFIED,
            tier=MemoryTier.QUARANTINE,
            contradictions=[],
            intent_root="",
        )

    def _fact_id_from_drawer(self, result: dict) -> str:
        hermes_id = result.get("hermes_id", "")
        if hermes_id:
            return hermes_id
        source = result.get("source_file", "")
        if source:
            return source
        return new_urn_uuid()

    def _fact_id_from_source(self, metadata: dict) -> str:
        if metadata:
            hermes_id = metadata.get("hermes_id", "")
            if hermes_id:
                return hermes_id
            source = metadata.get("source_file", "")
            if source:
                return source
        return new_urn_uuid()

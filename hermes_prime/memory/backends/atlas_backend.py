from __future__ import annotations

import importlib.util
from pathlib import Path

from hermes_prime.contracts import MemoryClaim
from hermes_prime.memory.base import MemoryBackend, MemorySearchResult
from hermes_prime.utils import utc_now_iso


class AtlasBackend(MemoryBackend):
    def __init__(self, chroma_path: str | Path | None = None) -> None:
        self.chroma_path = Path(chroma_path) if chroma_path else Path.cwd() / ".hermes-prime" / "chroma_db"
        self.chroma_path.mkdir(parents=True, exist_ok=True)
        self._collection = None
        self._chroma_available = self._check_chroma()

    def _check_chroma(self) -> bool:
        return importlib.util.find_spec("chromadb") is not None

    def _get_collection(self):
        if self._collection is not None:
            return self._collection
        if not self._chroma_available:
            raise RuntimeError(
                "ChromaDB is not installed. Install with: pip install chromadb"
            )
        import chromadb
        client = chromadb.PersistentClient(path=str(self.chroma_path))
        self._collection = client.get_or_create_collection(
            name="atlas_memory",
            metadata={"hnsw:space": "cosine"},
        )
        return self._collection

    def store(self, claim: MemoryClaim) -> None:
        collection = self._get_collection()
        tier = claim.tier.value if hasattr(claim.tier, 'value') else claim.tier
        state = claim.trust_state.value if hasattr(claim.trust_state, 'value') else claim.trust_state
        collection.upsert(
            ids=[claim.fact_id],
            documents=[claim.claim],
            metadatas=[{
                "fact_id": claim.fact_id,
                "source_trust": claim.source_trust,
                "verification_status": claim.verification_status,
                "epistemic_confidence": str(claim.epistemic_confidence),
                "tier": tier,
                "trust_state": state,
                "intent_root": claim.intent_root,
                "timestamp": claim.timestamp,
            }],
        )

    def get(self, fact_id: str) -> MemoryClaim | None:
        collection = self._get_collection()
        try:
            result = collection.get(ids=[fact_id], include=["documents", "metadatas"])
        except Exception:
            return None
        if not result["ids"]:
            return None
        doc = result["documents"][0] if result["documents"] else ""
        meta = result["metadatas"][0] if result["metadatas"] else {}
        return MemoryClaim(
            fact_id=fact_id,
            claim=doc or "",
            source={"backend": "atlas", "collection": "atlas_memory"},
            epistemic_confidence=float(meta.get("epistemic_confidence", "0.0")),
            verification_status=meta.get("verification_status", "unverified"),
            source_trust=meta.get("source_trust", "unknown"),
            timestamp=meta.get("timestamp", utc_now_iso()),
            trust_state=meta.get("trust_state", "UNVERIFIED"),
            tier=meta.get("tier", "quarantine"),
            contradictions=[],
            intent_root=meta.get("intent_root", ""),
        )

    def search(self, query: str, limit: int = 10) -> list[MemorySearchResult]:
        collection = self._get_collection()
        try:
            results = collection.query(
                query_texts=[query],
                n_results=limit,
                include=["documents", "metadatas", "distances"],
            )
        except Exception:
            return []
        if not results["ids"] or not results["ids"][0]:
            return []
        output: list[MemorySearchResult] = []
        for i, fact_id in enumerate(results["ids"][0]):
            doc = results["documents"][0][i] if results["documents"] and len(results["documents"][0]) > i else ""
            meta = results["metadatas"][0][i] if results["metadatas"] and len(results["metadatas"][0]) > i else {}
            distance = results["distances"][0][i] if results["distances"] and len(results["distances"][0]) > i else 0.0
            similarity = max(0.0, 1.0 - float(distance))
            output.append(MemorySearchResult(
                fact_id=fact_id,
                claim=doc,
                source={"backend": "atlas", "collection": "atlas_memory"},
                epistemic_confidence=float(meta.get("epistemic_confidence", "0.0")),
                verification_status=meta.get("verification_status", "unverified"),
                source_trust=meta.get("source_trust", "unknown"),
                timestamp=meta.get("timestamp", utc_now_iso()),
                trust_state=meta.get("trust_state", "UNVERIFIED"),
                tier=meta.get("tier", "quarantine"),
                contradictions=[],
                intent_root=meta.get("intent_root", ""),
                similarity=similarity,
            ))
        return output

    def list_all(self) -> list[MemoryClaim]:
        collection = self._get_collection()
        try:
            result = collection.get(include=["documents", "metadatas"])
        except Exception:
            return []
        if not result["ids"]:
            return []
        claims: list[MemoryClaim] = []
        for i, fact_id in enumerate(result["ids"]):
            doc = result["documents"][i] if result["documents"] and len(result["documents"]) > i else ""
            meta = result["metadatas"][i] if result["metadatas"] and len(result["metadatas"]) > i else {}
            claims.append(MemoryClaim(
                fact_id=fact_id,
                claim=doc or "",
                source={"backend": "atlas", "collection": "atlas_memory"},
                epistemic_confidence=float(meta.get("epistemic_confidence", "0.0")),
                verification_status=meta.get("verification_status", "unverified"),
                source_trust=meta.get("source_trust", "unknown"),
                timestamp=meta.get("timestamp", utc_now_iso()),
                trust_state=meta.get("trust_state", "UNVERIFIED"),
                tier=meta.get("tier", "quarantine"),
                contradictions=[],
                intent_root=meta.get("intent_root", ""),
            ))
        return claims

    def delete(self, fact_id: str) -> bool:
        collection = self._get_collection()
        try:
            collection.delete(ids=[fact_id])
            return True
        except Exception:
            return False

    def count(self) -> int:
        collection = self._get_collection()
        try:
            result = collection.get()
            return len(result["ids"]) if result["ids"] else 0
        except Exception:
            return 0

    def gc(self, before_timestamp: str) -> int:
        return 0

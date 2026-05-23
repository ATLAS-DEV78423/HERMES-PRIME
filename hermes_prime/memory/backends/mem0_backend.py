from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from hermes_prime.contracts import MemoryClaim, MemoryTier, TrustState
from hermes_prime.memory.base import MemoryBackend, MemorySearchResult
from hermes_prime.utils import new_urn_uuid, utc_now_iso

_ENTITY_BOOST_WEIGHT = 0.5
_DEFAULT_CHROMA_PATH = Path.cwd() / ".hermes-prime" / "mem0_chroma"


def _extract_entities(text: str) -> list[tuple[str, str]]:
    """Extract entities from text using regex patterns (no spaCy dependency).

    Returns list of (entity_text, entity_type) tuples matching mem0 categories:
    PROPER, QUOTED, COMPOUND, NOUN.
    """
    entities: list[tuple[str, str]] = []
    seen: set[str] = set()

    # 1. Quoted text
    for m in re.finditer(r""""([^"]+)"|'([^']+)'""", text):
        raw = m.group(1) or m.group(2)
        cleaned = raw.strip()
        if cleaned and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            entities.append((cleaned, "QUOTED"))

    # 2. Proper nouns: capitalized multi-word sequences (2+ words)
    for m in re.finditer(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", text):
        raw = m.group(1).strip()
        if raw and raw.lower() not in seen:
            seen.add(raw.lower())
            entities.append((raw, "PROPER"))

    # 3. Compound nouns: adjective + noun pairs
    for m in re.finditer(
        r"\b(?:machine|deep|reinforcement|supervised|unsupervised|natural|artificial|neural|social|political|economic|financial|cultural|technical|digital|physical|chemical|biological|medical|legal|ethical|theoretical|practical|statistical|mathematical|computational|experimental|clinical|industrial|commercial|educational|environmental|global|local|national|international|modern|traditional|classical|contemporary|advanced|basic|fundamental|applied|general|specific|abstract|concrete|relative|absolute|positive|negative|direct|indirect|primary|secondary|active|passive|static|dynamic|formal|informal|structural|functional|behavioral|cognitive|emotional|visual|spatial|temporal|quantitative|qualitative|systematic|strategic|operational|tactical|logical|intuitive|critical|analytical|creative|collaborative|autonomous|interactive|adaptive|predictive|generative|distributed|centralized|decentralized|concurrent|sequential|parallel|linear|nonlinear|discrete|continuous|finite|infinite|open|closed|native|cross)(?:\s+[a-zA-Z]\w+)",
        text,
    ):
        raw = m.group(0).strip()
        if raw and raw.lower() not in seen:
            seen.add(raw.lower())
            entities.append((raw, "COMPOUND"))

    # 4. Single capitalized nouns as fallback
    for m in re.finditer(r"\b[A-Z][a-z]+\b", text):
        raw = m.group(0)
        if raw.lower() not in seen:
            skip = {"The", "This", "That", "These", "Those", "It", "Its",
                    "A", "An", "And", "Or", "But", "Not", "For", "With",
                    "From", "Into", "Over", "Under", "After", "Before",
                    "Between", "Through", "During", "Without", "Within"}
            if raw not in skip:
                seen.add(raw.lower())
                entities.append((raw, "NOUN"))

    return entities


class Mem0Backend(MemoryBackend):
    """Memory backend with entity extraction and entity-boosted search (mem0-style).

    Features:
    - ChromaDB vector storage for memory claims
    - Entity extraction from claim text (regex-based, no spaCy required)
    - Entity store mapping entities to linked memory fact_ids
    - Entity-boosted search (boosts results sharing entities with the query)
    - All 7 backend ABC methods implemented
    """

    def __init__(self, chroma_path: str | Path | None = None) -> None:
        self.chroma_path = Path(chroma_path) if chroma_path else _DEFAULT_CHROMA_PATH
        self.chroma_path.mkdir(parents=True, exist_ok=True)
        self._memory_collection = None
        self._entity_collection = None
        self._chroma_available = self._check_chroma()

    def _check_chroma(self) -> bool:
        try:
            import chromadb
            return True
        except ImportError:
            return False

    def _get_collections(self):
        if self._memory_collection is not None:
            return self._memory_collection, self._entity_collection
        if not self._chroma_available:
            raise RuntimeError("ChromaDB not installed. Install with: pip install chromadb")
        import chromadb
        client = chromadb.PersistentClient(path=str(self.chroma_path))
        self._memory_collection = client.get_or_create_collection(
            name="mem0_memory",
            metadata={"hnsw:space": "cosine"},
        )
        self._entity_collection = client.get_or_create_collection(
            name="mem0_entities",
            metadata={"hnsw:space": "cosine"},
        )
        return self._memory_collection, self._entity_collection

    def store(self, claim: MemoryClaim) -> None:
        mem_coll, ent_coll = self._get_collections()
        tier = claim.tier.value if hasattr(claim.tier, 'value') else claim.tier
        state = claim.trust_state.value if hasattr(claim.trust_state, 'value') else claim.trust_state

        mem_coll.upsert(
            ids=[claim.fact_id],
            documents=[claim.claim],
            metadatas=[{
                "fact_id": claim.fact_id,
                "source_agent": claim.source.get("agent", "unknown") if isinstance(claim.source, dict) else "unknown",
                "source_trust": claim.source_trust,
                "verification_status": claim.verification_status,
                "epistemic_confidence": str(claim.epistemic_confidence),
                "tier": tier,
                "trust_state": state,
                "intent_root": claim.intent_root,
                "timestamp": claim.timestamp,
                "memory_type": claim.source.get("memory_type", "episodic") if isinstance(claim.source, dict) else "episodic",
            }],
        )

        entities = _extract_entities(claim.claim)
        if not entities:
            return

        existing = ent_coll.get(
            where={"entity_type": {"$in": list({e[1] for e in entities})}},
            limit=len(entities) * 2,
        )
        existing_map: dict[str, set[str]] = {}
        if existing and existing.get("ids"):
            for i, eid in enumerate(existing["ids"]):
                meta = existing["metadatas"][i] if existing.get("metadatas") and i < len(existing["metadatas"]) else {}
                linked = meta.get("linked_fact_ids", "")
                existing_map[eid] = set(linked.split(",")) if linked else set()

        for entity_text, entity_type in entities:
            eid = f"ent_{hash(entity_text.lower())}"
            linked_ids = existing_map.get(eid, set())
            linked_ids.add(claim.fact_id)
            ent_coll.upsert(
                ids=[eid],
                documents=[entity_text],
                metadatas=[{
                    "entity_text": entity_text,
                    "entity_type": entity_type,
                    "linked_fact_ids": ",".join(sorted(linked_ids)),
                }],
            )

    def get(self, fact_id: str) -> MemoryClaim | None:
        mem_coll, _ = self._get_collections()
        try:
            result = mem_coll.get(ids=[fact_id], include=["documents", "metadatas"])
        except Exception:
            return None
        if not result or not result.get("ids") or not result["ids"]:
            return None
        return self._claim_from_result(result, 0)

    def search(self, query: str, limit: int = 10) -> list[MemorySearchResult]:
        mem_coll, ent_coll = self._get_collections()

        try:
            results = mem_coll.query(
                query_texts=[query],
                n_results=limit * 2,
                include=["documents", "metadatas", "distances"],
            )
        except Exception:
            return []

        if not results or not results.get("ids") or not results["ids"][0]:
            return []

        query_entities = _extract_entities(query)
        boost_ids: set[str] = set()
        if query_entities:
            for entity_text, _ in query_entities:
                try:
                    ent_results = ent_coll.query(
                        query_texts=[entity_text],
                        n_results=3,
                        include=["metadatas"],
                    )
                    if ent_results and ent_results.get("ids") and ent_results["ids"][0]:
                        for i in range(len(ent_results["ids"][0])):
                            meta = (ent_results["metadatas"][0][i]
                                    if ent_results.get("metadatas") and len(ent_results["metadatas"][0]) > i
                                    else {})
                            linked = meta.get("linked_fact_ids", "")
                            if linked:
                                boost_ids.update(fid.strip() for fid in linked.split(",") if fid.strip())
                except Exception:
                    continue

        output: list[MemorySearchResult] = []
        for i, fact_id in enumerate(results["ids"][0]):
            doc = (results["documents"][0][i]
                   if results.get("documents") and len(results["documents"][0]) > i
                   else "")
            meta = (results["metadatas"][0][i]
                    if results.get("metadatas") and len(results["metadatas"][0]) > i
                    else {})
            distance = (results["distances"][0][i]
                        if results.get("distances") and len(results["distances"][0]) > i
                        else 0.0)
            similarity = max(0.0, 1.0 - float(distance))

            if fact_id in boost_ids:
                similarity = similarity + (1.0 - similarity) * _ENTITY_BOOST_WEIGHT

            output.append(MemorySearchResult(
                fact_id=fact_id,
                claim=doc,
                source={"backend": "mem0", "collection": "mem0_memory", "agent": meta.get("source_agent", "unknown")},
                epistemic_confidence=float(meta.get("epistemic_confidence", "0.0")),
                verification_status=meta.get("verification_status", "unverified"),
                source_trust=meta.get("source_trust", "unknown"),
                timestamp=meta.get("timestamp", utc_now_iso()),
                trust_state=meta.get("trust_state", TrustState.UNVERIFIED.value),
                tier=meta.get("tier", MemoryTier.QUARANTINE.value),
                contradictions=[],
                intent_root=meta.get("intent_root", ""),
                similarity=min(similarity, 1.0),
            ))

        output.sort(key=lambda r: r.similarity, reverse=True)
        return output[:limit]

    def list_all(self) -> list[MemoryClaim]:
        mem_coll, _ = self._get_collections()
        try:
            result = mem_coll.get(include=["documents", "metadatas"])
        except Exception:
            return []
        if not result or not result.get("ids"):
            return []
        claims: list[MemoryClaim] = []
        for i in range(len(result["ids"])):
            claims.append(self._claim_from_result(result, i))
        return claims

    def delete(self, fact_id: str) -> bool:
        mem_coll, ent_coll = self._get_collections()
        try:
            existing = mem_coll.get(ids=[fact_id])
            if not existing or not existing.get("ids") or not existing["ids"]:
                return False
            mem_coll.delete(ids=[fact_id])
            self._cleanup_entity_links(ent_coll, fact_id)
            return True
        except Exception:
            return False

    def count(self) -> int:
        mem_coll, _ = self._get_collections()
        try:
            result = mem_coll.get()
            return len(result["ids"]) if result and result.get("ids") else 0
        except Exception:
            return 0

    def gc(self, before_timestamp: str) -> int:
        mem_coll, ent_coll = self._get_collections()
        try:
            all_items = mem_coll.get(include=["metadatas"], limit=10000)
            if not all_items or not all_items.get("ids"):
                return 0
            to_delete: list[str] = []
            metadatas = all_items.get("metadatas") or []
            for i, fid in enumerate(all_items["ids"]):
                meta = metadatas[i] if i < len(metadatas) else {}
                if meta and meta.get("timestamp", "") < before_timestamp:
                    to_delete.append(fid)
            if to_delete:
                mem_coll.delete(ids=to_delete)
                for fid in to_delete:
                    self._cleanup_entity_links(ent_coll, fid)
            return len(to_delete)
        except Exception:
            return 0

    def _cleanup_entity_links(self, ent_coll, fact_id: str) -> None:
        try:
            all_entities = ent_coll.get(include=["metadatas"], limit=10000)
            if not all_entities or not all_entities.get("ids"):
                return
            metadatas = all_entities.get("metadatas") or []
            for i, eid in enumerate(all_entities["ids"]):
                meta = metadatas[i] if i < len(metadatas) else {}
                linked = meta.get("linked_fact_ids", "")
                if fact_id in linked:
                    ids_set = set(fid.strip() for fid in linked.split(",") if fid.strip())
                    ids_set.discard(fact_id)
                    if ids_set:
                        ent_coll.update(
                            ids=[eid],
                            metadatas=[{"linked_fact_ids": ",".join(sorted(ids_set))}],
                        )
                    else:
                        ent_coll.delete(ids=[eid])
        except Exception:
            pass

    def _claim_from_result(self, result: dict, index: int) -> MemoryClaim:
        doc = (result["documents"][index]
               if result.get("documents") and len(result["documents"]) > index
               else "")
        meta = (result["metadatas"][index]
                if result.get("metadatas") and len(result["metadatas"]) > index
                else {})
        return MemoryClaim(
            fact_id=result["ids"][index],
            claim=doc or "",
            source={
                "backend": "mem0",
                "collection": "mem0_memory",
                "agent": meta.get("source_agent", "unknown"),
                "memory_type": meta.get("memory_type", "episodic"),
            },
            epistemic_confidence=float(meta.get("epistemic_confidence", "0.0")),
            verification_status=meta.get("verification_status", "unverified"),
            source_trust=meta.get("source_trust", "unknown"),
            timestamp=meta.get("timestamp", utc_now_iso()),
            trust_state=meta.get("trust_state", TrustState.UNVERIFIED.value),
            tier=meta.get("tier", MemoryTier.QUARANTINE.value),
            contradictions=[],
            intent_root=meta.get("intent_root", ""),
        )

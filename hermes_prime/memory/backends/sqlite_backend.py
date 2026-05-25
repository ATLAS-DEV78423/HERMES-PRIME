from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from hermes_prime.contracts import MemoryClaim
from hermes_prime.memory.base import MemoryBackend, MemorySearchResult


class SQLiteMemoryBackend(MemoryBackend):
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        import sqlite3
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS memory_claims (
                fact_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                trust_state TEXT NOT NULL,
                tier TEXT NOT NULL DEFAULT 'quarantine',
                contradiction_payload TEXT NOT NULL DEFAULT '[]',
                intent_root TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_memory_tier ON memory_claims(tier);
            CREATE INDEX IF NOT EXISTS idx_memory_trust_state ON memory_claims(trust_state);
            CREATE INDEX IF NOT EXISTS idx_memory_intent_root ON memory_claims(intent_root);
            CREATE INDEX IF NOT EXISTS idx_memory_created_at ON memory_claims(created_at);
        """)
        try:
            self.conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS memory_claims_fts "
                "USING fts5(fact_id UNINDEXED, claim_text, trust_state, tier)"
            )
        except sqlite3.OperationalError:
            pass
        self.conn.commit()

    def store(self, claim: MemoryClaim) -> None:
        now = claim.timestamp
        contradictions = json.dumps(claim.contradictions, sort_keys=True, ensure_ascii=True)
        payload = claim.to_dict()
        payload_json = json.dumps(payload, sort_keys=True, ensure_ascii=True)
        state = claim.trust_state.value if hasattr(claim.trust_state, 'value') else claim.trust_state
        tier = claim.tier.value if hasattr(claim.tier, 'value') else claim.tier
        self.conn.execute(
            """
            INSERT INTO memory_claims(fact_id, payload, trust_state, tier, contradiction_payload, intent_root, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(fact_id) DO UPDATE SET
                payload=excluded.payload,
                trust_state=excluded.trust_state,
                tier=excluded.tier,
                contradiction_payload=excluded.contradiction_payload,
                intent_root=excluded.intent_root,
                updated_at=excluded.updated_at
            """,
            (claim.fact_id, payload_json, state, tier, contradictions, claim.intent_root, now, now),
        )
        try:
            claim_text = payload.get("claim", "")
            self.conn.execute(
                "INSERT OR REPLACE INTO memory_claims_fts(fact_id, claim_text, trust_state, tier) VALUES (?, ?, ?, ?)",
                (claim.fact_id, claim_text, state, tier),
            )
        except sqlite3.OperationalError:
            pass
        self.conn.commit()

    def get(self, fact_id: str) -> MemoryClaim | None:
        row = self.conn.execute(
            "SELECT payload FROM memory_claims WHERE fact_id = ?", (fact_id,)
        ).fetchone()
        if row is None:
            return None
        data = json.loads(row["payload"])
        return MemoryClaim(**data)

    def _build_fts_query(self, query: str) -> str:
        cleaned = re.sub(r'["()+\-~^*]', '', query)
        words = [w for w in cleaned.split() if w.upper() not in ('AND', 'OR', 'NOT', 'NEAR')]
        terms = [f'"{w}"*' for w in words if w]
        return ' AND '.join(terms)

    def search(self, query: str, limit: int = 10) -> list[MemorySearchResult]:
        try:
            fts_query = self._build_fts_query(query)
            rows = self.conn.execute(
                "SELECT payload FROM memory_claims "
                "WHERE fact_id IN ("
                "    SELECT fact_id FROM memory_claims_fts "
                "    WHERE claim_text MATCH ? "
                "    ORDER BY rank"
                ") LIMIT ?",
                (fts_query, limit),
            ).fetchall()
            return [MemorySearchResult.from_claim(MemoryClaim(**json.loads(row["payload"]))) for row in rows]
        except sqlite3.OperationalError:
            pass
        query_lower = query.lower()
        rows = self.conn.execute(
            "SELECT payload FROM memory_claims ORDER BY created_at DESC"
        ).fetchall()
        results: list[MemorySearchResult] = []
        for row in rows:
            data = json.loads(row["payload"])
            claim_text = data.get("claim", "").lower()
            if query_lower in claim_text:
                claim = MemoryClaim(**data)
                results.append(MemorySearchResult.from_claim(claim))
                if len(results) >= limit:
                    break
        return results

    def list_all(self) -> list[MemoryClaim]:
        rows = self.conn.execute(
            "SELECT payload FROM memory_claims ORDER BY created_at DESC"
        ).fetchall()
        return [MemoryClaim(**json.loads(row["payload"])) for row in rows]

    def delete(self, fact_id: str) -> bool:
        self.conn.execute("DELETE FROM memory_claims WHERE fact_id = ?", (fact_id,))
        self.conn.commit()
        return self.conn.total_changes > 0

    def count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS cnt FROM memory_claims").fetchone()
        return int(row["cnt"])

    def gc(self, before_timestamp: str) -> int:
        cursor = self.conn.execute(
            "DELETE FROM memory_claims WHERE created_at < ?",
            (before_timestamp,),
        )
        self.conn.commit()
        return cursor.rowcount

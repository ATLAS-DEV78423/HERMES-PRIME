from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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
        self.conn.commit()

    def store(self, claim: MemoryClaim) -> None:
        import sqlite3
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
        self.conn.commit()

    def get(self, fact_id: str) -> MemoryClaim | None:
        import sqlite3
        row = self.conn.execute(
            "SELECT payload FROM memory_claims WHERE fact_id = ?", (fact_id,)
        ).fetchone()
        if row is None:
            return None
        data = json.loads(row["payload"])
        return MemoryClaim(**data)

    def search(self, query: str, limit: int = 10) -> list[MemorySearchResult]:
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

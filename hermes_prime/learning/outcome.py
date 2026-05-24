from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from hermes_prime.contracts import ExecutionOutcome


class OutcomeStore:
    """Persistent SQLite-backed store for execution outcomes."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._init_db()

    def _init_db(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS outcomes (
                execution_id TEXT PRIMARY KEY,
                task_prompt TEXT,
                action_type TEXT,
                action_scope TEXT,
                approved INTEGER,
                blocking_layer INTEGER,
                denial_reason TEXT,
                parseable INTEGER,
                latency_ms REAL,
                tokens_used INTEGER,
                model TEXT,
                timestamp TEXT,
                outcome_labels TEXT
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_outcomes_timestamp
            ON outcomes(timestamp)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_outcomes_action_type
            ON outcomes(action_type)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_outcomes_approved
            ON outcomes(approved)
        """)
        self._conn.commit()

    def store(self, outcome: ExecutionOutcome) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO outcomes
            (execution_id, task_prompt, action_type, action_scope, approved,
             blocking_layer, denial_reason, parseable, latency_ms, tokens_used,
             model, timestamp, outcome_labels)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                outcome.execution_id,
                outcome.task_prompt,
                outcome.action_type,
                outcome.action_scope,
                1 if outcome.approved else 0,
                outcome.blocking_layer,
                outcome.denial_reason,
                1 if outcome.parseable else 0,
                outcome.latency_ms,
                outcome.tokens_used,
                outcome.model,
                outcome.timestamp,
                json.dumps(outcome.outcome_labels),
            ),
        )
        self._conn.commit()

    def get_recent(self, limit: int = 50) -> list[ExecutionOutcome]:
        rows = self._conn.execute(
            "SELECT * FROM outcomes ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_outcome(r) for r in rows]

    def get_since(self, timestamp: str) -> list[ExecutionOutcome]:
        rows = self._conn.execute(
            "SELECT * FROM outcomes WHERE timestamp > ? ORDER BY timestamp ASC",
            (timestamp,),
        ).fetchall()
        return [self._row_to_outcome(r) for r in rows]

    def get_by_action_type(self, action_type: str, limit: int = 100) -> list[ExecutionOutcome]:
        rows = self._conn.execute(
            "SELECT * FROM outcomes WHERE action_type = ? ORDER BY timestamp DESC LIMIT ?",
            (action_type, limit),
        ).fetchall()
        return [self._row_to_outcome(r) for r in rows]

    def get_metrics(self) -> dict[str, Any]:
        total = self._conn.execute("SELECT COUNT(*) FROM outcomes").fetchone()[0]
        if total == 0:
            return {"total": 0}

        approved = self._conn.execute("SELECT COUNT(*) FROM outcomes WHERE approved = 1").fetchone()[0]
        parseable_count = self._conn.execute("SELECT COUNT(*) FROM outcomes WHERE parseable = 1").fetchone()[0]
        rejected_total = self._conn.execute("SELECT COUNT(*) FROM outcomes WHERE parseable = 1 AND approved = 0").fetchone()[0]
        parse_failures = self._conn.execute("SELECT COUNT(*) FROM outcomes WHERE parseable = 0").fetchone()[0]

        avg_latency = self._conn.execute("SELECT AVG(latency_ms) FROM outcomes").fetchone()[0] or 0.0
        avg_tokens = self._conn.execute("SELECT AVG(tokens_used) FROM outcomes").fetchone()[0] or 0.0

        blocking_layers = self._conn.execute(
            "SELECT blocking_layer, COUNT(*) as cnt FROM outcomes WHERE approved = 0 AND blocking_layer IS NOT NULL GROUP BY blocking_layer ORDER BY cnt DESC"
        ).fetchall()

        return {
            "total": total,
            "approved": approved,
            "rejected_by_sentinel": rejected_total,
            "parse_failures": parse_failures,
            "approval_rate": round(approved / total, 3) if total else 0.0,
            "parse_rate": round(parseable_count / total, 3) if total else 0.0,
            "avg_latency_ms": round(avg_latency, 1),
            "avg_tokens": round(avg_tokens, 1),
            "blocking_layer_distribution": {str(r[0]): r[1] for r in blocking_layers},
        }

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM outcomes").fetchone()[0]

    def close(self) -> None:
        self._conn.close()

    def _row_to_outcome(self, row: sqlite3.Row) -> ExecutionOutcome:
        return ExecutionOutcome(
            execution_id=row[0],
            task_prompt=row[1],
            action_type=row[2],
            action_scope=row[3],
            approved=bool(row[4]),
            blocking_layer=row[5],
            denial_reason=row[6],
            parseable=bool(row[7]),
            latency_ms=row[8],
            tokens_used=row[9],
            model=row[10],
            timestamp=row[11],
            outcome_labels=json.loads(row[12]) if row[12] else [],
        )


class OutcomeTracker:
    """Tracks execution outcomes and feeds them to the learning loop."""

    def __init__(self, store: OutcomeStore):
        self.store = store

    def record(
        self,
        execution_id: str,
        task_prompt: str,
        action_type: str,
        action_scope: str,
        approved: bool,
        parseable: bool,
        latency_ms: float,
        tokens_used: int,
        model: str,
        timestamp: str,
        blocking_layer: int | None = None,
        denial_reason: str | None = None,
        outcome_labels: list[str] | None = None,
    ) -> ExecutionOutcome:
        outcome = ExecutionOutcome(
            execution_id=execution_id,
            task_prompt=task_prompt,
            action_type=action_type,
            action_scope=action_scope,
            approved=approved,
            blocking_layer=blocking_layer,
            denial_reason=denial_reason,
            parseable=parseable,
            latency_ms=latency_ms,
            tokens_used=tokens_used,
            model=model,
            timestamp=timestamp,
            outcome_labels=outcome_labels or [],
        )
        self.store.store(outcome)
        return outcome

    def get_summary(self) -> dict[str, Any]:
        return self.store.get_metrics()

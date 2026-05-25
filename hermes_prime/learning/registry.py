from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from hermes_prime.contracts import LearnedPattern


class LearningRegistry:
    """Persistent store for learned patterns that improve agent performance.

    Backed by SQLite (.db) for concurrency and performance, or JSON (.json)
    for backward compatibility.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._use_sqlite = self.path.suffix == ".db"
        if self._use_sqlite:
            self._conn = sqlite3.connect(str(self.path))
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._init_db()
        else:
            self._conn = None
            self._patterns: dict[str, LearnedPattern] = {}
            self._load_json()

    def _init_db(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS learned_patterns (
                pattern_id TEXT PRIMARY KEY,
                pattern_type TEXT NOT NULL,
                content TEXT NOT NULL,
                confidence REAL NOT NULL,
                source_outcomes TEXT NOT NULL DEFAULT '[]',
                action_types TEXT NOT NULL DEFAULT '[]',
                tags TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                last_applied_at TEXT,
                application_count INTEGER NOT NULL DEFAULT 0,
                success_rate REAL NOT NULL DEFAULT 0.0
            )
        """)
        self._conn.commit()

    # ── JSON backend ──────────────────────────────────────────────────────

    def _load_json(self) -> None:
        if self.path.exists():
            data = json.loads(self.path.read_text("utf-8"))
            for item in data.get("patterns", []):
                pattern = LearnedPattern(**item)
                self._patterns[pattern.pattern_id] = pattern

    def _save_json(self) -> None:
        data = {
            "patterns": [p.to_dict() for p in self._patterns.values()],
        }
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True), "utf-8")

    # ── SQLite helpers ────────────────────────────────────────────────────

    def _row_to_pattern(self, row: tuple) -> LearnedPattern:
        return LearnedPattern(
            pattern_id=row[0],
            pattern_type=row[1],
            content=row[2],
            confidence=row[3],
            source_outcomes=json.loads(row[4]),
            action_types=json.loads(row[5]),
            tags=json.loads(row[6]),
            created_at=row[7],
            last_applied_at=row[8],
            application_count=row[9],
            success_rate=row[10],
        )

    def _pattern_to_row(self, p: LearnedPattern) -> tuple:
        return (
            p.pattern_id,
            p.pattern_type,
            p.content,
            p.confidence,
            json.dumps(p.source_outcomes),
            json.dumps(p.action_types),
            json.dumps(p.tags),
            p.created_at,
            p.last_applied_at,
            p.application_count,
            p.success_rate,
        )

    def _upsert(self, pattern: LearnedPattern) -> None:
        if self._use_sqlite:
            self._conn.execute(
                """INSERT OR REPLACE INTO learned_patterns
                   (pattern_id, pattern_type, content, confidence,
                    source_outcomes, action_types, tags,
                    created_at, last_applied_at,
                    application_count, success_rate)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                self._pattern_to_row(pattern),
            )
            self._conn.commit()
        else:
            self._patterns[pattern.pattern_id] = pattern
            self._save_json()

    def _delete(self, pattern_id: str) -> bool:
        if self._use_sqlite:
            cur = self._conn.execute(
                "DELETE FROM learned_patterns WHERE pattern_id = ?",
                (pattern_id,),
            )
            self._conn.commit()
            return cur.rowcount > 0
        else:
            if pattern_id in self._patterns:
                del self._patterns[pattern_id]
                self._save_json()
                return True
            return False

    # ── Public API ────────────────────────────────────────────────────────

    def register(self, pattern: LearnedPattern) -> None:
        self._upsert(pattern)

    def get(self, pattern_id: str) -> LearnedPattern | None:
        if self._use_sqlite:
            cur = self._conn.execute(
                "SELECT * FROM learned_patterns WHERE pattern_id = ?",
                (pattern_id,),
            )
            row = cur.fetchone()
            return self._row_to_pattern(row) if row else None
        return self._patterns.get(pattern_id)

    def list_patterns(
        self,
        pattern_type: str | None = None,
        min_confidence: float = 0.0,
        action_type: str | None = None,
        limit: int = 20,
    ) -> list[LearnedPattern]:
        if self._use_sqlite:
            clauses: list[str] = []
            params: list[Any] = []
            if pattern_type:
                clauses.append("pattern_type = ?")
                params.append(pattern_type)
            if min_confidence > 0:
                clauses.append("confidence >= ?")
                params.append(min_confidence)
            if action_type:
                clauses.append("action_types LIKE ?")
                params.append(f"%{action_type}%")
            where = " AND ".join(clauses) if clauses else "1"
            sql = f"SELECT * FROM learned_patterns WHERE {where} ORDER BY confidence DESC LIMIT ?"
            params.append(limit)
            rows = self._conn.execute(sql, params).fetchall()
            return [self._row_to_pattern(r) for r in rows]

        results = list(self._patterns.values())
        if pattern_type:
            results = [p for p in results if p.pattern_type == pattern_type]
        if min_confidence > 0:
            results = [p for p in results if p.confidence >= min_confidence]
        if action_type:
            results = [p for p in results if action_type in p.action_types]
        results.sort(key=lambda p: p.confidence, reverse=True)
        return results[:limit]

    def get_active_instructions(self, action_types: list[str] | None = None) -> list[LearnedPattern]:
        results = self.list_patterns(
            pattern_type="prompt_instruction",
            min_confidence=0.6,
            action_type=action_types[0] if action_types else None,
        )
        return results[:10]

    def get_active_heuristics(self, action_types: list[str] | None = None) -> list[LearnedPattern]:
        results = self.list_patterns(
            pattern_type="action_heuristic",
            min_confidence=0.5,
            action_type=action_types[0] if action_types else None,
        )
        return results[:10]

    def record_application(self, pattern_id: str, success: bool) -> None:
        pattern = self.get(pattern_id)
        if pattern is None:
            return
        from hermes_prime.utils import utc_now_iso
        pattern.last_applied_at = utc_now_iso()
        pattern.application_count += 1
        old_total = pattern.application_count - 1
        pattern.success_rate = ((pattern.success_rate * old_total) + (1.0 if success else 0.0)) / pattern.application_count
        self._upsert(pattern)

    def remove(self, pattern_id: str) -> bool:
        return self._delete(pattern_id)

    def count(self) -> int:
        if self._use_sqlite:
            row = self._conn.execute("SELECT COUNT(*) FROM learned_patterns").fetchone()
            return row[0]
        return len(self._patterns)

    def close(self) -> None:
        if self._use_sqlite and self._conn:
            self._conn.close()

    def get_metrics(self) -> dict[str, Any]:
        if self._use_sqlite:
            total = self.count()
            row = self._conn.execute(
                "SELECT pattern_type, COUNT(*) FROM learned_patterns GROUP BY pattern_type"
            ).fetchall()
            by_type = {r[0]: r[1] for r in row}
            avg_row = self._conn.execute(
                "SELECT COALESCE(ROUND(AVG(confidence), 3), 0.0) FROM learned_patterns"
            ).fetchone()
            avg_confidence = avg_row[0]
            return {
                "total_patterns": total,
                "by_type": by_type,
                "avg_confidence": avg_confidence,
            }

        types: dict[str, int] = {}
        for p in self._patterns.values():
            types[p.pattern_type] = types.get(p.pattern_type, 0) + 1
        return {
            "total_patterns": self.count(),
            "by_type": types,
            "avg_confidence": round(
                sum(p.confidence for p in self._patterns.values()) / self.count(), 3
            ) if self._patterns else 0.0,
        }

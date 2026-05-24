from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hermes_prime.contracts import LearnedPattern


class LearningRegistry:
    """Persistent store for learned patterns that improve agent performance."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._patterns: dict[str, LearnedPattern] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            data = json.loads(self.path.read_text("utf-8"))
            for item in data.get("patterns", []):
                pattern = LearnedPattern(**item)
                self._patterns[pattern.pattern_id] = pattern

    def _save(self) -> None:
        data = {
            "patterns": [p.to_dict() for p in self._patterns.values()],
        }
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True), "utf-8")

    def register(self, pattern: LearnedPattern) -> None:
        self._patterns[pattern.pattern_id] = pattern
        self._save()

    def get(self, pattern_id: str) -> LearnedPattern | None:
        return self._patterns.get(pattern_id)

    def list_patterns(
        self,
        pattern_type: str | None = None,
        min_confidence: float = 0.0,
        action_type: str | None = None,
        limit: int = 20,
    ) -> list[LearnedPattern]:
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
        pattern = self._patterns.get(pattern_id)
        if pattern is None:
            return
        from hermes_prime.utils import utc_now_iso
        pattern.last_applied_at = utc_now_iso()
        pattern.application_count += 1
        old_total = pattern.application_count - 1
        pattern.success_rate = ((pattern.success_rate * old_total) + (1.0 if success else 0.0)) / pattern.application_count
        self._save()

    def remove(self, pattern_id: str) -> bool:
        if pattern_id in self._patterns:
            del self._patterns[pattern_id]
            self._save()
            return True
        return False

    def count(self) -> int:
        return len(self._patterns)

    def get_metrics(self) -> dict[str, Any]:
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

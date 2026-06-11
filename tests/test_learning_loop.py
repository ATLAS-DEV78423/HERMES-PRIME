"""Functional tests for the learning loop subsystem."""

from __future__ import annotations

import os
import tempfile

from hermes_prime.learning.outcome import OutcomeStore, OutcomeTracker
from hermes_prime.learning.registry import LearningRegistry
from hermes_prime.learning.engine import LearningEngine
from hermes_prime.learning.augmenter import PromptAugmenter
from hermes_prime.utils import new_urn_uuid, utc_now_iso


def test_outcome_tracking():
    with tempfile.TemporaryDirectory() as tmp:
        outcome_store = OutcomeStore(os.path.join(tmp, "outcomes.db"))
        tracker = OutcomeTracker(outcome_store)

        for i in range(10):
            tracker.record(
                execution_id=new_urn_uuid(),
                task_prompt=f"test task {i}",
                action_type="filesystem.read" if i % 2 == 0 else "filesystem.write",
                action_scope="/workspace/test",
                approved=i < 7,
                parseable=True,
                latency_ms=1000 + i * 100,
                tokens_used=100 + i * 10,
                model="test-model",
                timestamp=utc_now_iso(),
                blocking_layer=2 if i >= 7 else None,
                denial_reason="scope violation" if i >= 7 else None,
            )

        metrics = outcome_store.get_metrics()
        assert metrics["total"] == 10
        assert metrics["approved"] == 7
        assert metrics["rejected_by_sentinel"] == 3
        assert metrics["parse_failures"] == 0

        recent = outcome_store.get_recent(limit=5)
        assert len(recent) == 5

        by_type = outcome_store.get_by_action_type("filesystem.read", limit=10)
        assert len(by_type) == 5

        outcome_store.close()


def test_learning_registry():
    with tempfile.TemporaryDirectory() as tmp:
        registry = LearningRegistry(os.path.join(tmp, "patterns.json"))

        from hermes_prime.contracts import LearnedPattern

        p1 = LearnedPattern(
            pattern_id=new_urn_uuid(),
            pattern_type="prompt_instruction",
            content="Always output valid JSON.",
            confidence=0.8,
            source_outcomes=[],
            action_types=["filesystem.read"],
            tags=["output_format"],
            created_at=utc_now_iso(),
        )
        p2 = LearnedPattern(
            pattern_id=new_urn_uuid(),
            pattern_type="action_heuristic",
            content="Prefer filesystem.read for text tasks.",
            confidence=0.7,
            source_outcomes=[],
            action_types=["filesystem.read"],
            tags=["heuristic"],
            created_at=utc_now_iso(),
        )

        registry.register(p1)
        registry.register(p2)
        assert registry.count() == 2

        by_type = registry.list_patterns(pattern_type="prompt_instruction")
        assert len(by_type) == 1
        assert by_type[0].pattern_id == p1.pattern_id

        by_confidence = registry.list_patterns(min_confidence=0.75)
        assert len(by_confidence) == 1
        assert by_confidence[0].pattern_id == p1.pattern_id

        registry.record_application(p1.pattern_id, success=True)
        updated = registry.get(p1.pattern_id)
        assert updated is not None
        assert updated.application_count == 1
        assert updated.success_rate == 1.0

        registry.record_application(p1.pattern_id, success=False)
        updated = registry.get(p1.pattern_id)
        assert updated.application_count == 2
        assert updated.success_rate == 0.5

        registry.remove(p2.pattern_id)
        assert registry.count() == 1

        active = registry.get_active_instructions(action_types=["filesystem.read"])
        assert len(active) == 1

        metrics = registry.get_metrics()
        assert metrics["total_patterns"] == 1


def test_learning_engine():
    with tempfile.TemporaryDirectory() as tmp:
        outcome_store = OutcomeStore(os.path.join(tmp, "outcomes.db"))
        registry = LearningRegistry(os.path.join(tmp, "patterns.json"))
        engine = LearningEngine(outcome_store, registry)

        status = engine.status()
        assert status["ready_to_learn"] is False
        assert status["outcomes"]["total"] == 0

        # Record 10 outcomes
        tracker = OutcomeTracker(outcome_store)
        for i in range(10):
            tracker.record(
                execution_id=new_urn_uuid(),
                task_prompt=f"test task {i}",
                action_type="filesystem.read" if i % 2 == 0 else "filesystem.write",
                action_scope="/workspace/test",
                approved=i < 7,
                parseable=True,
                latency_ms=1000 + i * 100,
                tokens_used=100 + i * 10,
                model="test-model",
                timestamp=utc_now_iso(),
                blocking_layer=2 if i >= 7 else None,
                denial_reason="scope violation" if i >= 7 else None,
            )

        # Reflect
        result = engine.reflect(min_outcomes=5)
        assert result["reflected"]
        assert result["patterns_created"] > 0

        # Second reflection shouldn't duplicate patterns
        result2 = engine.reflect(min_outcomes=5)
        assert result2.get("patterns_created", 0) == 0

        status = engine.status()
        assert status["ready_to_learn"] is True
        assert status["outcomes"]["total"] == 10

        # Test with parse failures too
        for i in range(3):
            tracker.record(
                execution_id=new_urn_uuid(),
                task_prompt=f"bad task {i}",
                action_type="execution.command",
                action_scope="/workspace/test",
                approved=False,
                parseable=False,
                latency_ms=500,
                tokens_used=50,
                model="test-model",
                timestamp=utc_now_iso(),
            )

        result3 = engine.reflect(min_outcomes=5)
        assert result3["reflected"]
        outcome_store.close()


def test_prompt_augmenter():
    with tempfile.TemporaryDirectory() as tmp:
        registry = LearningRegistry(os.path.join(tmp, "patterns.json"))

        from hermes_prime.contracts import LearnedPattern

        p1 = LearnedPattern(
            pattern_id=new_urn_uuid(),
            pattern_type="prompt_instruction",
            content="Always output valid JSON within fences.",
            confidence=0.8,
            source_outcomes=[],
            action_types=["filesystem.read"],
            tags=["output_format"],
            created_at=utc_now_iso(),
        )
        registry.register(p1)

        p2 = LearnedPattern(
            pattern_id=new_urn_uuid(),
            pattern_type="task_pattern",
            content="Read tasks succeed reliably.",
            confidence=0.6,
            source_outcomes=[],
            action_types=["filesystem.read"],
            tags=["read"],
            created_at=utc_now_iso(),
        )
        registry.register(p2)

        augmenter = PromptAugmenter(registry)

        guidance = augmenter.build_augmentation_block(
            "read some files", action_type="filesystem.read"
        )
        assert len(guidance) > 0

        # Task should match the task pattern tag
        assert "Read tasks" in guidance or "Always output" in guidance


if __name__ == "__main__":
    test_outcome_tracking()
    test_learning_registry()
    test_learning_engine()
    test_prompt_augmenter()

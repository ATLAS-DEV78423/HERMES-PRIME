from __future__ import annotations

from typing import Any

from hermes_prime.contracts import LearnedPattern
from hermes_prime.learning.outcome import OutcomeStore
from hermes_prime.learning.registry import LearningRegistry
from hermes_prime.memory.store import MemoryStore
from hermes_prime.memory.consolidation import ConsolidationRequest, ReflectiveConsolidator
from hermes_prime.utils import new_urn_uuid, utc_now_iso


class LearningEngine:
    """Periodic reflection engine that extracts patterns from past outcomes.

    The learning engine reviews execution outcomes, identifies what works and
    what doesn't, and registers learned patterns that improve future behavior.
    """

    def __init__(
        self,
        outcome_store: OutcomeStore,
        registry: LearningRegistry,
        memory_store: MemoryStore | None = None,
        reflection_interval: int = 10,
    ):
        self.outcome_store = outcome_store
        self.registry = registry
        self.memory_store = memory_store
        self._reflection_interval = reflection_interval
        self.consolidator = ReflectiveConsolidator(memory_store) if memory_store else None

    @property
    def reflection_interval(self) -> int:
        return self._reflection_interval

    def reflect(self, min_outcomes: int = 5) -> dict[str, Any]:
        """Run one reflection cycle: review outcomes, extract patterns, store learnings."""
        metrics = self.outcome_store.get_metrics()
        total = metrics.get("total", 0)
        if total < min_outcomes:
            return {
                "reflected": False,
                "reason": f"only {total} outcomes available, need {min_outcomes}",
                "patterns_created": 0,
            }

        outcomes = self.outcome_store.get_recent(limit=100)
        patterns_created = 0

        patterns_created += self._extract_approval_patterns(outcomes, metrics)
        patterns_created += self._extract_rejection_patterns(outcomes, metrics)
        patterns_created += self._extract_task_patterns(outcomes)
        patterns_created += self._extract_efficiency_patterns(outcomes, metrics)

        if self.consolidator:
            self._consolidate_learnings()

        return {
            "reflected": True,
            "total_outcomes_reviewed": len(outcomes),
            "patterns_created": patterns_created,
            "metrics": metrics,
        }

    def _extract_approval_patterns(self, outcomes: list, metrics: dict) -> int:
        """Extract patterns from actions that were approved by Sentinel."""
        approved = [o for o in outcomes if o.approved]
        if len(approved) < 3:
            return 0

        type_counts: dict[str, int] = {}
        for o in approved:
            type_counts[o.action_type] = type_counts.get(o.action_type, 0) + 1

        dominant_type = max(type_counts, key=type_counts.get)
        type_rate = type_counts[dominant_type] / len(approved)

        if type_rate > 0.6 and not self.registry.list_patterns(
            pattern_type="action_heuristic", action_type=dominant_type
        ):
            pattern = LearnedPattern(
                pattern_id=new_urn_uuid(),
                pattern_type="action_heuristic",
                content=(
                    f"Actions of type '{dominant_type}' have high approval rate "
                    f"({type_rate:.0%} of approved actions). Prefer this action type "
                    f"when the task fits its scope."
                ),
                confidence=min(type_rate, 0.9),
                source_outcomes=[o.execution_id for o in approved[:5]],
                action_types=[dominant_type],
                tags=["approval_pattern", dominant_type],
                created_at=utc_now_iso(),
                success_rate=type_rate,
            )
            self.registry.register(pattern)
            return 1
        return 0

    def _extract_rejection_patterns(self, outcomes: list, metrics: dict) -> int:
        """Extract patterns from actions that were rejected or failed parsing."""
        rejected = [o for o in outcomes if not o.approved and o.parseable]
        parse_failures = [o for o in outcomes if not o.parseable]

        created = 0

        if len(rejected) >= 3:
            layer_counts: dict[int, int] = {}
            for o in rejected:
                if o.blocking_layer is not None:
                    layer_counts[o.blocking_layer] = layer_counts.get(o.blocking_layer, 0) + 1

            if layer_counts:
                most_blocked = max(layer_counts, key=layer_counts.get)
                block_rate = layer_counts[most_blocked] / len(rejected)

                if block_rate > 0.4 and not self.registry.list_patterns(
                    pattern_type="prompt_instruction"
                ):
                    pattern = LearnedPattern(
                        pattern_id=new_urn_uuid(),
                        pattern_type="prompt_instruction",
                        content=(
                            f"Sentinel Layer {most_blocked} frequently blocks proposals "
                            f"({block_rate:.0%} of rejections). Ensure proposed actions "
                            f"comply with layer {most_blocked} rules: verify scope containment, "
                            f"avoid shell metacharacters, stay within workspace boundaries."
                        ),
                        confidence=min(block_rate, 0.85),
                        source_outcomes=[o.execution_id for o in rejected[:5]],
                        action_types=list({o.action_type for o in rejected}),
                        tags=["rejection_pattern", f"layer_{most_blocked}"],
                        created_at=utc_now_iso(),
                        success_rate=0.0,
                    )
                    self.registry.register(pattern)
                    created += 1

        if len(parse_failures) >= 3:
            pattern = LearnedPattern(
                pattern_id=new_urn_uuid(),
                pattern_type="prompt_instruction",
                content=(
                    f"Output parsing has a {metrics.get('parse_failures', 0)} failure rate. "
                    f"Always output proposals as valid JSON within ```json ... ``` fences. "
                    f"Never include explanatory text outside the fences."
                ),
                confidence=0.7,
                source_outcomes=[o.execution_id for o in parse_failures[:5]],
                action_types=list({o.action_type for o in parse_failures}),
                tags=["parse_failure", "output_format"],
                created_at=utc_now_iso(),
                success_rate=0.0,
            )
            self.registry.register(pattern)
            created += 1

        return created

    def _extract_task_patterns(self, outcomes: list) -> int:
        """Extract patterns about what types of tasks are handled well."""
        from collections import Counter
        task_keywords: Counter = Counter()
        approved_tasks = [o.task_prompt for o in outcomes if o.approved]

        if len(approved_tasks) < 3:
            return 0

        for task in approved_tasks:
            for word in task.lower().split()[:5]:
                if len(word) > 3:
                    task_keywords[word] += 1

        common = task_keywords.most_common(3)
        keyword_str = ", ".join(f"'{w}'" for w, _ in common)

        if common and not self.registry.list_patterns(pattern_type="task_pattern"):
            pattern = LearnedPattern(
                pattern_id=new_urn_uuid(),
                pattern_type="task_pattern",
                content=(
                    f"Tasks mentioning {keyword_str} have high success rates. "
                    f"When these keywords appear, the agent can proceed confidently "
                    f"with standard action proposals."
                ),
                confidence=0.6,
                source_outcomes=[o.execution_id for o in outcomes if o.approved][:3],
                action_types=["filesystem.read", "miner.dispatch"],
                tags=["task_pattern", "keywords"],
                created_at=utc_now_iso(),
                success_rate=0.8,
            )
            self.registry.register(pattern)
            return 1
        return 0

    def _extract_efficiency_patterns(self, outcomes: list, metrics: dict) -> int:
        """Extract patterns about token usage and latency."""
        high_latency = [o for o in outcomes if o.latency_ms > 5000]
        if len(high_latency) >= 3:
            pattern = LearnedPattern(
                pattern_id=new_urn_uuid(),
                pattern_type="prompt_instruction",
                content=(
                    f"Average inference latency is {metrics.get('avg_latency_ms', 0)}ms "
                    f"with {metrics.get('avg_tokens', 0)} tokens per call. "
                    f"Keep proposals concise to minimize token usage."
                ),
                confidence=0.5,
                source_outcomes=[o.execution_id for o in high_latency[:3]],
                action_types=list({o.action_type for o in high_latency}),
                tags=["efficiency", "latency", "tokens"],
                created_at=utc_now_iso(),
                success_rate=0.0,
            )
            self.registry.register(pattern)
            return 1
        return 0

    def _consolidate_learnings(self) -> None:
        """Write a reflective summary of learnings to the memory fabric."""
        if not self.consolidator or not self.memory_store:
            return

        patterns = self.registry.list_patterns(min_confidence=0.5, limit=10)
        if not patterns:
            return

        pattern_summaries = []
        for p in patterns:
            pattern_summaries.append({
                "text": p.content,
                "type": p.pattern_type,
                "source_fact_ids": p.source_outcomes[:3],
            })

        summary = (
            f"Learning loop reflected on {self.outcome_store.count()} execution outcomes. "
            f"Active patterns: {', '.join(p.pattern_type for p in patterns[:5])}. "
            f"Key insight: {patterns[0].content[:120]}"
        )

        dummy_intent = None
        try:
            from hermes_prime.contracts import IntentRoot
            from hermes_prime.secrets import get_signer as _get_signer
            signer = _get_signer("learning")
            sig = signer.sign(b"learning-reflection")
            dummy_intent = IntentRoot(
                intent_root=new_urn_uuid(),
                scope="hermes-prime://learning/reflection",
                issued_to="system:learning-engine",
                issued_at=utc_now_iso(),
                expires_at=utc_now_iso(),
                signature=sig,
            )
        except Exception:
            return

        request = ConsolidationRequest(
            intent_root=dummy_intent,
            summary=summary,
            patterns=pattern_summaries,
        )
        self.consolidator.consolidate(request)

    def status(self) -> dict[str, Any]:
        outcome_metrics = self.outcome_store.get_metrics()
        registry_metrics = self.registry.get_metrics()
        return {
            "outcomes": outcome_metrics,
            "learned_patterns": registry_metrics,
            "ready_to_learn": outcome_metrics.get("total", 0) >= 5,
        }

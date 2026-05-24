from __future__ import annotations

from hermes_prime.learning.registry import LearningRegistry


class PromptAugmenter:
    """Injects learned patterns into prompts to improve LLM output."""

    def __init__(self, registry: LearningRegistry):
        self.registry = registry

    def build_augmentation_block(self, task: str, action_type: str | None = None) -> str:
        """Build a string of learned guidance to inject into the user prompt."""
        parts: list[str] = []

        instructions = self.registry.get_active_instructions(
            action_types=[action_type] if action_type else None
        )
        heuristics = self.registry.get_active_heuristics(
            action_types=[action_type] if action_type else None
        )

        relevant_task_patterns = self._match_task_patterns(task)
        all_patterns = instructions + heuristics + relevant_task_patterns

        if not all_patterns:
            return ""

        for p in all_patterns:
            parts.append(f"- {p.content}")

        block = "\n".join(parts)
        return f"\nLEARNED GUIDANCE (from past executions):\n{block}\n"

    def _match_task_patterns(self, task: str) -> list:
        patterns = self.registry.list_patterns(pattern_type="task_pattern", min_confidence=0.5)
        task_lower = task.lower()
        matched = []
        for p in patterns:
            for tag in p.tags:
                if tag in task_lower:
                    matched.append(p)
                    break
        return matched

    def record_application_result(self, pattern_ids: list[str], success: bool) -> None:
        for pid in pattern_ids:
            self.registry.record_application(pid, success)

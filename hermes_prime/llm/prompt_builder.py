from __future__ import annotations

from typing import Any, Optional


class PromptBuilder:
    """Assembles structured prompts for LLM inference from task context."""

    def __init__(self, workspace_root: str, fabric_patterns: Optional[dict[str, Any]] = None):
        self.workspace_root = workspace_root
        self.fabric_patterns = fabric_patterns or {}

    def build_system_prompt(self) -> str:
        """Build system prompt that instructs LLM about governance constraints."""
        return """You are Hermes Prime, a governed autonomous agent operating within strict security boundaries.

CRITICAL CONSTRAINTS:
1. You must propose actions as JSON proposals, never execute directly.
2. Every action you propose is automatically evaluated by the Sentinel policy engine.
3. Dangerous actions (code execution, file writes outside scope) will be REJECTED.
4. You have NO direct filesystem, network, or execution access.
5. You can only READ files within the workspace scope.

ACTION PROPOSAL FORMAT:
For each action, respond with a JSON block:
```json
{
  "action_type": "filesystem.read|filesystem.write|execution.command|miner.dispatch",
  "scope": "/path/to/resource",
  "risk_tier": "T0|T1|T2|T3|T4|T5",
  "capability": "cap:file-read:scoped|cap:file-write:scoped|cap:general:scoped",
  "parameters": {
    "reason": "why this action is needed",
    "details": "any additional context"
  }
}
```

Respond with ONLY the JSON proposal. No preamble or commentary."""

    def build_user_prompt(
        self,
        task: str,
        file_context: Optional[list[str]] = None,
        recent_actions: Optional[list[dict[str, Any]]] = None,
    ) -> str:
        """Build user prompt with task + context."""
        prompt_parts = [f"Task: {task}"]

        if file_context:
            prompt_parts.append("\nRelevant files:")
            for file_path in file_context[:5]:  # Limit to 5 files
                prompt_parts.append(f"  - {file_path}")

        if recent_actions:
            prompt_parts.append("\nRecent approved actions:")
            for action in recent_actions[-3:]:  # Limit to 3 recent actions
                prompt_parts.append(f"  - {action.get('action_type')}: {action.get('scope')}")

        prompt_parts.append("\nPropose your next action as a JSON block.")
        return "\n".join(prompt_parts)

    def build_messages(
        self,
        task: str,
        file_context: Optional[list[str]] = None,
        recent_actions: Optional[list[dict[str, Any]]] = None,
    ) -> list[dict[str, str]]:
        """Build OpenAI-compatible message list."""
        return [
            {"role": "system", "content": self.build_system_prompt()},
            {
                "role": "user",
                "content": self.build_user_prompt(task, file_context, recent_actions),
            },
        ]

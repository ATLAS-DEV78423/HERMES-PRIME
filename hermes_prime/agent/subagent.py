from __future__ import annotations

import json
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hermes_prime.agent.loop import AgentLoop
from hermes_prime.agent.types import AgentContext, AgentResult
from hermes_prime.llm.client import LLMClient


@dataclass
class SubagentTask:
    id: str
    prompt: str
    model: str
    status: str = "pending"
    result: AgentResult | None = None
    error: str | None = None


@dataclass
class SubagentManager:
    """Manages subagent spawning and result collection for agent-to-agent delegation."""

    llm_client: LLMClient
    workspace_root: str | Path = "."
    max_workers: int = 4
    _pool: ThreadPoolExecutor = field(default_factory=lambda: ThreadPoolExecutor(max_workers=4))
    _tasks: dict[str, SubagentTask] = field(default_factory=dict)

    def spawn(
        self,
        prompt: str,
        model: str | None = None,
        tools: list[tuple[str, Any, str]] | None = None,
    ) -> SubagentTask:
        """Spawn a subagent to handle a subtask concurrently."""
        task_id = str(uuid.uuid4())
        task = SubagentTask(id=task_id, prompt=prompt, model=model or "mistral")
        self._tasks[task_id] = task

        future = self._pool.submit(self._run_subagent, task, tools or [])
        future.add_done_callback(lambda f: self._on_complete(task_id, f))
        return task

    def _run_subagent(self, task: SubagentTask, tools: list[tuple[str, Any, str]]) -> AgentResult:
        loop = AgentLoop(
            workspace_root=str(self.workspace_root),
            llm_client=self.llm_client,
        )
        for name, fn, desc in tools:
            loop.register_tool(name, fn, desc)

        ctx = AgentContext(
            workspace_root=str(self.workspace_root),
            model=task.model,
            max_iterations=10,
        )
        result = loop.run(task.prompt, context=ctx)
        return result

    def _on_complete(self, task_id: str, future: Future) -> None:
        task = self._tasks.get(task_id)
        if not task:
            return
        try:
            task.result = future.result()
            task.status = "completed"
        except Exception as e:
            task.error = str(e)
            task.status = "failed"

    def get_result(self, task_id: str, timeout: float | None = None) -> SubagentTask | None:
        """Get task result, optionally blocking until complete."""
        task = self._tasks.get(task_id)
        if not task:
            return None
        if task.status == "pending":
            import time
            deadline = (time.monotonic() + timeout) if timeout else None
            while task.status == "pending":
                if deadline and time.monotonic() > deadline:
                    break
                time.sleep(0.1)
        return task

    def map_reduce(
        self,
        subtasks: list[str],
        reducer_prompt: str,
        model: str | None = None,
        tool_fns: list[tuple[str, Any, str]] | None = None,
    ) -> AgentResult:
        """Spawn multiple subagents, collect results, reduce via LLM."""
        spawned = [self.spawn(p, model=model, tools=tool_fns) for p in subtasks]
        results = []
        for task in spawned:
            completed = self.get_result(task.id, timeout=120)
            if completed and completed.result:
                results.append(completed.result.summary)
            else:
                results.append(f"[{task.id}] error: {task.error or 'timeout'}")

        combined = "\n\n".join(f"--- Subtask ---\n{r}" for r in results)
        reduce_prompt = f"{reducer_prompt}\n\nSubtask results:\n{combined}"

        return self._run_subagent(
            SubagentTask(id="reduce", prompt=reduce_prompt, model=model or "mistral"),
            tool_fns or [],
        )

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False)

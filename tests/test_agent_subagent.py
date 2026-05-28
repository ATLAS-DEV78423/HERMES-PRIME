from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from hermes_prime.agent.types import AgentResult


@pytest.fixture
def mock_llm_client():
    return MagicMock()


@pytest.fixture
def mock_agent_result():
    return AgentResult(
        session_id="test-session",
        messages=[],
        tool_calls=[],
        summary="Completed task.",
        success=True,
    )


class TestSubagentTask:
    def test_task_creation_defaults(self):
        from hermes_prime.agent.subagent import SubagentTask

        task = SubagentTask(id="t1", prompt="do something", model="mistral")
        assert task.id == "t1"
        assert task.prompt == "do something"
        assert task.model == "mistral"
        assert task.status == "pending"
        assert task.result is None
        assert task.error is None


class TestSubagentManagerSpawn:
    @patch("hermes_prime.agent.subagent.AgentLoop")
    def test_spawn_creates_task_with_pending_status(self, MockLoop, mock_llm_client):
        import threading
        block = threading.Event()
        MockLoop.return_value.run.side_effect = lambda *a, **kw: block.wait()

        from hermes_prime.agent.subagent import SubagentManager

        mgr = SubagentManager(llm_client=mock_llm_client, max_workers=1)
        task = mgr.spawn(prompt="test prompt", model="llama3")
        assert task.id is not None
        assert task.prompt == "test prompt"
        assert task.model == "llama3"
        assert task.status == "pending"
        assert task.id in mgr._tasks
        block.set()
        mgr.shutdown()

    @patch("hermes_prime.agent.subagent.AgentLoop")
    def test_spawn_defaults_model_to_mistral(self, MockLoop, mock_llm_client):
        from hermes_prime.agent.subagent import SubagentManager

        mgr = SubagentManager(llm_client=mock_llm_client, max_workers=1)
        task = mgr.spawn(prompt="test")
        assert task.model == "mistral"
        mgr.shutdown()


class TestSubagentManagerRunSubagent:
    def test_run_subagent_creates_loop_and_runs(self, mock_llm_client, mock_agent_result):
        with patch("hermes_prime.agent.subagent.AgentLoop") as MockLoop:
            mock_loop_instance = MagicMock()
            mock_loop_instance.run.return_value = mock_agent_result
            MockLoop.return_value = mock_loop_instance

            from hermes_prime.agent.subagent import SubagentManager, SubagentTask

            mgr = SubagentManager(llm_client=mock_llm_client)
            task = SubagentTask(id="t1", prompt="my task", model="mistral")
            result = mgr._run_subagent(task, tools=[])

            assert result is mock_agent_result
            MockLoop.assert_called_once_with(
                workspace_root=".",
                llm_client=mock_llm_client,
            )
            mock_loop_instance.run.assert_called_once()
            mgr.shutdown()

    def test_run_subagent_registers_tools(self, mock_llm_client, mock_agent_result):
        with patch("hermes_prime.agent.subagent.AgentLoop") as MockLoop:
            mock_loop_instance = MagicMock()
            mock_loop_instance.run.return_value = mock_agent_result
            MockLoop.return_value = mock_loop_instance

            from hermes_prime.agent.subagent import SubagentManager, SubagentTask

            mgr = SubagentManager(llm_client=mock_llm_client)
            tools = [("web_search", lambda q: "ok", "search tool")]
            task = SubagentTask(id="t1", prompt="search", model="mistral")
            mgr._run_subagent(task, tools=tools)

            mock_loop_instance.register_tool.assert_called_once_with(
                "web_search", tools[0][1], "search tool"
            )
            mgr.shutdown()


class TestSubagentManagerMapReduce:
    def test_map_reduce_spawns_and_reduces(self, mock_llm_client, mock_agent_result):
        with patch(
            "hermes_prime.agent.subagent.SubagentManager._run_subagent",
            return_value=mock_agent_result,
        ) as mock_run:
            from hermes_prime.agent.subagent import SubagentManager

            mgr = SubagentManager(llm_client=mock_llm_client, max_workers=2)
            subtasks = ["task A", "task B"]
            result = mgr.map_reduce(
                subtasks=subtasks,
                reducer_prompt="Combine the results",
                model="llama3",
            )

            assert result is mock_agent_result
            assert mock_run.call_count >= 3
            mgr.shutdown()

    def test_map_reduce_reducer_failure(self, mock_llm_client, mock_agent_result):
        with patch(
            "hermes_prime.agent.subagent.SubagentManager._run_subagent",
        ) as mock_run:
            mock_run.side_effect = [
                mock_agent_result,
                mock_agent_result,
                Exception("reduce failed"),
            ]

            from hermes_prime.agent.subagent import SubagentManager

            mgr = SubagentManager(llm_client=mock_llm_client, max_workers=2)
            with pytest.raises(Exception, match="reduce failed"):
                mgr.map_reduce(
                    subtasks=["a", "b"],
                    reducer_prompt="reduce",
                    model="llama3",
                )
            mgr.shutdown()

    def test_map_reduce_without_model_uses_default(self, mock_llm_client, mock_agent_result):
        with patch(
            "hermes_prime.agent.subagent.SubagentManager._run_subagent",
            return_value=mock_agent_result,
        ):
            from hermes_prime.agent.subagent import SubagentManager

            mgr = SubagentManager(llm_client=mock_llm_client, max_workers=1)
            result = mgr.map_reduce(
                subtasks=["single task"],
                reducer_prompt="reduce",
            )
            assert result is mock_agent_result
            mgr.shutdown()


class TestSubagentManagerGetResult:
    def test_get_result_returns_task(self, mock_llm_client):
        from hermes_prime.agent.subagent import SubagentManager, SubagentTask

        mgr = SubagentManager(llm_client=mock_llm_client)
        task = mgr.spawn(prompt="test")
        mgr._tasks[task.id].status = "completed"
        mgr._tasks[task.id].result = MagicMock()

        result = mgr.get_result(task.id)
        assert result is not None
        assert result.status == "completed"
        mgr.shutdown()

    def test_get_result_returns_none_for_unknown_id(self, mock_llm_client):
        from hermes_prime.agent.subagent import SubagentManager

        mgr = SubagentManager(llm_client=mock_llm_client)
        assert mgr.get_result("nonexistent") is None
        mgr.shutdown()

    @patch("hermes_prime.agent.subagent.AgentLoop")
    def test_get_result_with_timeout_returns_pending_task(self, MockLoop, mock_llm_client):
        import threading
        block = threading.Event()
        MockLoop.return_value.run.side_effect = lambda *a, **kw: block.wait()

        from hermes_prime.agent.subagent import SubagentManager

        mgr = SubagentManager(llm_client=mock_llm_client)
        task = mgr.spawn(prompt="slow task")
        result = mgr.get_result(task.id, timeout=0.05)
        assert result is not None
        assert result.status == "pending"
        block.set()
        mgr.shutdown()

    @patch("hermes_prime.agent.subagent.AgentLoop")
    def test_get_result_blocks_until_completed(self, MockLoop, mock_llm_client):
        from hermes_prime.agent.subagent import SubagentManager
        import threading

        mgr = SubagentManager(llm_client=mock_llm_client)
        task = mgr.spawn(prompt="test")

        def complete_later():
            import time
            time.sleep(0.15)
            mgr._tasks[task.id].status = "completed"
            mgr._tasks[task.id].result = MagicMock()

        t = threading.Thread(target=complete_later, daemon=True)
        t.start()

        result = mgr.get_result(task.id, timeout=2.0)
        assert result is not None
        assert result.status == "completed"
        mgr.shutdown()


class TestSubagentManagerOnComplete:
    def test_on_complete_sets_result_and_status(self, mock_llm_client, mock_agent_result):
        from hermes_prime.agent.subagent import SubagentManager, SubagentTask
        from concurrent.futures import Future

        mgr = SubagentManager(llm_client=mock_llm_client)
        task = SubagentTask(id="t1", prompt="test", model="mistral")
        mgr._tasks["t1"] = task

        future = Future()
        future.set_result(mock_agent_result)
        mgr._on_complete("t1", future)

        assert task.status == "completed"
        assert task.result is mock_agent_result
        mgr.shutdown()

    def test_on_complete_sets_error_on_exception(self, mock_llm_client):
        from hermes_prime.agent.subagent import SubagentManager, SubagentTask
        from concurrent.futures import Future

        mgr = SubagentManager(llm_client=mock_llm_client)
        task = SubagentTask(id="t1", prompt="test", model="mistral")
        mgr._tasks["t1"] = task

        future = Future()
        future.set_exception(ValueError("something went wrong"))
        mgr._on_complete("t1", future)

        assert task.status == "failed"
        assert "something went wrong" in task.error
        mgr.shutdown()

    def test_on_complete_unknown_task_ignored(self, mock_llm_client):
        from hermes_prime.agent.subagent import SubagentManager
        from concurrent.futures import Future

        mgr = SubagentManager(llm_client=mock_llm_client)
        future = Future()
        future.set_result(None)
        mgr._on_complete("unknown", future)
        mgr.shutdown()


class TestSubagentManagerShutdown:
    def test_shutdown_does_not_raise(self, mock_llm_client):
        from hermes_prime.agent.subagent import SubagentManager

        mgr = SubagentManager(llm_client=mock_llm_client)
        mgr.shutdown()

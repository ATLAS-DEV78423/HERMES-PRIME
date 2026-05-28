import pytest
import tempfile
from pathlib import Path


def test_kanban_create():
    from hermes_prime.agent.kanban import KanbanBoard

    with tempfile.TemporaryDirectory() as tmp:
        board = KanbanBoard(Path(tmp) / "kanban.db")
        task = board.create("Write tests", "Add unit tests for the agent")
        assert task["id"] is not None
        assert task["title"] == "Write tests"
        assert task["status"] == "todo"
        board.close()


def test_kanban_transitions():
    from hermes_prime.agent.kanban import KanbanBoard

    with tempfile.TemporaryDirectory() as tmp:
        board = KanbanBoard(Path(tmp) / "kanban.db")
        task = board.create("Implement feature")
        board.transition(task["id"], "in_progress")
        assert board.get(task["id"])["status"] == "in_progress"
        board.transition(task["id"], "done")
        assert board.get(task["id"])["status"] == "done"
        board.close()


def test_kanban_list():
    from hermes_prime.agent.kanban import KanbanBoard

    with tempfile.TemporaryDirectory() as tmp:
        board = KanbanBoard(Path(tmp) / "kanban.db")
        board.create("Task 1")
        board.create("Task 2", status="in_progress")
        board.create("Task 3", status="done")
        todo = board.list_by_status("todo")
        assert len(todo) == 1
        all_tasks = board.list_all()
        assert len(all_tasks) == 3
        board.close()


def test_kanban_assign():
    from hermes_prime.agent.kanban import KanbanBoard

    with tempfile.TemporaryDirectory() as tmp:
        board = KanbanBoard(Path(tmp) / "kanban.db")
        task = board.create("My task")
        board.assign(task["id"], "agent-1")
        assert board.get(task["id"])["assignee"] == "agent-1"
        board.close()

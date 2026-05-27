import pytest


def test_todo_create():
    from hermes_prime.agent.tools.todo import TodoManager

    mgr = TodoManager()
    mgr.create("Write tests", ["unit tests", "integration"], priority="high")
    tasks = mgr.list_all()
    assert len(tasks) == 1
    assert tasks[0]["title"] == "Write tests"


def test_todo_complete():
    from hermes_prime.agent.tools.todo import TodoManager

    mgr = TodoManager()
    mgr.create("Do something")
    tasks = mgr.list_all()
    task_id = tasks[0]["id"]
    mgr.complete(task_id)
    assert mgr.get(task_id)["status"] == "done"


def test_todo_list():
    from hermes_prime.agent.tools.todo import TodoManager

    mgr = TodoManager()
    mgr.create("Task 1", priority="high")
    mgr.create("Task 2", priority="low")
    output = mgr.list_all()
    assert len(output) == 2

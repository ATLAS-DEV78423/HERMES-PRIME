import pytest


def test_code_exec_tool_registered():
    from hermes_prime.agent.tools.code_exec import execute_code, get_code_exec_schema
    assert callable(execute_code)
    schema = get_code_exec_schema()
    assert schema["name"] == "execute_code"
    assert "code" in schema["parameters"]["properties"]


def test_code_exec_python():
    from hermes_prime.agent.tools.code_exec import execute_code
    result = execute_code("print('hello world')", language="python")
    assert "hello world" in result


def test_code_exec_error():
    from hermes_prime.agent.tools.code_exec import execute_code
    result = execute_code("1/0", language="python")
    assert "ZeroDivisionError" in result or "Error" in result

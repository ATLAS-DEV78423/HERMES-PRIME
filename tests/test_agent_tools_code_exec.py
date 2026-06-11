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


def test_code_exec_blocks_os_access():
    from hermes_prime.agent.tools.code_exec import execute_code
    result = execute_code("import os; os.listdir('.')")
    assert "Error" in result or "not allowed" in result or "ModuleNotFoundError" in result


def test_code_exec_blocks_subprocess():
    from hermes_prime.agent.tools.code_exec import execute_code
    result = execute_code("import subprocess; subprocess.run(['echo', 'hi'])")
    assert "Error" in result or "not allowed" in result or "ModuleNotFoundError" in result


def test_code_exec_blocks_file_read():
    from hermes_prime.agent.tools.code_exec import execute_code
    result = execute_code("open('/etc/passwd').read()")
    assert "Error" in result or "not allowed" in result or "NameError" in result


def test_code_exec_blocks_class_escape():
    from hermes_prime.agent.tools.code_exec import execute_code
    result = execute_code("().__class__.__bases__[0].__subclasses__()")
    assert "Error" in result or "not allowed" in result


def test_code_exec_allowed_math():
    from hermes_prime.agent.tools.code_exec import execute_code
    result = execute_code("sum([1, 2, 3, 4, 5])")
    assert "15" in result


def test_code_exec_timeout():
    from hermes_prime.agent.tools.code_exec import execute_code
    result = execute_code("while True: pass")
    assert "Timeout" in result


def test_code_exec_defense_in_depth():
    from hermes_prime.agent.tools.code_exec import execute_code
    result = execute_code("type(())")
    assert "Error" not in result

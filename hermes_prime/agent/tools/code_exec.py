from __future__ import annotations

import ast
import subprocess
import sys
from typing import Any


_SUBPROCESS_TIMEOUT = 10  # seconds

_DANGEROUS_DUNDERS = frozenset({
    "__class__", "__bases__", "__subclasses__", "__globals__", "__code__",
    "__closure__", "__func__", "__self__", "__mro__", "__base__",
    "__builtins__", "__import__",
})


def _check_code_safe(code: str) -> bool:
    """Check if code AST contains dangerous dunder attribute access."""
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in _DANGEROUS_DUNDERS:
                return False
        return True
    except SyntaxError:
        return True

_SANDBOX_BOOTSTRAP = """
import sys
import io
import textwrap

_RESTRICTED_BUILTINS = {{
    "abs": abs, "all": all, "any": any, "ascii": ascii, "bin": bin,
    "bool": bool, "bytearray": bytearray, "bytes": bytes, "callable": callable,
    "chr": chr, "complex": complex, "dict": dict, "divmod": divmod,
    "enumerate": enumerate, "filter": filter, "float": float, "format": format,
    "frozenset": frozenset, "hex": hex, "int": int, "isinstance": isinstance,
    "issubclass": issubclass, "iter": iter, "len": len, "list": list,
    "map": map, "max": max, "min": min, "next": next, "object": object,
    "oct": oct, "ord": ord, "pow": pow, "print": print, "range": range,
    "repr": repr, "reversed": reversed, "round": round, "set": set,
    "slice": slice, "sorted": sorted, "str": str, "sum": sum,
    "tuple": tuple, "type": type, "zip": zip,
    "True": True, "False": False, "None": None,
    "Exception": Exception, "ValueError": ValueError, "TypeError": TypeError,
    "KeyError": KeyError, "IndexError": IndexError, "AttributeError": AttributeError,
    "RuntimeError": RuntimeError, "StopIteration": StopIteration,
    "ZeroDivisionError": ZeroDivisionError, "ArithmeticError": ArithmeticError,
    "LookupError": LookupError, "ImportError": ImportError,
}}

_CODE = {code!r}

def main():
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = stdout_capture
    sys.stderr = stderr_capture
    result_message = ""
    try:
        dedented = textwrap.dedent(_CODE)
        exec_globals = {{"__builtins__": _RESTRICTED_BUILTINS}}
        try:
            result = eval(dedented, exec_globals)
            if result is not None:
                print(result)
        except SyntaxError:
            exec(dedented, exec_globals)
        output = stdout_capture.getvalue()
        error = stderr_capture.getvalue()
        if error:
            output += f"\\nSTDERR:\\n{{error}}"
        result_message = output or "Code executed successfully (no output)."
    except Exception as e:
        result_message = f"Error: {{type(e).__name__}}: {{e}}"
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
    print(result_message)

if __name__ == "__main__":
    main()
"""


def execute_code(code: str, language: str = "python") -> str:
    """Execute Python code in a subprocess-based sandbox.

    The code runs in a separate Python process with restricted builtins.
    The subprocess is killed after _SUBPROCESS_TIMEOUT seconds.
    """
    if language != "python":
        return f"Language '{language}' not supported yet."

    if not _check_code_safe(code):
        return "Error: Blocked by pre-execution safety scan (defense-in-depth)."

    bootstrap_script = _SANDBOX_BOOTSTRAP.format(code=code)

    try:
        proc = subprocess.run(
            [sys.executable, "-c", bootstrap_script],
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT,
        )
        output = proc.stdout.strip()
        if proc.stderr:
            output += f"\nSTDERR:\n{proc.stderr.strip()}"
        return output or "Code executed successfully (no output)."
    except subprocess.TimeoutExpired:
        return f"Error: TimeoutError: execution exceeded {_SUBPROCESS_TIMEOUT}s"
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"


def get_code_exec_schema() -> dict[str, Any]:
    return {
        "name": "execute_code",
        "description": "Execute Python code in a sandboxed environment",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Code to execute"},
                "language": {
                    "type": "string",
                    "description": "Language (default: python)",
                    "default": "python",
                },
            },
            "required": ["code"],
        },
    }


__all__ = ["execute_code", "get_code_exec_schema"]

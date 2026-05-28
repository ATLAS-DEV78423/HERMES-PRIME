from __future__ import annotations

import sys
import io
import textwrap
from typing import Any


def execute_code(code: str, language: str = "python") -> str:
    """Execute code in a sandboxed environment."""
    if language != "python":
        return f"Language '{language}' not supported yet."

    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = stdout_capture
    sys.stderr = stderr_capture

    try:
        dedented = textwrap.dedent(code)
        exec_globals = {"__builtins__": __builtins__}
        exec(dedented, exec_globals)
        output = stdout_capture.getvalue()
        error = stderr_capture.getvalue()
        if error:
            output += f"\nSTDERR:\n{error}"
        return output or "Code executed successfully (no output)."
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr


def get_code_exec_schema() -> dict[str, Any]:
    return {
        "name": "execute_code",
        "description": "Execute Python code in a sandboxed environment",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Code to execute"},
                "language": {"type": "string", "description": "Language (default: python)", "default": "python"},
            },
            "required": ["code"],
        },
    }


__all__ = ["execute_code", "get_code_exec_schema"]

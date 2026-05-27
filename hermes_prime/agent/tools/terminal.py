from __future__ import annotations

import subprocess
import shlex
import os
from typing import Any


def terminal_execute(command: str, timeout: int = 60, workdir: str | None = None) -> str:
    """Execute a shell command and return output."""
    allowed_commands = [
        "ls", "cat", "head", "tail", "echo", "pwd", "cd", "mkdir",
        "cp", "mv", "rm", "grep", "find", "sort", "wc", "diff",
        "python", "node", "npm", "pip", "git", "make", "curl",
        "wget", "tar", "gzip", "unzip", "chmod", "whoami",
    ]

    parts = shlex.split(command)
    if parts and parts[0] not in allowed_commands:
        return f"Command '{parts[0]}' not in allowed list. Contact administrator."

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workdir or os.getcwd(),
        )
        output = result.stdout
        if result.stderr:
            output += f"\nSTDERR:\n{result.stderr[:2000]}"
        if result.returncode != 0:
            output += f"\nExit code: {result.returncode}"
        return output[:10000]
    except subprocess.TimeoutExpired:
        return f"Command timed out after {timeout}s"
    except Exception as e:
        return f"Execution error: {e}"


def get_terminal_schema() -> dict[str, Any]:
    return {
        "name": "terminal",
        "description": "Execute a shell command with output",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default 60)", "default": 60},
            },
            "required": ["command"],
        },
    }


__all__ = ["terminal_execute", "get_terminal_schema"]

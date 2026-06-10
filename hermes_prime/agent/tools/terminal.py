from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from typing import Any

WINDOWS_SHELL_BUILTINS = {"echo", "dir", "type", "copy", "move", "del", "rmdir", "cd", "set", "path", "cls", "date", "time", "ver"}


def _find_command(name: str) -> str | None:
    """Resolve a command name to a full path, trying known Windows exe variants."""
    resolved = shutil.which(name)
    if resolved:
        return resolved
    if sys.platform == "win32":
        for ext in [".exe", ".cmd", ".bat", ".ps1"]:
            resolved = shutil.which(name + ext)
            if resolved:
                return resolved
    return None


def terminal_execute(command: str, timeout: int = 60, workdir: str | None = None) -> str:
    """Execute a shell command and return output."""
    allowed_commands = [
        "echo", "mkdir", "sort", "wc", "diff",
        "python", "node", "npm", "pip", "git", "curl",
        "unzip",
    ]
    if sys.platform != "win32":
        allowed_commands.extend([
            "ls", "cat", "head", "tail", "pwd", "cp", "mv", "rm",
            "grep", "find", "make", "wget", "tar", "gzip", "chmod", "whoami",
        ])
    else:
        allowed_commands.extend([
            "dir", "type", "findstr", "where", "copy", "move", "del",
            "mkdir", "rmdir", "whoami",
        ])

    parts = shlex.split(command)
    if parts and parts[0] not in allowed_commands:
        return f"Command '{parts[0]}' not in allowed list. Contact administrator."

    cmd_path = _find_command(parts[0]) if parts else None
    is_builtin = sys.platform == "win32" and parts and parts[0] in WINDOWS_SHELL_BUILTINS
    if parts and not cmd_path and not is_builtin:
        return f"Command '{parts[0]}' not found on system PATH."

    use_shell = sys.platform == "win32" and is_builtin
    try:
        result = subprocess.run(
            command if use_shell else ([cmd_path or parts[0]] + parts[1:]),
            shell=use_shell,
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

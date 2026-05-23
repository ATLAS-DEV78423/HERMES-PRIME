"""
Sandbox enforcement for subagent execution.

This is a *reference* implementation. Production deployments should use
OS-level sandboxing (seccomp, landlock, containers, etc.) for real isolation.
The Python-level checks here defend against well-meaning bugs but not
against motivated attackers.
"""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path

from refrlow.protocol import Scope


class ScopeViolation(Exception):
    """Raised when a subagent attempts to access a path outside its scope."""

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"Scope violation: {path} ({reason})")
        self.path = path
        self.reason = reason


def normalize_and_validate_path(scope: Scope, candidate: str) -> Path:
    """
    Normalize a candidate path and verify it is inside the scope.

    Defeats:
      - Relative path traversal (../../etc/passwd)
      - Symlink escapes (best-effort; not bulletproof without OS sandboxing)
      - Excluded glob matches
    """
    root = Path(scope.root).resolve()
    if not root.exists():
        raise ScopeViolation(scope.root, "scope root does not exist")

    # Resolve the candidate relative to the root, following any '..' components.
    abs_path = (root / candidate).resolve() if not os.path.isabs(candidate) else Path(candidate).resolve()

    # Containment check: abs_path must be at or below root.
    try:
        abs_path.relative_to(root)
    except ValueError:
        raise ScopeViolation(str(abs_path), "outside workspace root")

    rel = str(abs_path.relative_to(root))

    # Exclude-glob check.
    for pattern in scope.exclude_globs:
        if fnmatch.fnmatch(rel, pattern):
            raise ScopeViolation(rel, f"matches exclude pattern '{pattern}'")

    # Include-glob check (any-match).
    if scope.include_globs:
        included = any(
            fnmatch.fnmatch(rel, pattern) for pattern in scope.include_globs
        )
        if not included:
            raise ScopeViolation(rel, "does not match any include pattern")

    return abs_path


def iter_scoped_files(scope: Scope, recurse: bool = True) -> list[Path]:
    """
    Yield all files within scope that satisfy include/exclude globs.

    For deterministic subagents (file_miner, grep_miner) to walk only
    legal paths.
    """
    root = Path(scope.root).resolve()
    results: list[Path] = []

    if recurse:
        walker = root.rglob("*")
    else:
        walker = root.glob("*")

    for path in walker:
        if not path.is_file():
            continue
        try:
            normalize_and_validate_path(scope, str(path.relative_to(root)))
        except ScopeViolation:
            continue
        results.append(path)

    return results


# --- Process-level sandboxing hooks (reference stubs) ---
#
# Production deployments should wire these into seccomp/landlock/jail/etc.
# For the reference implementation, they are no-ops with clear contracts.


def enter_subagent_sandbox(scope: Scope, allow_network: bool = False) -> None:
    """
    Apply OS-level restrictions to the current process before subagent runs.

    Stub. Production implementations should:
      - Drop privileges to an unprivileged user.
      - Restrict filesystem access via landlock or container mounts.
      - Block network unless allow_network is True.
      - Apply seccomp filter to limit syscalls.
      - Set ulimits on CPU time, memory, and file descriptors.

    For now this is a no-op that documents the contract.
    """
    # Production: install seccomp filter, configure landlock, etc.
    _ = scope, allow_network
    return

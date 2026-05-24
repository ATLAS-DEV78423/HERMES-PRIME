from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import re
import urllib.parse
import uuid
from pathlib import Path
from typing import Any


UUID_URN_RE = re.compile(
    r"^urn:uuid:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

SHELL_META_RE = re.compile(r"[;&|`]")
NULL_BYTE_RE = re.compile(r"\x00")


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def new_urn_uuid() -> str:
    return f"urn:uuid:{uuid.uuid4()}"


def parse_iso8601(value: str) -> dt.datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def is_urn_uuid(value: str) -> bool:
    return bool(UUID_URN_RE.match(value))


def canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def hash_struct(data: Any) -> str:
    return sha256_text(canonical_json(normalize_for_json(data)))


def normalize_for_json(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return normalize_for_json(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {str(k): normalize_for_json(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [normalize_for_json(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, set):
        return [normalize_for_json(v) for v in sorted(value, key=repr)]
    return value


def contains_shell_meta(value: str) -> bool:
    return bool(SHELL_META_RE.search(value))


def contains_null_byte(value: str) -> bool:
    return bool(NULL_BYTE_RE.search(value))


def decode_percent(value: str) -> str:
    return urllib.parse.unquote(value)


def scope_prefix(scope: str) -> str:
    scope = decode_percent(scope)
    wildcard_index = len(scope)
    for token in ("*", "?", "["):
        idx = scope.find(token)
        if idx != -1:
            wildcard_index = min(wildcard_index, idx)
    prefix = scope[:wildcard_index]
    return prefix.rstrip("/\\")


def path_within_scope(path: str, scope: str) -> bool:
    normalized_path = Path(path).resolve()
    prefix = scope_prefix(scope)
    if not prefix:
        return False
    if any(ch in prefix for ch in ("*", "?", "[")):
        return False
    normalized_scope = Path(prefix).resolve()
    try:
        normalized_path.relative_to(normalized_scope)
        return True
    except ValueError:
        return False


def relative_to_root(path: str, root: str) -> str:
    return str(Path(path).resolve().relative_to(Path(root).resolve()))


def path_subscope(child_scope: str, parent_scope: str) -> bool:
    child = Path(scope_prefix(child_scope)).resolve()
    parent = Path(scope_prefix(parent_scope)).resolve()
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def read_text_safe(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")

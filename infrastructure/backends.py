from __future__ import annotations

import importlib.util
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BackendStatus:
    name: str
    available: bool
    source: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "available": self.available,
            "source": self.source,
            "details": dict(self.details),
        }


class BackendRegistry:
    def __init__(self, workspace_root: str | Path) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.external_root = self.workspace_root / "external"

    def detect(self) -> dict[str, BackendStatus]:
        return {
            "opa": self._detect_opa(),
            "tree_sitter": self._detect_tree_sitter(),
            "file_miner": BackendStatus(
                name="file_miner",
                available=True,
                source="python+rg",
                details={
                    "ripgrep": shutil.which("rg") is not None,
                    "fallback": "python_regex",
                },
            ),
        }

    def manifest(self) -> dict[str, Any]:
        backends = self.detect()
        return {
            "workspace_root": str(self.workspace_root),
            "backends": {name: status.to_dict() for name, status in backends.items()},
            "preferred": self.preferred_backend(backends),
        }

    def readiness(self) -> dict[str, Any]:
        manifest = self.manifest()
        backends = manifest["backends"]
        critical_missing = []
        if not backends["tree_sitter"]["available"]:
            critical_missing.append("tree_sitter")
        if not backends["opa"]["available"] and not backends["opa"]["details"]["can_use_wasm"]:
            critical_missing.append("opa")
        ready = len(critical_missing) == 0
        return {
            "ready": ready,
            "critical_missing": critical_missing,
            "manifest": manifest,
            "notes": [
                "OPA can be satisfied by a binary or by a compiled wasm bundle with a runtime.",
                "tree-sitter is considered ready when the runtime and at least one grammar package are present.",
            ],
        }

    def preferred_backend(self, backends: dict[str, BackendStatus] | None = None) -> str:
        backends = backends or self.detect()
        if backends["opa"].available:
            return "opa"
        if backends["tree_sitter"].available:
            return "tree_sitter"
        return "fallback"

    def opa_executable(self) -> Path | None:
        env_binary = os.environ.get("HERMES_PRIME_OPA_BINARY")
        candidates = []
        if env_binary:
            candidates.append(Path(env_binary))
        candidates.extend(
            [
                self.workspace_root / ".hermes-prime" / "bin" / "opa.exe",
                self.workspace_root / ".hermes-prime" / "bin" / "opa",
                self.workspace_root / "bin" / "opa.exe",
                self.workspace_root / "bin" / "opa",
            ]
        )
        which_binary = shutil.which("opa")
        if which_binary:
            candidates.append(Path(which_binary))
        for candidate in candidates:
            if candidate.exists():
                return candidate.resolve()
        return None

    def _detect_opa(self) -> BackendStatus:
        binary_path = self.opa_executable()
        source_tree = self.external_root / "opa"
        engine_wasm = source_tree / "internal" / "compiler" / "wasm" / "opa" / "opa.wasm"
        compiled_bundle = self._locate_compiled_opa_bundle()
        has_runtime = self._module_usable("wasmtime") or self._module_usable("wasmer")
        available = binary_path is not None or (compiled_bundle is not None and has_runtime)
        return BackendStatus(
            name="opa",
            available=available,
            source="binary" if binary_path else ("wasm" if available else "source_tree"),
            details={
                "binary": str(binary_path) if binary_path else "",
                "source_tree_present": source_tree.exists(),
                "engine_wasm_present": engine_wasm.exists(),
                "wasm_runtime_present": has_runtime,
                "compiled_policy_bundle_present": compiled_bundle is not None,
                "compiled_policy_bundle": compiled_bundle or "",
                "can_use_wasm": compiled_bundle is not None and has_runtime,
            },
        )

    def _detect_tree_sitter(self) -> BackendStatus:
        runtime_present = self._module_usable("tree_sitter")
        grammar_packages = [
            name
            for name in (
                "tree_sitter_python",
                "tree_sitter_javascript",
                "tree_sitter_typescript",
                "tree_sitter_tsx",
            )
            if self._module_usable(name)
        ]
        source_tree = self.external_root / "tree-sitter"
        available = runtime_present and bool(grammar_packages)
        return BackendStatus(
            name="tree_sitter",
            available=available,
            source="packages" if available else "source_tree",
            details={
                "runtime_present": runtime_present,
                "grammar_packages": grammar_packages,
                "source_tree_present": source_tree.exists(),
                "can_use_source_tree": source_tree.exists()
                and runtime_present
                and bool(grammar_packages),
            },
        )

    def _module_usable(self, name: str) -> bool:
        if importlib.util.find_spec(name) is None:
            return False
        try:
            __import__(name)
            return True
        except Exception:
            return False

    def _locate_compiled_opa_bundle(self) -> str | None:
        env_bundle = os.environ.get("HERMES_PRIME_OPA_WASM_BUNDLE")
        candidates = []
        if env_bundle:
            candidates.append(Path(env_bundle))
        candidates.extend(
            [
                self.workspace_root / ".hermes-prime" / "opa-policy.wasm",
                self.workspace_root / ".hermes-prime" / "policy.wasm",
                self.workspace_root
                / "infrastructure"
                / "policy_engine"
                / "compiled"
                / "policy.wasm",
                self.workspace_root / "infrastructure" / "policy_engine" / "policy.wasm",
            ]
        )
        for candidate in candidates:
            if candidate.exists():
                return str(candidate.resolve())
        return None

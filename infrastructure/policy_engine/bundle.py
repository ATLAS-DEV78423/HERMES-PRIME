from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from infrastructure.backends import BackendRegistry


@dataclass(frozen=True)
class PolicyArtifact:
    kind: str
    name: str
    path: str
    sha256: str
    size_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "path": self.path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


class PolicyBundle:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.policy_root = self.root / "policies"
        self.schema_root = self.root / "schemas"

    def available(self) -> bool:
        return self.policy_root.exists() and self.schema_root.exists()

    def opa_available(self) -> bool:
        return BackendRegistry(self.root.parent.parent).opa_executable() is not None

    def artifacts(self) -> list[PolicyArtifact]:
        artifacts: list[PolicyArtifact] = []
        for base, kind in ((self.policy_root, "rego"), (self.schema_root, "schema")):
            if not base.exists():
                continue
            for path in sorted(base.glob("*")):
                if not path.is_file():
                    continue
                data = path.read_bytes()
                artifacts.append(
                    PolicyArtifact(
                        kind=kind,
                        name=path.name,
                        path=str(path),
                        sha256="sha256:" + hashlib.sha256(data).hexdigest(),
                        size_bytes=len(data),
                    )
                )
        return artifacts

    def manifest(self) -> dict[str, Any]:
        backend_manifest = BackendRegistry(self.root.parent.parent).manifest()
        return {
            "bundle_root": str(self.root),
            "available": self.available(),
            "opa_available": self.opa_available(),
            "artifacts": [artifact.to_dict() for artifact in self.artifacts()],
            "backends": backend_manifest,
        }

    def readiness(self) -> dict[str, Any]:
        backend_readiness = BackendRegistry(self.root.parent.parent).readiness()
        ready = self.available() and backend_readiness["ready"]
        return {
            "ready": ready,
            "bundle": self.manifest(),
            "backend_readiness": backend_readiness,
        }

    def to_json(self) -> str:
        return json.dumps(self.manifest(), indent=2, sort_keys=True)

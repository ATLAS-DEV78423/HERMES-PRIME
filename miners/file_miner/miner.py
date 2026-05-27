from __future__ import annotations

import fnmatch
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

from hermes_prime.contracts import ExaminedFile, MinerAttestation
from hermes_prime.secrets import get_signer
from hermes_prime.signing import HMACSigner
from hermes_prime.utils import hash_struct, new_urn_uuid, read_text_safe, utc_now_iso
from infrastructure.trust_store import TrustStore


@dataclass
class FileMinerBudget:
    max_results: int = 50
    max_lines: int = 500
    max_bytes_per_result: int = 4096
    timeout_seconds: int = 10


class FileMiner:
    def __init__(
        self,
        workspace_root: str | Path,
        signer: Optional[HMACSigner] = None,
        trust_store: Optional[TrustStore] = None,
        miner_id: str = "fm-001",
        miner_version: str = "0.1.0",
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.signer = signer or get_signer("miner")
        self.trust_store = trust_store
        self.miner_id = miner_id
        self.miner_version = miner_version

    def find_by_glob(self, pattern: str, budget: FileMinerBudget | None = None) -> MinerAttestation:
        budget = budget or FileMinerBudget()
        start = time.monotonic()
        matches: list[dict[str, Any]] = []
        examined: list[ExaminedFile] = []
        for path in self._walk_files():
            if time.monotonic() - start > budget.timeout_seconds:
                break
            rel = str(path.relative_to(self.workspace_root))
            if fnmatch.fnmatch(rel, pattern):
                examined.append(self._file_record(path))
                matches.append(
                    {
                        "file": rel,
                        "line": None,
                        "relevance": 1.0,
                        "match": rel,
                    }
                )
            if len(matches) >= budget.max_results:
                break
        return self._attest("find_by_glob", examined, matches, start)

    def find_by_extension(
        self, ext: str, budget: FileMinerBudget | None = None
    ) -> MinerAttestation:
        if not ext.startswith("."):
            ext = "." + ext
        return self.find_by_glob(f"**/*{ext}", budget)

    def find_large(self, min_bytes: int, budget: FileMinerBudget | None = None) -> MinerAttestation:
        budget = budget or FileMinerBudget()
        start = time.monotonic()
        matches: list[dict[str, Any]] = []
        examined: list[ExaminedFile] = []
        for path in self._walk_files():
            if time.monotonic() - start > budget.timeout_seconds:
                break
            try:
                stat = path.stat()
            except OSError:
                continue
            if stat.st_size >= min_bytes:
                examined.append(self._file_record(path))
                matches.append(
                    {
                        "file": str(path.relative_to(self.workspace_root)),
                        "line": None,
                        "relevance": min(1.0, stat.st_size / max(min_bytes, 1)),
                        "match": f"size_bytes={stat.st_size}",
                    }
                )
            if len(matches) >= budget.max_results:
                break
        return self._attest("find_large", examined, matches, start)

    def search_text(
        self,
        pattern: str,
        scope: str | None = None,
        budget: FileMinerBudget | None = None,
    ) -> MinerAttestation:
        budget = budget or FileMinerBudget()
        start = time.monotonic()
        matches: list[dict[str, Any]] = []
        examined: list[ExaminedFile] = []
        root = Path(scope).resolve() if scope else self.workspace_root
        rg = shutil.which("rg")
        if rg:
            matches, examined = self._rg_search(root, pattern, budget, start)
        else:
            matches, examined = self._python_search(root, pattern, budget, start)
        return self._attest("search_text", examined, matches, start)

    def enumerate_tree(self, max_depth: int = 3) -> MinerAttestation:
        start = time.monotonic()
        tree: dict[str, Any] = {}
        examined = [self._file_record(self.workspace_root)]

        def walk(path: Path, depth: int, container: dict[str, Any]) -> None:
            if depth > max_depth:
                return
            for child in sorted(path.iterdir(), key=lambda p: p.name):
                if child.name == ".git":
                    continue
                if child.is_dir():
                    container[child.name + "/"] = {}
                    walk(child, depth + 1, container[child.name + "/"])
                else:
                    container[child.name] = None

        walk(self.workspace_root, 0, tree)
        return self._attest("enumerate_tree", examined, [{"tree": tree}], start)

    def _walk_files(self) -> Iterable[Path]:
        for path in self.workspace_root.rglob("*"):
            if path.is_file() and ".git" not in path.parts:
                yield path

    def _file_record(self, path: Path) -> ExaminedFile:
        data = path.read_bytes()
        return ExaminedFile(
            path=str(path.resolve()),
            hash="sha256:" + __import__("hashlib").sha256(data).hexdigest(),
            size_bytes=len(data),
        )

    def _rg_search(
        self,
        root: Path,
        pattern: str,
        budget: FileMinerBudget,
        start: float,
    ) -> tuple[list[dict[str, Any]], list[ExaminedFile]]:
        proc = subprocess.run(
            ["rg", "-n", "--no-heading", pattern, str(root)],
            capture_output=True,
            text=True,
            timeout=budget.timeout_seconds,
            check=False,
        )
        results: list[dict[str, Any]] = []
        examined: list[ExaminedFile] = []
        for line in proc.stdout.splitlines()[: budget.max_lines]:
            parts = line.rsplit(":", 2)
            if len(parts) < 3:
                continue
            file_path, line_no, match = parts[0], parts[1], parts[2]
            file = Path(file_path).resolve()
            if file.exists():
                examined.append(self._file_record(file))
            results.append(
                {
                    "file": str(file.relative_to(root.resolve())),
                    "line": int(line_no),
                    "relevance": 1.0,
                    "match": match[: budget.max_bytes_per_result],
                }
            )
            if len(results) >= budget.max_results:
                break
        return results, examined

    def _python_search(
        self,
        root: Path,
        pattern: str,
        budget: FileMinerBudget,
        start: float,
    ) -> tuple[list[dict[str, Any]], list[ExaminedFile]]:
        regex = re.compile(pattern)
        results: list[dict[str, Any]] = []
        examined: list[ExaminedFile] = []
        for path in root.rglob("*"):
            if not path.is_file() or ".git" in path.parts:
                continue
            try:
                text = read_text_safe(path)
            except OSError:
                continue
            matched = False
            for idx, line in enumerate(text.splitlines(), start=1):
                if regex.search(line):
                    examined.append(self._file_record(path))
                    results.append(
                        {
                            "file": str(path.relative_to(root)),
                            "line": idx,
                            "relevance": 1.0,
                            "match": line[: budget.max_bytes_per_result],
                        }
                    )
                    matched = True
                if len(results) >= budget.max_results or idx >= budget.max_lines:
                    break
            if matched and len(results) >= budget.max_results:
                break
        return results, examined

    def _attest(
        self,
        task: str,
        examined: list[ExaminedFile],
        results: list[dict[str, Any]],
        start: float,
    ) -> MinerAttestation:
        duration_ms = int((time.monotonic() - start) * 1000)
        payload = {
            "miner_id": self.miner_id,
            "task": task,
            "results": results,
            "files_examined": [record.to_dict() for record in examined],
            "duration_ms": duration_ms,
        }
        signature = self.signer.sign_json(payload)
        attestation = MinerAttestation(
            attestation_id=new_urn_uuid(),
            miner_id=self.miner_id,
            miner_type="file_miner",
            miner_version=self.miner_version,
            scan_scope=str(self.workspace_root),
            scan_time=utc_now_iso(),
            duration_ms=duration_ms,
            files_examined=examined,
            results=results,
            confidence=0.98 if results else 1.0,
            content_summary_hash=hash_struct(results),
            signature=signature,
        )
        if self.trust_store is not None:
            self.trust_store.store_miner_attestation(attestation)
        return attestation

from __future__ import annotations

import ast
import importlib.util
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from hermes_prime.contracts import ExaminedFile, MinerAttestation
from hermes_prime.signing import HMACSigner
from hermes_prime.utils import hash_struct, new_urn_uuid, read_text_safe, utc_now_iso
from infrastructure.backends import BackendRegistry
from infrastructure.trust_store import TrustStore


@dataclass
class AstMinerBudget:
    max_files: int = 50
    timeout_seconds: int = 20


class AstMiner:
    def __init__(
        self,
        workspace_root: str | Path,
        signer: Optional[HMACSigner] = None,
        trust_store: Optional[TrustStore] = None,
        miner_id: str = "am-001",
        miner_version: str = "0.1.0",
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.signer = signer or HMACSigner(
            identity="miner:ast", secret=b"hermes-prime-ast-secret"
        )
        self.trust_store = trust_store
        self.miner_id = miner_id
        self.miner_version = miner_version
        self.backend_registry = BackendRegistry(self.workspace_root)
        self._tree_sitter_backend = self._load_tree_sitter_backend()
        if self._tree_sitter_backend is not None:
            self.parser_backend = f"tree-sitter:{','.join(sorted(self._tree_sitter_backend['languages']))}"
        else:
            self.parser_backend = "python_ast_fallback"

    def extract_symbols(self, scope: str | None = None, budget: AstMinerBudget | None = None) -> MinerAttestation:
        budget = budget or AstMinerBudget()
        start = time.monotonic()
        root = Path(scope).resolve() if scope else self.workspace_root
        results: list[dict[str, Any]] = []
        examined: list[ExaminedFile] = []
        for path in self._walk_files(root):
            if time.monotonic() - start > budget.timeout_seconds:
                break
            symbols = self._symbols_for_file(path)
            if symbols:
                examined.append(self._file_record(path))
                results.extend(symbols)
            if len(examined) >= budget.max_files:
                break
        return self._attest("extract_symbols", root, examined, results, start)

    def trace_imports(self, scope: str | None = None, budget: AstMinerBudget | None = None) -> MinerAttestation:
        budget = budget or AstMinerBudget()
        start = time.monotonic()
        root = Path(scope).resolve() if scope else self.workspace_root
        results: list[dict[str, Any]] = []
        examined: list[ExaminedFile] = []
        for path in self._walk_files(root):
            if time.monotonic() - start > budget.timeout_seconds:
                break
            imports = self._imports_for_file(path)
            if imports:
                examined.append(self._file_record(path))
                results.extend(imports)
            if len(examined) >= budget.max_files:
                break
        return self._attest("trace_imports", root, examined, results, start)

    def index_api_surface(self, scope: str | None = None) -> MinerAttestation:
        start = time.monotonic()
        root = Path(scope).resolve() if scope else self.workspace_root
        results = []
        examined: list[ExaminedFile] = []
        for path in self._walk_files(root):
            api = self._public_surface_for_file(path)
            if api:
                examined.append(self._file_record(path))
                results.extend(api)
        return self._attest("index_api_surface", root, examined, results, start)

    def _walk_files(self, root: Path):
        for path in root.rglob("*"):
            if path.is_file() and ".git" not in path.parts:
                yield path

    def _file_record(self, path: Path) -> ExaminedFile:
        data = path.read_bytes()
        return ExaminedFile(
            path=str(path.resolve()),
            hash="sha256:" + __import__("hashlib").sha256(data).hexdigest(),
            size_bytes=len(data),
        )

    def _symbols_for_file(self, path: Path) -> list[dict[str, Any]]:
        if self._tree_sitter_backend is not None:
            tree_sitter_symbols = self._tree_sitter_symbols(path)
            if tree_sitter_symbols:
                return tree_sitter_symbols
        if path.suffix == ".py":
            return self._python_symbols(path)
        return self._text_symbols(path)

    def _imports_for_file(self, path: Path) -> list[dict[str, Any]]:
        if self._tree_sitter_backend is not None:
            tree_sitter_imports = self._tree_sitter_imports(path)
            if tree_sitter_imports:
                return tree_sitter_imports
        if path.suffix == ".py":
            return self._python_imports(path)
        return self._text_imports(path)

    def _public_surface_for_file(self, path: Path) -> list[dict[str, Any]]:
        symbols = self._symbols_for_file(path)
        return [item for item in symbols if item.get("visibility") == "public"]

    def _python_symbols(self, path: Path) -> list[dict[str, Any]]:
        try:
            tree = ast.parse(read_text_safe(path))
        except SyntaxError:
            return []
        results: list[dict[str, Any]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                results.append(
                    {
                        "file": str(path.relative_to(self.workspace_root)),
                        "symbol": node.name,
                        "kind": "function",
                        "line": node.lineno,
                        "visibility": "public" if not node.name.startswith("_") else "private",
                    }
                )
            elif isinstance(node, ast.ClassDef):
                results.append(
                    {
                        "file": str(path.relative_to(self.workspace_root)),
                        "symbol": node.name,
                        "kind": "class",
                        "line": node.lineno,
                        "visibility": "public" if not node.name.startswith("_") else "private",
                    }
                )
        return results

    def _python_imports(self, path: Path) -> list[dict[str, Any]]:
        try:
            tree = ast.parse(read_text_safe(path))
        except SyntaxError:
            return []
        results: list[dict[str, Any]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    results.append(
                        {
                            "file": str(path.relative_to(self.workspace_root)),
                            "from": None,
                            "import": alias.name,
                            "line": node.lineno,
                        }
                    )
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for alias in node.names:
                    results.append(
                        {
                            "file": str(path.relative_to(self.workspace_root)),
                            "from": mod,
                            "import": alias.name,
                            "line": node.lineno,
                        }
                    )
        return results

    def _text_symbols(self, path: Path) -> list[dict[str, Any]]:
        text = read_text_safe(path)
        results: list[dict[str, Any]] = []
        patterns = [
            (re.compile(r"^\s*export\s+class\s+([A-Za-z_][A-Za-z0-9_]*)", re.M), "class"),
            (re.compile(r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)", re.M), "class"),
            (re.compile(r"^\s*export\s+function\s+([A-Za-z_][A-Za-z0-9_]*)", re.M), "function"),
            (re.compile(r"^\s*function\s+([A-Za-z_][A-Za-z0-9_]*)", re.M), "function"),
            (re.compile(r"^\s*export\s+(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)", re.M), "variable"),
        ]
        for regex, kind in patterns:
            for match in regex.finditer(text):
                results.append(
                    {
                        "file": str(path.relative_to(self.workspace_root)),
                        "symbol": match.group(1),
                        "kind": kind,
                        "line": text[: match.start()].count("\n") + 1,
                        "visibility": "public" if "export" in match.group(0) else "private",
                    }
                )
        return results

    def _text_imports(self, path: Path) -> list[dict[str, Any]]:
        text = read_text_safe(path)
        results: list[dict[str, Any]] = []
        for regex in (
            re.compile(r"^\s*import\s+.*?from\s+['\"]([^'\"]+)['\"]", re.M),
            re.compile(r"require\(['\"]([^'\"]+)['\"]\)"),
        ):
            for match in regex.finditer(text):
                results.append(
                    {
                        "file": str(path.relative_to(self.workspace_root)),
                        "from": match.group(1),
                        "import": None,
                        "line": text[: match.start()].count("\n") + 1,
                    }
                )
        return results

    def _load_tree_sitter_backend(self) -> dict[str, Any] | None:
        if importlib.util.find_spec("tree_sitter") is None:
            return None
        try:
            from tree_sitter import Language, Parser  # type: ignore
            import tree_sitter_javascript as tsjavascript  # type: ignore
            import tree_sitter_python as tspython  # type: ignore
            import tree_sitter_typescript as tstypescript  # type: ignore
        except Exception:
            return None

        parser_factories = {
            "python": lambda: Language(tspython.language()),
            "javascript": lambda: Language(tsjavascript.language()),
            "typescript": lambda: Language(tstypescript.language_typescript()),
            "tsx": lambda: Language(tstypescript.language_tsx()),
        }

        parsers: dict[str, Any] = {}
        for lang_name, factory in parser_factories.items():
            try:
                language = factory()
                parser = Parser()
                try:
                    parser.language = language
                except AttributeError:
                    parser.set_language(language)
                parsers[lang_name] = parser
            except Exception:
                continue
        if not parsers:
            return None
        return {"languages": parsers}

    def _tree_sitter_parser_for_path(self, path: Path) -> Any | None:
        if self._tree_sitter_backend is None:
            return None
        language_names = {
            ".py": ["python"],
            ".js": ["javascript"],
            ".jsx": ["javascript"],
            ".ts": ["typescript", "tsx"],
            ".tsx": ["tsx", "typescript"],
            ".mjs": ["javascript"],
            ".cjs": ["javascript"],
        }.get(path.suffix.lower(), [])
        for lang_name in language_names:
            parser = self._tree_sitter_backend["languages"].get(lang_name)
            if parser is not None:
                return parser
        return None

    def _tree_sitter_symbols(self, path: Path) -> list[dict[str, Any]]:
        parser = self._tree_sitter_parser_for_path(path)
        if parser is None:
            return []
        source = read_text_safe(path)
        tree = parser.parse(source.encode("utf-8"))
        results: list[dict[str, Any]] = []
        suffix = path.suffix.lower()
        if suffix == ".py":
            results.extend(self._tree_sitter_python_symbols(path, source, tree.root_node))
        else:
            results.extend(self._tree_sitter_js_symbols(path, source, tree.root_node))
        return results

    def _tree_sitter_imports(self, path: Path) -> list[dict[str, Any]]:
        parser = self._tree_sitter_parser_for_path(path)
        if parser is None:
            return []
        source = read_text_safe(path)
        tree = parser.parse(source.encode("utf-8"))
        results: list[dict[str, Any]] = []
        if path.suffix.lower() == ".py":
            results.extend(self._tree_sitter_python_imports(path, source, tree.root_node))
        else:
            results.extend(self._tree_sitter_js_imports(path, source, tree.root_node))
        return results

    def _iter_tree_nodes(self, node: Any):
        yield node
        for child in getattr(node, "children", []) or []:
            yield from self._iter_tree_nodes(child)

    def _tree_sitter_python_symbols(self, path: Path, source: str, root: Any) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for node in self._iter_tree_nodes(root):
            if node.type not in {"function_definition", "async_function_definition", "class_definition"}:
                continue
            name_node = node.child_by_field_name("name")
            if name_node is None:
                continue
            name = source[name_node.start_byte : name_node.end_byte].strip()
            if not name:
                continue
            results.append(
                {
                    "file": str(path.relative_to(self.workspace_root)),
                    "symbol": name,
                    "kind": "class" if node.type == "class_definition" else "function",
                    "line": node.start_point[0] + 1,
                    "visibility": "public" if not name.startswith("_") else "private",
                    "parser_backend": "tree-sitter",
                }
            )
        return results

    def _tree_sitter_python_imports(self, path: Path, source: str, root: Any) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for node in self._iter_tree_nodes(root):
            if node.type == "import_statement":
                for child in getattr(node, "named_children", []) or []:
                    if child.type != "dotted_name":
                        continue
                    module = source[child.start_byte : child.end_byte].strip()
                    if module:
                        results.append(
                            {
                                "file": str(path.relative_to(self.workspace_root)),
                                "from": None,
                                "import": module,
                                "line": node.start_point[0] + 1,
                                "parser_backend": "tree-sitter",
                            }
                        )
            elif node.type == "import_from_statement":
                module_node = node.child_by_field_name("module")
                if module_node is None:
                    continue
                module = source[module_node.start_byte : module_node.end_byte].strip()
                names = []
                for child in getattr(node, "named_children", []) or []:
                    if child.type in {"dotted_name", "identifier", "aliased_import"}:
                        text = source[child.start_byte : child.end_byte].strip()
                        if text and text != module:
                            names.append(text)
                if not names:
                    names = [None]
                for imported in names:
                    results.append(
                        {
                            "file": str(path.relative_to(self.workspace_root)),
                            "from": module,
                            "import": imported,
                            "line": node.start_point[0] + 1,
                            "parser_backend": "tree-sitter",
                        }
                    )
        return results

    def _tree_sitter_js_symbols(self, path: Path, source: str, root: Any) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for node in self._iter_tree_nodes(root):
            if node.type == "export_statement":
                for child in getattr(node, "named_children", []) or []:
                    if child.type in {"class_declaration", "function_declaration", "lexical_declaration", "method_definition"}:
                        results.extend(self._js_symbol_from_node(path, source, child, exported=True))
            elif node.type in {"class_declaration", "function_declaration", "lexical_declaration", "method_definition"}:
                results.extend(self._js_symbol_from_node(path, source, node, exported=False))
        return results

    def _js_symbol_from_node(self, path: Path, source: str, node: Any, exported: bool) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        if node.type in {"class_declaration", "function_declaration", "method_definition"}:
            name_node = node.child_by_field_name("name")
            if name_node is None:
                return results
            name = source[name_node.start_byte : name_node.end_byte].strip()
            if not name:
                return results
            results.append(
                {
                    "file": str(path.relative_to(self.workspace_root)),
                    "symbol": name,
                    "kind": "class" if node.type == "class_declaration" else "function",
                    "line": node.start_point[0] + 1,
                    "visibility": "public" if exported or not name.startswith("_") else "private",
                    "parser_backend": "tree-sitter",
                }
            )
            return results
        if node.type == "lexical_declaration":
            for child in getattr(node, "named_children", []) or []:
                if child.type != "variable_declarator":
                    continue
                name_node = child.child_by_field_name("name")
                if name_node is None:
                    continue
                name = source[name_node.start_byte : name_node.end_byte].strip()
                if not name:
                    continue
                results.append(
                    {
                        "file": str(path.relative_to(self.workspace_root)),
                        "symbol": name,
                        "kind": "variable",
                        "line": node.start_point[0] + 1,
                        "visibility": "public" if exported or not name.startswith("_") else "private",
                        "parser_backend": "tree-sitter",
                    }
                )
        return results

    def _tree_sitter_js_imports(self, path: Path, source: str, root: Any) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for node in self._iter_tree_nodes(root):
            if node.type != "import_statement":
                continue
            module_node = node.child_by_field_name("source")
            if module_node is None:
                continue
            module = source[module_node.start_byte : module_node.end_byte].strip().strip("'\"")
            if not module:
                continue
            results.append(
                {
                    "file": str(path.relative_to(self.workspace_root)),
                    "from": module,
                    "import": None,
                    "line": node.start_point[0] + 1,
                    "parser_backend": "tree-sitter",
                }
            )
        return results

    def _attest(
        self,
        task: str,
        root: Path,
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
            "parser_backend": self.parser_backend,
            "backend_manifest": self.backend_registry.manifest(),
        }
        signature = self.signer.sign_json(payload)
        attestation = MinerAttestation(
            attestation_id=new_urn_uuid(),
            miner_id=self.miner_id,
            miner_type="ast_miner",
            miner_version=self.miner_version,
            parser_backend=self.parser_backend,
            scan_scope=str(root),
            scan_time=utc_now_iso(),
            duration_ms=duration_ms,
            files_examined=examined,
            results=results,
            confidence=0.95 if results else 1.0,
            content_summary_hash=hash_struct(results),
            signature=signature,
        )
        if self.trust_store is not None:
            self.trust_store.store_miner_attestation(attestation)
        return attestation

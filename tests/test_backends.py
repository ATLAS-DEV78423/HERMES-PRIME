from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from infrastructure.backends import BackendRegistry


class BackendRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        (self.root / "external" / "opa" / "internal" / "compiler" / "wasm" / "opa").mkdir(
            parents=True
        )
        (
            self.root / "external" / "opa" / "internal" / "compiler" / "wasm" / "opa" / "opa.wasm"
        ).write_bytes(b"wasm")
        (self.root / "external" / "tree-sitter").mkdir(parents=True)

    def test_backend_manifest_reports_native_and_fallback_paths(self) -> None:
        registry = BackendRegistry(self.root)
        manifest = registry.manifest()
        self.assertEqual(manifest["preferred"], "tree_sitter")
        self.assertIsNone(registry.opa_executable())
        self.assertFalse(manifest["backends"]["opa"]["available"])
        self.assertTrue(manifest["backends"]["opa"]["details"]["source_tree_present"])
        self.assertTrue(manifest["backends"]["opa"]["details"]["engine_wasm_present"])
        self.assertFalse(manifest["backends"]["opa"]["details"]["compiled_policy_bundle_present"])
        self.assertTrue(manifest["backends"]["tree_sitter"]["available"])
        self.assertTrue(manifest["backends"]["file_miner"]["available"])

    def test_backend_registry_prefers_workspace_opa_binary_when_present(self) -> None:
        opa_binary = self.root / ".hermes-prime" / "bin" / "opa.exe"
        opa_binary.parent.mkdir(parents=True, exist_ok=True)
        opa_binary.write_bytes(b"binary")
        registry = BackendRegistry(self.root)
        self.assertEqual(registry.opa_executable(), opa_binary.resolve())
        self.assertEqual(
            registry.manifest()["backends"]["opa"]["details"]["binary"], str(opa_binary.resolve())
        )


if __name__ == "__main__":
    unittest.main()

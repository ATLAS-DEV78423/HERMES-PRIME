from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hermes_prime.contracts import ActionProposal, ActionType, RiskTier, SentinelDecision
from hermes_prime.utils import new_urn_uuid, utc_now_iso
from infrastructure.sandboxed_forge.forge import SandboxedForge
from miners.ast_miner.miner import AstMiner
from miners.file_miner.miner import FileMiner


class MinerAndForgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        (self.root / "src").mkdir()
        (self.root / "src" / "auth.py").write_text(
            "import os\n\nclass Auth:\n    pass\n\n\ndef parse_config(url):\n    return url\n",
            encoding="utf-8",
        )
        (self.root / "notes.txt").write_text("needle in a haystack", encoding="utf-8")

    def test_file_miner_returns_structured_manifest(self) -> None:
        miner = FileMiner(self.root)
        attestation = miner.search_text("needle")
        payload = attestation.to_dict()
        self.assertEqual(payload["miner_type"], "file_miner")
        self.assertTrue(payload["results"])
        self.assertIn("content_summary_hash", payload)

    def test_ast_miner_extracts_symbols_and_imports(self) -> None:
        miner = AstMiner(self.root)
        symbols = miner.extract_symbols().to_dict()
        imports = miner.trace_imports().to_dict()
        self.assertTrue(symbols["parser_backend"].startswith("tree-sitter:") or symbols["parser_backend"] == "python_ast_fallback")
        self.assertTrue(any(item["symbol"] == "Auth" for item in symbols["results"]))
        self.assertTrue(any(item["import"] == "os" for item in imports["results"]))

    def test_forge_supports_diff_commit_and_rollback(self) -> None:
        forge = SandboxedForge(self.root)
        intent_root = new_urn_uuid()
        capability = "cap:file-write:scoped"

        def authorize(action: ActionProposal) -> SentinelDecision:
            return SentinelDecision(
                decision_id=new_urn_uuid(),
                timestamp=utc_now_iso(),
                action_id=action.action_id,
                permitted=True,
                risk_tier=action.risk_tier,
                policy_rule="test",
                blocking_layer=None,
                denial_reason=None,
                advisory_signals=[],
                consent_required=True,
                audit_written=True,
            )

        session = forge.start_session(
            intent_root=intent_root,
            capability=capability,
            authorizer=authorize,
        )
        session.write_text("src/auth.py", "print('patched')\n")
        diff = session.diff("src/auth.py")
        self.assertIn("+print('patched')", diff)
        committed = session.commit()
        self.assertIn("src/auth.py", committed)
        self.assertIn("print('patched')", (self.root / "src" / "auth.py").read_text(encoding="utf-8"))
        session.write_text("src/auth.py", "second change\n")
        session.rollback()
        self.assertEqual(session.list_changes(), [])

    def test_forge_surfaces_layered_denial_messages(self) -> None:
        forge = SandboxedForge(self.root)
        intent_root = new_urn_uuid()
        capability = "cap:file-write:scoped"

        def deny(action: ActionProposal) -> SentinelDecision:
            return SentinelDecision(
                decision_id=new_urn_uuid(),
                timestamp=utc_now_iso(),
                action_id=action.action_id,
                permitted=False,
                risk_tier=action.risk_tier,
                policy_rule="test",
                blocking_layer=4,
                denial_reason="forbidden",
                advisory_signals=[],
                consent_required=True,
                audit_written=True,
            )

        session = forge.start_session(
            intent_root=intent_root,
            capability=capability,
            authorizer=deny,
        )
        with self.assertRaises(PermissionError) as ctx:
            session.write_text("src/auth.py", "blocked\n")
        self.assertIn("sentinel_denied:layer_4:forbidden", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

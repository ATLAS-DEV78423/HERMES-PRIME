from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from hermes_prime.cli import main
from infrastructure.policy_engine.bundle import PolicyBundle
from infrastructure.policy_engine.sentinel_service import SentinelService


class CliAndBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.policy_root = self.root / "infrastructure" / "policy_engine"
        self.fabric_root = self.root / "external" / "fabric"
        (self.policy_root / "policies").mkdir(parents=True)
        (self.policy_root / "schemas").mkdir(parents=True)
        (self.fabric_root / "data" / "patterns" / "security-review").mkdir(parents=True)
        (self.policy_root / "policies" / "filesystem.rego").write_text(
            "package sentinel.filesystem\n", encoding="utf-8"
        )
        (self.policy_root / "schemas" / "action.json").write_text(
            '{"$schema":"http://json-schema.org/draft-07/schema#"}',
            encoding="utf-8",
        )
        (self.fabric_root / "data" / "patterns" / "security-review" / "system.md").write_text(
            "# security review\ncheck secrets and shell injection\n",
            encoding="utf-8",
        )

    def test_policy_bundle_manifest_is_structured(self) -> None:
        bundle = PolicyBundle(self.policy_root)
        payload = bundle.manifest()
        self.assertTrue(payload["available"])
        self.assertEqual(payload["artifacts"][0]["kind"], "rego")
        self.assertIn("backends", payload)

    def test_sentinel_service_reports_source(self) -> None:
        service = SentinelService(
            workspace_root=self.root, policy_root=self.policy_root
        )
        payload = service.bundle.manifest()
        self.assertIn("opa_available", payload)
        self.assertTrue(payload["available"])

    def test_cli_inspect_json(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(
                [
                    "--workspace",
                    str(self.root),
                    "--json",
                    "inspect",
                ]
        )
        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertTrue(payload["bundle"]["available"])
        self.assertIn("trace_id", payload)
        self.assertIn("backends", payload)
        self.assertEqual(payload["backends"]["preferred"], "tree_sitter")

    def test_cli_doctor_reports_readiness(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(
                [
                    "--workspace",
                    str(self.root),
                    "--json",
                    "doctor",
                ]
        )
        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["workspace_root"], str(self.root))
        self.assertIn("checks", payload)
        self.assertIn("healthy", payload)
        self.assertIn("readiness", payload)

    def test_cli_patch_commit_json(self) -> None:
        sample = self.root / "sample.txt"
        sample.write_text("original", encoding="utf-8")
        mint_out = io.StringIO()
        with redirect_stdout(mint_out):
            mint_code = main(
                [
                    "--workspace",
                    str(self.root),
                    "--json",
                    "mint",
                    "--scope",
                    str(self.root),
                    "--issued-to",
                    "user:test",
                    "--capability",
                    "cap:file-write:scoped",
                    "--actions",
                    "filesystem.write",
                    "filesystem.commit",
                    "--risk-tier-ceiling",
                    "T2",
                ]
            )
        self.assertEqual(mint_code, 0)
        minted = json.loads(mint_out.getvalue())
        token_id = minted["token"]["token_id"]
        intent_root = minted["intent_root"]["intent_root"]

        out = io.StringIO()
        with redirect_stdout(out):
            code = main(
                [
                    "--workspace",
                    str(self.root),
                    "--json",
                    "patch",
                    "--intent-root",
                    intent_root,
                    "--token-id",
                    token_id,
                    "--path",
                    str(sample),
                    "--content",
                    "patched",
                    "--commit",
                ]
            )
        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertTrue(payload["evaluation"]["decision"]["permitted"])
        self.assertIn("patched", payload["diff"])
        self.assertIn("sample.txt", payload["committed"])
        self.assertIn("trace_id", payload)

        replay_out = io.StringIO()
        with redirect_stdout(replay_out):
            replay_code = main(
                [
                    "--workspace",
                    str(self.root),
                    "--json",
                    "replay",
                    "--trace-id",
                    payload["trace_id"],
                ]
            )
        self.assertEqual(replay_code, 0)
        replay_payload = json.loads(replay_out.getvalue())
        self.assertEqual(replay_payload["replay"]["trace_id"], payload["trace_id"])
        self.assertEqual(replay_payload["replay"]["trace_type"], "patch_flow")

    def test_cli_prompt_flow_is_traced_and_replayable(self) -> None:
        sample = self.root / "sample.txt"
        sample.write_text("read this content", encoding="utf-8")
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(
                [
                    "--workspace",
                    str(self.root),
                    "--fabric-root",
                    str(self.fabric_root),
                    "--json",
                    "--prompt",
                    "read sample",
                ]
            )
        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertIn("trace_id", payload)
        self.assertEqual(payload["action"]["action_type"], "filesystem.read")
        self.assertIn("backends", payload)
        self.assertEqual(payload["backends"]["preferred"], "tree_sitter")

        replay_out = io.StringIO()
        with redirect_stdout(replay_out):
            replay_code = main(
                [
                    "--workspace",
                    str(self.root),
                    "--json",
                    "replay",
                    "--trace-id",
                    payload["trace_id"],
                ]
            )
        self.assertEqual(replay_code, 0)
        replay_payload = json.loads(replay_out.getvalue())
        self.assertEqual(replay_payload["replay"]["trace_id"], payload["trace_id"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import unittest
from pathlib import Path


class PolicyArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1]
        self.policy_root = self.root / "infrastructure" / "policy_engine"

    def test_rego_policy_files_exist(self) -> None:
        policies = {
            "common.rego",
            "filesystem.rego",
            "execution.rego",
            "memory.rego",
            "capability.rego",
            "risk_tiers.rego",
            "injection.rego",
            "sentinel.rego",
        }
        found = {path.name for path in (self.policy_root / "policies").glob("*.rego")}
        self.assertTrue(policies.issubset(found))

    def test_schema_files_are_present_and_valid_json(self) -> None:
        for name in ("action.json", "capability_token.json", "sentinel_decision.json"):
            path = self.policy_root / "schemas" / name
            self.assertTrue(path.exists(), path)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["$schema"], "http://json-schema.org/draft-07/schema#")

    def test_rego_mentions_workspace_root_and_path_traversal(self) -> None:
        filesystem_rego = (self.policy_root / "policies" / "filesystem.rego").read_text(
            encoding="utf-8"
        )
        self.assertIn("path_traversal_attempt", filesystem_rego)
        self.assertIn("workspace", filesystem_rego)


if __name__ == "__main__":
    unittest.main()

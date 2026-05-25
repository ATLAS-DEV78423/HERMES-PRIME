from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from hermes_prime.cli import main
from hermes_prime.system_doctor import Severity, run_doctor, run_repair


class SystemDoctorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.policy_root = self.root / "infrastructure" / "policy_engine"
        (self.policy_root / "policies").mkdir(parents=True)
        (self.policy_root / "schemas").mkdir(parents=True)
        (self.policy_root / "policies" / "filesystem.rego").write_text(
            "package sentinel.filesystem\n",
            encoding="utf-8",
        )
        (self.policy_root / "schemas" / "action.json").write_text(
            '{"$schema":"http://json-schema.org/draft-07/schema#"}',
            encoding="utf-8",
        )

    def test_doctor_reports_layout_issue_when_hermes_dir_missing(self) -> None:
        report = run_doctor(self.root)
        layout_issues = [c for c in report.checks if c.check_id == "layout.hermes_dir"]
        self.assertTrue(layout_issues)
        self.assertEqual(layout_issues[0].severity, Severity.ERROR)
        self.assertTrue(layout_issues[0].auto_fixable)

    def test_repair_creates_hermes_layout(self) -> None:
        repair = run_repair(self.root)
        hermes_dir = self.root / ".hermes-prime"
        self.assertTrue(hermes_dir.is_dir())
        self.assertTrue((hermes_dir / "bin").is_dir())
        self.assertTrue((hermes_dir / "palace").is_dir())
        self.assertTrue(any(a.success for a in repair.actions))

        after = run_doctor(self.root)
        layout = next(c for c in after.checks if c.check_id == "layout.hermes_dir")
        self.assertEqual(layout.severity, Severity.OK)

    def test_repair_dry_run_does_not_create_dirs(self) -> None:
        hermes_dir = self.root / ".hermes-prime"
        if hermes_dir.exists():
            shutil.rmtree(hermes_dir)
        run_repair(self.root, dry_run=True)
        self.assertFalse(hermes_dir.exists())

    def test_cli_hp_doctor_json(self) -> None:
        import io
        from contextlib import redirect_stdout

        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["--workspace", str(self.root), "--json", "hp-doctor"])
        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertIn("checks", payload)
        self.assertIn("healthy", payload)

    def test_cli_repair_json(self) -> None:
        import io
        from contextlib import redirect_stdout

        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["--workspace", str(self.root), "--json", "repair"])
        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertIn("actions", payload)


if __name__ == "__main__":
    unittest.main()

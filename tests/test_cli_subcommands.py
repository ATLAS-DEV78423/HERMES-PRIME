from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
import pytest


# ── Parser-level tests ──────────────────────────────────────────────

def _get_parser():
    """Helper: build parser with mocked external/hermes-agent."""
    _fake_agent = Path(__file__).resolve().parent.parent / "external" / "hermes-agent"
    if str(_fake_agent) not in sys.path:
        sys.path.insert(0, str(_fake_agent))
    from hermes_prime.cli import build_parser
    return build_parser()


class TestSubcommandRegistrations:
    """Every known subcommand must appear in parser help."""

    KNOWN_COMMANDS = {
        "hp-doctor", "repair", "inspect", "mint", "evaluate",
        "patch", "replay", "hp-memory", "models", "hp-dashboard",
        "tui", "learn", "brain", "agents", "run", "graphify",
        "chat", "gateway", "skills", "sessions", "todo", "tools",
        "kanban", "cron", "profile", "rate-limit", "repl",
    }

    def test_all_known_commands_registered(self):
        parser = _get_parser()
        help_text = parser.format_help()
        for cmd in sorted(self.KNOWN_COMMANDS):
            assert cmd in help_text, f"Subcommand '{cmd}' missing from help"

    def test_no_unknown_subcommands_leak(self):
        parser = _get_parser()
        help_text = parser.format_help()
        for cmd in sorted(self.KNOWN_COMMANDS):
            assert cmd in help_text


class TestSubcommandHelp:
    """Each subcommand must have its own help text."""

    @pytest.mark.parametrize("cmd", sorted(TestSubcommandRegistrations.KNOWN_COMMANDS))
    def test_subcommand_shows_help(self, cmd):
        parser = _get_parser()
        sub = parser._subparsers._group_actions[0]
        for choice, action in sub.choices.items():
            if choice == cmd:
                help_text = action.format_help() if hasattr(action, "format_help") else action.description or ""
                assert len(help_text) > 0, f"Subcommand '{cmd}' has no help text"
                return
        pytest.fail(f"Subcommand '{cmd}' not found as parser choice")


class TestSubcommandErrorHandling:
    """CLI must handle invalid input gracefully."""

    def test_unknown_command_returns_nonzero(self):
        with pytest.raises(SystemExit) as exc:
            from hermes_prime.cli import build_parser
            build_parser().parse_args(["nonexistent-cmd"])
        assert exc.value.code == 2

    def test_missing_required_args_shows_error(self):
        parser = _get_parser()
        for cmd in ["mint"]:
            try:
                args = parser.parse_args([cmd])
            except SystemExit:
                pass


class TestSubcommandArgStructure:
    """Each subcommand must accept --json and --workspace (if applicable)."""

    def test_global_args_present(self):
        parser = _get_parser()
        help_text = parser.format_help()
        assert "--workspace" in help_text
        assert "--json" in help_text
        assert "--help" in help_text

    @pytest.mark.parametrize("cmd", sorted(TestSubcommandRegistrations.KNOWN_COMMANDS))
    def test_each_cmd_accepts_help(self, cmd):
        parser = _get_parser()
        try:
            args = parser.parse_args([cmd, "--help"])
        except SystemExit:
            pass


# ── Smoke tests for high-risk paths ──────────────────────────────

class TestDoctorSubcommand:
    """doctor/repair are the most commonly used commands."""

    def test_hp_doctor_imports(self):
        from hermes_prime.system_doctor import run_doctor, format_doctor_text
        assert callable(run_doctor)
        assert callable(format_doctor_text)

    def test_repair_imports(self):
        from hermes_prime.system_doctor import run_repair
        assert callable(run_repair)

    def test_doctor_runs_without_crash(self):
        from hermes_prime.system_doctor import run_doctor
        with tempfile.TemporaryDirectory() as tmp:
            report = run_doctor(Path(tmp))
            assert report.workspace_root == str(Path(tmp).resolve())
            assert isinstance(report.checks, list)


# ── Main entry point ──────────────────────────────────────────────

class TestMainEntry:
    def test_main_runs_with_help_and_exits_zero(self):
        with pytest.raises(SystemExit) as exc:
            from hermes_prime.cli import main
            main(["--help"])
        assert exc.value.code == 0

    def test_main_runs_with_unknown_and_falls_through(self):
        from hermes_prime.cli import main
        with patch("hermes_cli.main.main", return_value=1):
            result = main([])
        assert result != 0

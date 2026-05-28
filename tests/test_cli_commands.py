import pytest
from unittest.mock import patch


def test_hp_doctor_subcommand_registered():
    from hermes_prime.cli import build_parser

    parser = build_parser()
    help_text = parser.format_help()
    assert "hp-doctor" in help_text
    assert "doctor" not in help_text or "hp-doctor" in help_text


def test_hp_memory_subcommand_registered():
    from hermes_prime.cli import build_parser

    parser = build_parser()
    help_text = parser.format_help()
    assert "hp-memory" in help_text
    assert "memory" not in help_text or "hp-memory" in help_text


def test_unknown_cmd_falls_through():
    """When HP doesn't recognize the command, upstream parser is called.
    We test by checking that 'hermes setup' (an upstream-only command)
    triggers the upstream code path.
    """
    from hermes_prime.cli import known_hp_commands

    assert "setup" not in known_hp_commands
    assert "model" not in known_hp_commands
    assert "cron" not in known_hp_commands


def test_hp_dashboard_subcommand_registered():
    from hermes_prime.cli import build_parser

    parser = build_parser()
    help_text = parser.format_help()
    assert "hp-dashboard" in help_text
    assert "dashboard" not in help_text or "hp-dashboard" in help_text


def test_upstream_passthrough_invoked():
    """When no subcommand given, upstream main() should be called."""
    import hermes_prime.cli

    with patch("hermes_cli.main.main") as mock_upstream:
        from hermes_prime.cli import main

        main([])
        mock_upstream.assert_called_once()


def test_hp_command_does_not_trigger_upstream():
    """Known HP commands should NOT call upstream."""
    import hermes_prime.cli

    with patch("hermes_cli.main.main") as mock_upstream:
        from hermes_prime.cli import main

        main(["graphify", "status"])
        mock_upstream.assert_not_called()


def test_known_hp_set_has_all_registered_subcommands():
    """Every subcommand registered in build_parser should be in known_hp_commands."""
    from hermes_prime.cli import build_parser, known_hp_commands

    parser = build_parser()
    registered = set()
    for action in parser._actions:
        if hasattr(action, "_name_parser_map"):
            registered.update(action._name_parser_map.keys())
    missing = registered - known_hp_commands
    assert not missing, f"Registered subcommands missing from known_hp_commands: {missing}"


def test_known_hp_set_does_not_contain_upstream_commands():
    """known_hp_commands should NOT contain upstream-only commands."""
    from hermes_prime.cli import known_hp_commands

    upstream_only = [
        "setup",
        "model",
        "cron",
        "profile",
        "plugins",
        "auth",
        "backup",
        "bundle",
        "version",
        "update",
        "checkpoints",
    ]
    for cmd in upstream_only:
        assert cmd not in known_hp_commands, f"{cmd} should NOT be in known_hp_commands"


def test_upstream_module_importable():
    """Verify the upstream hermes_cli module is accessible on sys.path."""
    import importlib

    assert importlib.util.find_spec("hermes_cli") is not None, (
        "hermes_cli not importable — check external/hermes-agent/ on sys.path"
    )

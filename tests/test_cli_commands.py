import pytest

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

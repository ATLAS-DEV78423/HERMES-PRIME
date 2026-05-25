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

def test_hp_dashboard_subcommand_registered():
    from hermes_prime.cli import build_parser
    parser = build_parser()
    help_text = parser.format_help()
    assert "hp-dashboard" in help_text
    assert "dashboard" not in help_text or "hp-dashboard" in help_text

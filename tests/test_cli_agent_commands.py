import pytest


def test_skills_subcommand_registered():
    from hermes_prime.cli import build_parser
    parser = build_parser()
    help_text = parser.format_help()
    assert "skills" in help_text


def test_sessions_subcommand_registered():
    from hermes_prime.cli import build_parser
    parser = build_parser()
    help_text = parser.format_help()
    assert "sessions" in help_text


def test_todo_subcommand_registered():
    from hermes_prime.cli import build_parser
    parser = build_parser()
    help_text = parser.format_help()
    assert "todo" in help_text


def test_tools_subcommand_registered():
    from hermes_prime.cli import build_parser
    parser = build_parser()
    help_text = parser.format_help()
    assert "tools" in help_text

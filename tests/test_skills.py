from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


def test_skill_store_create():
    from hermes_prime.agent.skills.store import SkillStore

    with tempfile.TemporaryDirectory() as tmp:
        store = SkillStore(Path(tmp) / "skills.json")
        store.create("test_skill", "print('hello')", "python", tags=["test"])
        skills = store.list_all()
        assert len(skills) == 1
        assert skills[0]["name"] == "test_skill"


def test_skill_store_search():
    from hermes_prime.agent.skills.store import SkillStore

    with tempfile.TemporaryDirectory() as tmp:
        store = SkillStore(Path(tmp) / "skills.json")
        store.create(
            "web_scraper", "import requests", "python", tags=["web", "scraping"]
        )
        store.create(
            "data_analyzer", "import pandas", "python", tags=["data", "analysis"]
        )
        results = store.search("web")
        assert len(results) == 1
        assert results[0]["name"] == "web_scraper"


def test_skill_manager_register_tool():
    from hermes_prime.agent.skills.manager import SkillManager

    mgr = SkillManager()
    assert "skills_list" in mgr.get_tool_names()
    assert "skill_view" in mgr.get_tool_names()

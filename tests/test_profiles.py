from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture
def home(tmp_path: Path) -> Path:
    return tmp_path / "home"


@pytest.fixture
def manager(tmp_path: Path) -> "ProfileManager":
    from hermes_prime.profiles import ProfileManager

    return ProfileManager(tmp_path / "home")


def test_init_creates_profiles_dir(tmp_path: Path) -> None:
    from hermes_prime.profiles import ProfileManager

    h = tmp_path / "custom_root"
    mgr = ProfileManager(h)
    assert mgr.home_root == h.resolve()
    assert (h / "profiles").exists()


def test_init_default_home() -> None:
    from hermes_prime.profiles import ProfileManager

    mgr = ProfileManager()
    assert mgr.home_root.name == ".hermes"
    assert mgr.home_root.parent == Path.home()


def test_list_profiles_empty(manager: "ProfileManager") -> None:
    assert manager.list_profiles() == []


def test_create_profile_success(manager: "ProfileManager") -> None:
    result = manager.create_profile("work", description="Work profile")
    assert result["status"] == "created"
    assert result["name"] == "work"
    profile_path = Path(result["path"])
    assert profile_path.exists()
    assert (profile_path / "config.yaml").exists()
    assert (profile_path / ".env").exists()
    assert (profile_path / "state.db").exists()
    assert (profile_path / "skills").is_dir()

    import yaml
    config = yaml.safe_load((profile_path / "config.yaml").read_text())
    assert config["name"] == "work"
    assert config["description"] == "Work profile"


def test_create_profile_default_description(manager: "ProfileManager") -> None:
    result = manager.create_profile("no_desc")
    assert result["status"] == "created"
    import yaml
    config = yaml.safe_load((Path(result["path"]) / "config.yaml").read_text())
    assert config["description"] == ""


def test_create_profile_already_exists(manager: "ProfileManager") -> None:
    manager.create_profile("personal")
    result = manager.create_profile("personal")
    assert result == {"error": "Profile 'personal' already exists"}


def test_list_profiles_after_creation(manager: "ProfileManager") -> None:
    manager.create_profile("work", description="Work stuff")
    manager.create_profile("personal", description="Personal stuff")
    profiles = manager.list_profiles()
    assert len(profiles) == 2
    names = {p["name"] for p in profiles}
    assert names == {"work", "personal"}
    for p in profiles:
        assert "path" in p
        assert "description" in p


def test_list_profiles_with_description_in_config(manager: "ProfileManager") -> None:
    manager.create_profile("dev", description="Development")
    profiles = manager.list_profiles()
    dev = [p for p in profiles if p["name"] == "dev"][0]
    assert dev["description"] == "Development"


def test_delete_profile_success(manager: "ProfileManager") -> None:
    manager.create_profile("temp")
    result = manager.delete_profile("temp")
    assert result == {"name": "temp", "status": "deleted"}
    assert not (manager.profiles_root / "temp").exists()
    assert len(manager.list_profiles()) == 0


def test_delete_profile_not_found(manager: "ProfileManager") -> None:
    result = manager.delete_profile("nonexistent")
    assert result == {"error": "Profile 'nonexistent' not found"}


def test_delete_profile_default(manager: "ProfileManager") -> None:
    manager.create_profile("default")
    result = manager.delete_profile("default")
    assert result == {"error": "Cannot delete default profile"}
    assert (manager.profiles_root / "default").exists()


def test_rename_profile_success(manager: "ProfileManager") -> None:
    manager.create_profile("old_name", description="rename me")
    result = manager.rename_profile("old_name", "new_name")
    assert result == {"old_name": "old_name", "new_name": "new_name", "status": "renamed"}
    assert not (manager.profiles_root / "old_name").exists()
    assert (manager.profiles_root / "new_name").exists()

    import yaml
    config = yaml.safe_load((manager.profiles_root / "new_name" / "config.yaml").read_text())
    assert config["name"] == "new_name"


def test_rename_profile_not_found(manager: "ProfileManager") -> None:
    result = manager.rename_profile("ghost", "something")
    assert result == {"error": "Profile 'ghost' not found"}


def test_rename_profile_target_exists(manager: "ProfileManager") -> None:
    manager.create_profile("a")
    manager.create_profile("b")
    result = manager.rename_profile("a", "b")
    assert result == {"error": "Profile 'b' already exists"}


def test_switch_to_success(manager: "ProfileManager") -> None:
    manager.create_profile("staging")
    result = manager.switch_to("staging")
    assert result["name"] == "staging"
    assert result["status"] == "active"
    assert os.environ.get("HERMES_HOME") == str(manager.profiles_root / "staging")


def test_switch_to_not_found(manager: "ProfileManager") -> None:
    result = manager.switch_to("phantom")
    assert result == {"error": "Profile 'phantom' not found"}


def test_switch_to_sets_env_var(manager: "ProfileManager") -> None:
    manager.create_profile("production")
    manager.switch_to("production")
    assert os.environ["HERMES_HOME"] == str(manager.profiles_root / "production")


def test_get_active_default(manager: "ProfileManager") -> None:
    if "HERMES_HOME" in os.environ:
        saved = os.environ.pop("HERMES_HOME")
    try:
        active = manager.get_active()
        assert active["name"] == "default"
        assert active["hermes_home"] == str(manager.home_root)
    finally:
        if "HERMES_HOME" in locals().get("saved", ""):
            os.environ["HERMES_HOME"] = saved


def test_get_active_with_env_var(manager: "ProfileManager") -> None:
    manager.create_profile("active_profile")
    profile_path = str(manager.profiles_root / "active_profile")
    os.environ["HERMES_HOME"] = profile_path
    try:
        active = manager.get_active()
        assert active["name"] == "active_profile"
        assert active["hermes_home"] == profile_path
    finally:
        del os.environ["HERMES_HOME"]


def test_get_active_when_env_is_not_a_profile_dir(manager: "ProfileManager") -> None:
    os.environ["HERMES_HOME"] = str(manager.home_root / "nonexistent")
    try:
        active = manager.get_active()
        assert active["name"] == "default"
    finally:
        del os.environ["HERMES_HOME"]


def test_ignores_dot_prefixed_dirs(tmp_path: Path) -> None:
    from hermes_prime.profiles import ProfileManager

    mgr = ProfileManager(tmp_path / "home")
    mgr.create_profile("visible")
    (mgr.profiles_root / ".hidden").mkdir()
    profiles = mgr.list_profiles()
    names = {p["name"] for p in profiles}
    assert "visible" in names
    assert ".hidden" not in names


def test_list_profiles_skips_files(tmp_path: Path) -> None:
    from hermes_prime.profiles import ProfileManager

    mgr = ProfileManager(tmp_path / "home")
    mgr.create_profile("valid")
    (mgr.profiles_root / "not_a_dir.txt").write_text("hello")
    profiles = mgr.list_profiles()
    assert len(profiles) == 1
    assert profiles[0]["name"] == "valid"

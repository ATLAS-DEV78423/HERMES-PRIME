from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any


class ProfileManager:
    """Multi-instance profile management."""

    def __init__(self, home_root: str | Path | None = None):
        self.home_root = Path(home_root).resolve() if home_root else Path.home() / ".hermes"
        self.profiles_root = self.home_root / "profiles"
        self.profiles_root.mkdir(parents=True, exist_ok=True)

    def list_profiles(self) -> list[dict[str, Any]]:
        profiles: list[dict[str, Any]] = []
        if not self.profiles_root.exists():
            return profiles
        for entry in sorted(self.profiles_root.iterdir()):
            if entry.is_dir() and not entry.name.startswith("."):
                config_file = entry / "config.yaml"
                desc = ""
                if config_file.exists():
                    for line in config_file.read_text().splitlines():
                        if line.startswith("description:"):
                            desc = line.split(":", 1)[1].strip().strip("\"'")
                            break
                profiles.append({
                    "name": entry.name,
                    "path": str(entry),
                    "description": desc,
                })
        return profiles

    def create_profile(self, name: str, description: str = "") -> dict[str, Any]:
        profile_path = self.profiles_root / name
        if profile_path.exists():
            return {"error": f"Profile '{name}' already exists"}
        profile_path.mkdir(parents=True)
        config = {"name": name, "description": description}
        import yaml
        with open(profile_path / "config.yaml", "w") as f:
            yaml.dump(config, f)
        (profile_path / ".env").touch()
        (profile_path / "state.db").touch()
        (profile_path / "skills").mkdir(exist_ok=True)
        return {"name": name, "path": str(profile_path), "status": "created"}

    def delete_profile(self, name: str) -> dict[str, Any]:
        profile_path = self.profiles_root / name
        if not profile_path.exists():
            return {"error": f"Profile '{name}' not found"}
        if name == "default":
            return {"error": "Cannot delete default profile"}
        shutil.rmtree(profile_path)
        return {"name": name, "status": "deleted"}

    def rename_profile(self, old_name: str, new_name: str) -> dict[str, Any]:
        old_path = self.profiles_root / old_name
        new_path = self.profiles_root / new_name
        if not old_path.exists():
            return {"error": f"Profile '{old_name}' not found"}
        if new_path.exists():
            return {"error": f"Profile '{new_name}' already exists"}
        old_path.rename(new_path)
        config_file = new_path / "config.yaml"
        if config_file.exists():
            import yaml
            config = yaml.safe_load(config_file.read_text()) or {}
            config["name"] = new_name
            with open(config_file, "w") as f:
                yaml.dump(config, f)
        return {"old_name": old_name, "new_name": new_name, "status": "renamed"}

    def switch_to(self, name: str) -> dict[str, Any]:
        profile_path = self.profiles_root / name
        if not profile_path.exists():
            return {"error": f"Profile '{name}' not found"}
        os.environ["HERMES_HOME"] = str(profile_path)
        return {"name": name, "hermes_home": str(profile_path), "status": "active"}

    def get_active(self) -> dict[str, Any]:
        hermes_home = os.environ.get("HERMES_HOME", str(self.home_root))
        active_name = "default"
        profiles_root = self.home_root / "profiles"
        if profiles_root.exists():
            for entry in profiles_root.iterdir():
                if entry.is_dir() and str(entry) == hermes_home:
                    active_name = entry.name
                    break
        return {"name": active_name, "hermes_home": hermes_home}

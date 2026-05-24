from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch


class VaultClientTests(unittest.TestCase):
    def test_vault_client_fallback_to_env(self) -> None:
        from hermes_prime.vault.vault_client import VaultClient
        with patch.dict(os.environ, {"HERMES_TEST_KEY": "fallback-value"}, clear=True):
            client = VaultClient(url="http://localhost:9999", token="", fallback_env_prefix="HERMES_")
            secret = client.read("test/key")
            self.assertIsNotNone(secret)
            self.assertEqual(secret.value, "fallback-value")
            self.assertEqual(secret.metadata.get("source"), "env_fallback")

    def test_vault_client_no_hvac(self) -> None:
        from hermes_prime.vault.vault_client import VaultClient
        client = VaultClient(url="http://localhost:9999", token="")
        self.assertFalse(client.available)

    def test_vault_client_health_no_hvac(self) -> None:
        from hermes_prime.vault.vault_client import VaultClient
        client = VaultClient(url="http://localhost:9999", token="")
        health = client.health()
        self.assertIn("url", health)
        self.assertFalse(health["available"])

    def test_vault_client_list_paths_no_hvac(self) -> None:
        from hermes_prime.vault.vault_client import VaultClient
        client = VaultClient(url="http://localhost:9999", token="")
        paths = client.list_paths()
        self.assertEqual(paths, [])

    def test_vault_client_write_raises_without_hvac(self) -> None:
        from hermes_prime.vault.vault_client import VaultClient, VaultError
        client = VaultClient(url="http://localhost:9999", token="")
        with self.assertRaises(VaultError):
            client.write("test/path", {"key": "val"})


class RecoveryTests(unittest.TestCase):
    def test_shutdown_not_requested_initially(self) -> None:
        from hermes_prime.recovery import shutdown_requested
        self.assertFalse(shutdown_requested())

    def test_safe_main_returns_zero(self) -> None:
        from hermes_prime.recovery import safe_main
        result = safe_main(lambda: 0)
        self.assertEqual(result, 0)

    def test_safe_main_returns_int(self) -> None:
        from hermes_prime.recovery import safe_main
        result = safe_main(lambda: 42)
        self.assertEqual(result, 42)

    def test_safe_main_handles_keyboard_interrupt(self) -> None:
        from hermes_prime.recovery import safe_main

        def raises_kb():
            raise KeyboardInterrupt()

        result = safe_main(raises_kb)
        self.assertEqual(result, 130)

    def test_safe_main_handles_system_exit(self) -> None:
        from hermes_prime.recovery import safe_main

        def raises_exit():
            raise SystemExit(3)

        result = safe_main(raises_exit)
        self.assertEqual(result, 3)

    def test_safe_main_handles_exception(self) -> None:
        from hermes_prime.recovery import safe_main

        def raises_exc():
            raise RuntimeError("boom")

        result = safe_main(raises_exc)
        self.assertEqual(result, 1)

    def test_safe_main_clears_shutdown_flag(self) -> None:
        from hermes_prime.recovery import safe_main, shutdown_requested
        safe_main(lambda: 0)
        self.assertFalse(shutdown_requested())


class RecoveryFileTests(unittest.TestCase):
    def test_module_imports(self) -> None:
        import hermes_prime.recovery
        self.assertTrue(hasattr(hermes_prime.recovery, "safe_main"))
        self.assertTrue(hasattr(hermes_prime.recovery, "install_signal_handlers"))
        self.assertTrue(hasattr(hermes_prime.recovery, "shutdown_requested"))


class MainEntryTests(unittest.TestCase):
    def test_main_module_imports(self) -> None:
        import hermes_prime.__main__ as m
        self.assertTrue(hasattr(m, "_entry"))


class PackageDataTests(unittest.TestCase):
    def test_pyproject_has_classifiers(self) -> None:
        import tomllib
        with open("pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        classifiers = data["project"].get("classifiers", [])
        self.assertTrue(len(classifiers) > 5)
        self.assertIn("License :: OSI Approved :: MIT License", classifiers)

    def test_pyproject_has_urls(self) -> None:
        import tomllib
        with open("pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        urls = data["project"].get("urls", {})
        self.assertIn("Homepage", urls)
        self.assertIn("Repository", urls)

    def test_pyproject_has_authors(self) -> None:
        import tomllib
        with open("pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        authors = data["project"].get("authors", [])
        self.assertTrue(len(authors) > 0)

    def test_dockerfile_exists(self) -> None:
        self.assertTrue(Path("Dockerfile").exists())

    def test_ci_workflow_has_matrix(self) -> None:
        import yaml
        with open(".github/workflows/ci.yml") as f:
            data = yaml.safe_load(f)
        jobs = data.get("jobs", {})
        test_job = jobs.get("test", {})
        strategy = test_job.get("strategy", {})
        matrix = strategy.get("matrix", {})
        self.assertIn("python-version", matrix)
        self.assertIn("os", matrix)

    def test_publish_workflow_exists(self) -> None:
        self.assertTrue(Path(".github/workflows/publish.yml").exists())

    def test_vault_package_importable(self) -> None:
        from hermes_prime.vault import VaultClient, VaultError
        self.assertTrue(callable(VaultClient))
        self.assertTrue(issubclass(VaultError, Exception))


if __name__ == "__main__":
    unittest.main()

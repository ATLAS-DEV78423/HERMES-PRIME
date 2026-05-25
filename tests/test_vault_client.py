from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from hermes_prime.vault.vault_client import VaultClient, VaultError, VaultSecret


class TestVaultSecret(unittest.TestCase):
    def test_default_values(self):
        secret = VaultSecret(path="test/path", key="mykey", value="myvalue")
        self.assertEqual(secret.path, "test/path")
        self.assertEqual(secret.key, "mykey")
        self.assertEqual(secret.value, "myvalue")
        self.assertEqual(secret.version, 0)
        self.assertEqual(secret.metadata, {})

    def test_metadata_defaults_to_empty_dict(self):
        secret = VaultSecret(path="p", key="k", value="v", version=3)
        self.assertEqual(secret.metadata, {})

    def test_explicit_metadata(self):
        secret = VaultSecret(path="p", key="k", value="v", metadata={"env": "prod"})
        self.assertEqual(secret.metadata, {"env": "prod"})


class TestVaultClientInit(unittest.TestCase):
    def test_default_url_and_token(self):
        client = VaultClient()
        self.assertEqual(client._url, "http://127.0.0.1:8200")
        self.assertEqual(client._token, "")

    def test_custom_url_and_token(self):
        client = VaultClient(url="http://vault:8200", token="s.abc123")
        self.assertEqual(client._url, "http://vault:8200")
        self.assertEqual(client._token, "s.abc123")

    def test_env_var_fallback_for_url(self, monkeypatch=None):
        with patch.dict("os.environ", {"VAULT_ADDR": "http://env-vault:8200"}, clear=True):
            client = VaultClient()
            self.assertEqual(client._url, "http://env-vault:8200")

    def test_env_var_fallback_for_token(self):
        with patch.dict("os.environ", {"VAULT_TOKEN": "env-token"}, clear=True):
            client = VaultClient()
            self.assertEqual(client._token, "env-token")

    def test_custom_prefix(self):
        client = VaultClient(fallback_env_prefix="MYAPP_")
        self.assertEqual(client._fallback_prefix, "MYAPP_")

    def test_custom_mount_point(self):
        client = VaultClient(mount_point="kv-v2")
        self.assertEqual(client._mount_point, "kv-v2")


class TestVaultClientAvailable(unittest.TestCase):
    def test_available_false_when_hvac_not_installed(self):
        client = VaultClient()
        with patch.object(client, "_lazy_init") as mock_init:
            client._hvac_available = False
            self.assertFalse(client.available)

    def test_available_true_when_authenticated(self):
        client = VaultClient()
        client._hvac_available = True
        client._client = MagicMock()
        client._client.is_authenticated.return_value = True
        self.assertTrue(client.available)

    def test_available_false_on_exception(self):
        client = VaultClient()
        client._hvac_available = True
        client._client = MagicMock()
        client._client.is_authenticated.side_effect = Exception("fail")
        self.assertFalse(client.available)


class TestVaultClientRead(unittest.TestCase):
    def test_read_returns_env_var_when_hvac_not_installed(self):
        client = VaultClient(fallback_env_prefix="TEST_")
        client._hvac_available = False
        path = "myapp/db"
        env_key = "TEST_MYAPP_DB"
        with patch.dict("os.environ", {env_key: "env-value"}):
            secret = client.read(path)
            self.assertIsNotNone(secret)
            self.assertEqual(secret.value, "env-value")
            self.assertEqual(secret.metadata, {"source": "env_fallback"})

    def test_read_returns_none_when_no_env_var_and_no_hvac(self):
        client = VaultClient(fallback_env_prefix="TEST_")
        client._hvac_available = False
        with patch.dict("os.environ", {}, clear=True):
            secret = client.read("some/path")
            self.assertIsNone(secret)

    def test_read_returns_secret_from_vault(self):
        client = VaultClient()
        client._hvac_available = True
        client._client = MagicMock()
        client._client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {
                "data": {"password": "s3cret"},
                "metadata": {"version": 2},
            }
        }
        secret = client.read("db/creds", key="password")
        self.assertIsNotNone(secret)
        self.assertEqual(secret.value, "s3cret")
        self.assertEqual(secret.version, 2)

    def test_read_returns_none_on_vault_exception(self):
        client = VaultClient()
        client._hvac_available = True
        client._client = MagicMock()
        client._client.secrets.kv.v2.read_secret_version.side_effect = Exception("fail")
        secret = client.read("db/creds")
        self.assertIsNone(secret)

    def test_read_returns_none_when_data_empty(self):
        client = VaultClient()
        client._hvac_available = True
        client._client = MagicMock()
        client._client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {}}
        }
        secret = client.read("empty/path", key="missing")
        self.assertIsNone(secret)

    def test_read_env_var_takes_precedence_over_vault(self):
        client = VaultClient(fallback_env_prefix="TEST_")
        client._hvac_available = True
        client._client = MagicMock()
        env_key = "TEST_DB_PASSWORD"
        with patch.dict("os.environ", {env_key: "from-env"}):
            secret = client.read("db/password")
            self.assertEqual(secret.value, "from-env")
            self.assertEqual(secret.metadata, {"source": "env_fallback"})
            client._client.secrets.kv.v2.read_secret_version.assert_not_called()

    def test_read_strips_leading_slash(self):
        client = VaultClient(fallback_env_prefix="TEST_")
        client._hvac_available = False
        with patch.dict("os.environ", {"TEST_HELLO_WORLD": "val"}):
            secret = client.read("/hello/world")
            self.assertIsNotNone(secret)
            self.assertEqual(secret.path, "hello/world")


class TestVaultClientWrite(unittest.TestCase):
    def test_write_raises_vault_error_when_hvac_not_installed(self):
        client = VaultClient()
        client._hvac_available = False
        with self.assertRaises(VaultError):
            client.write("path", {"key": "val"})

    def test_write_succeeds_when_hvac_available(self):
        client = VaultClient()
        client._hvac_available = True
        client._client = MagicMock()
        result = client.write("my/secret", {"user": "admin"})
        self.assertTrue(result)
        client._client.secrets.kv.v2.create_or_update_secret.assert_called_once_with(
            path="my/secret",
            secret={"user": "admin"},
            mount_point="secret",
        )

    def test_write_raises_on_hvac_exception(self):
        client = VaultClient()
        client._hvac_available = True
        client._client = MagicMock()
        client._client.secrets.kv.v2.create_or_update_secret.side_effect = Exception("fail")
        with self.assertRaises(VaultError):
            client.write("path", {"k": "v"})


class TestVaultClientListPaths(unittest.TestCase):
    def test_list_paths_returns_empty_when_hvac_not_installed(self):
        client = VaultClient()
        client._hvac_available = False
        self.assertEqual(client.list_paths("some/path"), [])

    def test_list_paths_returns_keys(self):
        client = VaultClient()
        client._hvac_available = True
        client._client = MagicMock()
        client._client.secrets.kv.v2.list_secrets.return_value = {
            "data": {"keys": ["a", "b", "c/"]}
        }
        self.assertEqual(client.list_paths(""), ["a", "b", "c/"])

    def test_list_paths_returns_empty_on_exception(self):
        client = VaultClient()
        client._hvac_available = True
        client._client = MagicMock()
        client._client.secrets.kv.v2.list_secrets.side_effect = Exception("fail")
        self.assertEqual(client.list_paths(""), [])


class TestVaultClientHealth(unittest.TestCase):
    def test_health_returns_url_and_available_when_not_available(self):
        client = VaultClient()
        with patch.object(client, "_lazy_init"):
            client._hvac_available = False
            report = client.health()
            self.assertEqual(report["url"], "http://127.0.0.1:8200")
            self.assertFalse(report["available"])
            self.assertNotIn("authenticated", report)

    def test_health_returns_auth_and_sealed_when_available(self):
        client = VaultClient()
        client._hvac_available = True
        client._client = MagicMock()
        client._client.is_authenticated.return_value = True
        client._client.is_sealed.return_value = False
        report = client.health()
        self.assertTrue(report["authenticated"])
        self.assertFalse(report["sealed"])

    def test_health_includes_error_on_exception(self):
        client = VaultClient()
        client._hvac_available = True
        client._client = MagicMock()
        client._client.is_authenticated.side_effect = Exception("conn refused")
        report = client.health()
        self.assertIn("error", report)
        self.assertEqual(report["error"], "conn refused")

    def test_health_calls_lazy_init(self):
        client = VaultClient()
        with patch.object(client, "_lazy_init") as mock_init:
            client.health()
            mock_init.assert_called_once()


class TestVaultClientSealed(unittest.TestCase):
    def test_sealed_false_when_hvac_not_available(self):
        client = VaultClient()
        client._hvac_available = False
        self.assertFalse(client.sealed)

    def test_sealed_delegates_to_client(self):
        client = VaultClient()
        client._hvac_available = True
        client._client = MagicMock()
        client._client.is_sealed.return_value = True
        self.assertTrue(client.sealed)

    def test_sealed_returns_true_on_exception(self):
        client = VaultClient()
        client._hvac_available = True
        client._client = MagicMock()
        client._client.is_sealed.side_effect = Exception("fail")
        self.assertTrue(client.sealed)


class TestVaultClientLazyInit(unittest.TestCase):
    def test_lazy_init_skips_when_client_already_set(self):
        client = VaultClient()
        client._client = "already_set"
        with patch("hermes_prime.vault.vault_client.hvac", create=True) as mock_hvac:
            client._lazy_init()
            mock_hvac.Client.assert_not_called()

    def test_lazy_init_sets_hvac_available_on_success(self):
        import sys
        fake_hvac = MagicMock()
        fake_hvac.Client.return_value = MagicMock()
        with patch.dict("sys.modules", {"hvac": fake_hvac}):
            client = VaultClient()
            client._client = None
            client._lazy_init()
            self.assertTrue(client._hvac_available)

    def test_lazy_init_sets_hvac_available_false_on_import_error(self):
        import builtins
        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "hvac":
                raise ImportError("no hvac")
            return original_import(name, *args, **kwargs)

        client = VaultClient()
        client._client = None
        with patch("builtins.__import__", side_effect=fake_import):
            client._lazy_init()
            self.assertFalse(client._hvac_available)
            self.assertIsNone(client._client)


if __name__ == "__main__":
    unittest.main()

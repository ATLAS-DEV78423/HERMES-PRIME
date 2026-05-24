from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


class VaultError(Exception):
    pass


class VaultSealedError(VaultError):
    pass


@dataclass
class VaultSecret:
    path: str
    key: str
    value: str
    version: int = 0
    metadata: dict[str, Any] = None

    def __post_init__(self) -> None:
        if self.metadata is None:
            self.metadata = {}


class VaultClient:
    def __init__(
        self,
        url: str | None = None,
        token: str | None = None,
        mount_point: str = "secret",
        verify: bool = True,
        timeout: int = 10,
        fallback_env_prefix: str = "HERMES_",
    ) -> None:
        self._url = url or os.environ.get("VAULT_ADDR", "http://127.0.0.1:8200")
        self._token = token or os.environ.get("VAULT_TOKEN", "")
        self._mount_point = mount_point
        self._verify = verify
        self._timeout = timeout
        self._fallback_prefix = fallback_env_prefix
        self._client: Any = None
        self._hvac_available = False

    def _lazy_init(self) -> None:
        if self._client is not None:
            return
        try:
            import hvac
            self._client = hvac.Client(
                url=self._url,
                token=self._token,
                verify=self._verify,
                timeout=self._timeout,
            )
            self._hvac_available = True
        except ImportError:
            self._hvac_available = False
            self._client = None
            logger.warning("hvac not installed; VaultClient falls back to env vars")

    @property
    def available(self) -> bool:
        self._lazy_init()
        if not self._hvac_available:
            return False
        try:
            return self._client.is_authenticated()
        except Exception:
            return False

    @property
    def sealed(self) -> bool:
        if not self._hvac_available:
            return False
        try:
            return self._client.is_sealed()
        except Exception:
            return True

    def read(self, path: str, key: str | None = None) -> VaultSecret | None:
        norm_path = path.strip("/")
        env_key = f"{self._fallback_prefix}{norm_path.upper().replace('/', '_')}"
        env_value = os.environ.get(env_key)
        if env_value is not None:
            return VaultSecret(
                path=norm_path,
                key=key or "value",
                value=env_value,
                version=0,
                metadata={"source": "env_fallback"},
            )

        if not self._hvac_available:
            return None

        try:
            secret = self._client.secrets.kv.v2.read_secret_version(
                path=norm_path,
                mount_point=self._mount_point,
            )
        except Exception as exc:
            logger.debug("Vault read failed for %s: %s", norm_path, exc)
            return None

        data = secret.get("data", {}).get("data", {})
        if not data:
            return None

        lookup_key = key or "value"
        raw = data.get(lookup_key)
        if raw is None:
            return None

        meta = secret.get("data", {}).get("metadata", {})
        return VaultSecret(
            path=norm_path,
            key=lookup_key,
            value=str(raw),
            version=int(meta.get("version", 0)),
            metadata=meta,
        )

    def write(self, path: str, values: dict[str, Any]) -> bool:
        if not self._hvac_available:
            raise VaultError("hvac not installed; cannot write to Vault")
        try:
            self._client.secrets.kv.v2.create_or_update_secret(
                path=path.strip("/"),
                secret=values,
                mount_point=self._mount_point,
            )
            return True
        except Exception as exc:
            raise VaultError(f"Vault write failed for {path}: {exc}") from exc

    def list_paths(self, path: str = "") -> list[str]:
        if not self._hvac_available:
            return []
        try:
            result = self._client.secrets.kv.v2.list_secrets(
                path=path.strip("/"),
                mount_point=self._mount_point,
            )
            return result.get("data", {}).get("keys", [])
        except Exception:
            return []

    def health(self) -> dict[str, Any]:
        self._lazy_init()
        report: dict[str, Any] = {
            "url": self._url,
            "available": self._hvac_available,
        }
        if self._hvac_available:
            try:
                report["authenticated"] = self._client.is_authenticated()
                report["sealed"] = self._client.is_sealed()
            except Exception as e:
                report["error"] = str(e)
        return report

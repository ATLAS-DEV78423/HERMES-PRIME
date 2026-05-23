"""
Signing service abstraction.

The reference implementation uses in-process ed25519. Production deployments
swap in KMS/HSM. The interface is intentionally tiny so that swapping is
mechanical.
"""

from __future__ import annotations

import base64
import hashlib
from abc import ABC, abstractmethod
from typing import Optional


class Signer(ABC):
    """Abstract signing oracle. Returns signatures; never exposes keys."""

    @property
    @abstractmethod
    def identity(self) -> str:
        """Stable identity string for this signer."""

    @property
    @abstractmethod
    def kind(self) -> str:
        """'service' or 'personal'."""

    @property
    @abstractmethod
    def cert_chain(self) -> list[str]:
        """Certificate chain as base64-encoded DER, leaf first."""

    @property
    @abstractmethod
    def algorithm(self) -> str:
        """Signature algorithm identifier (e.g., 'ed25519')."""

    @abstractmethod
    def sign(self, payload: bytes) -> str:
        """Sign the payload, return base64 signature."""

    @abstractmethod
    def verify(self, payload: bytes, signature_b64: str) -> bool:
        """Verify a signature against the payload using this signer's public key."""


class Ed25519Signer(Signer):
    """
    Reference signer using in-process ed25519.
    Suitable for tests and local dev; not for production.

    Production: implement Signer against your KMS/HSM SDK.
    """

    def __init__(
        self,
        identity: str,
        kind: str = "service",
        seed: Optional[bytes] = None,
    ) -> None:
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                Ed25519PrivateKey,
            )
        except ImportError as exc:
            raise ImportError(
                "Ed25519Signer requires the 'cryptography' package. "
                "Install with: pip install cryptography"
            ) from exc

        self._identity = identity
        self._kind = kind
        if seed is not None:
            self._private_key = Ed25519PrivateKey.from_private_bytes(seed)
        else:
            self._private_key = Ed25519PrivateKey.generate()
        self._public_key = self._private_key.public_key()

    @property
    def identity(self) -> str:
        return self._identity

    @property
    def kind(self) -> str:
        return self._kind

    @property
    def cert_chain(self) -> list[str]:
        # Reference impl returns the raw public key as a "cert."
        # Production: return real X.509 chain.
        from cryptography.hazmat.primitives.serialization import (
            Encoding,
            PublicFormat,
        )

        public_bytes = self._public_key.public_bytes(
            encoding=Encoding.Raw, format=PublicFormat.Raw
        )
        return [base64.b64encode(public_bytes).decode("ascii")]

    @property
    def algorithm(self) -> str:
        return "ed25519"

    def sign(self, payload: bytes) -> str:
        signature = self._private_key.sign(payload)
        return base64.b64encode(signature).decode("ascii")

    def verify(self, payload: bytes, signature_b64: str) -> bool:
        from cryptography.exceptions import InvalidSignature

        try:
            sig_bytes = base64.b64decode(signature_b64)
            self._public_key.verify(sig_bytes, payload)
            return True
        except (InvalidSignature, Exception):
            return False


def verify_with_public_key_b64(
    public_key_b64: str, payload: bytes, signature_b64: str
) -> bool:
    """
    Verify a signature given a public key (as returned in cert_chain).
    Used by verifiers that don't hold the signer instance.
    """
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )

        public_bytes = base64.b64decode(public_key_b64)
        sig_bytes = base64.b64decode(signature_b64)
        public_key = Ed25519PublicKey.from_public_bytes(public_bytes)
        public_key.verify(sig_bytes, payload)
        return True
    except Exception:
        return False

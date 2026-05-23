"""
KMS-backed Signer implementations.

These wrap cloud KMS / HashiCorp Vault Transit. Each implementation:
  - Holds NO private key material in process.
  - Authenticates to the KMS via workload identity (IAM role, GCP SA,
    AppRole, etc.) — configured outside this code.
  - Performs signing as a remote operation.
  - Exposes the public key (or a public key reference) via cert_chain.

All three classes are intentionally minimal. Production deployments
typically need:
  - Retry with backoff (KMS rate limits)
  - Connection pooling
  - Local public-key caching with periodic refresh
  - Metrics on signing latency

These are left as deployment concerns. The core signing/verification
contract is what's encoded here.
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Optional

from cogtrust.signing import Signer

logger = logging.getLogger("cogtrust.signers.kms")


# ----------------------------------------------------------------------
# AWS KMS
# ----------------------------------------------------------------------


class AwsKmsSigner(Signer):
    """
    Signer backed by AWS KMS.

    Requires boto3. The KMS key must be of type ECC_NIST_P256 or RSA;
    for ed25519 use a different KMS provider (AWS KMS does not yet
    support ed25519 as of writing).

    Usage:
        signer = AwsKmsSigner(
            identity="attestation_service",
            key_id="arn:aws:kms:us-east-1:123:key/abc-123",
            region="us-east-1",
            algorithm="ECDSA_SHA_256",
        )

    Authentication: boto3 picks up AWS credentials from environment /
    IAM role / config file via the standard chain. Do not pass keys.
    """

    def __init__(
        self,
        identity: str,
        key_id: str,
        region: str,
        algorithm: str = "ECDSA_SHA_256",
        kind: str = "service",
    ) -> None:
        try:
            import boto3
        except ImportError as exc:
            raise ImportError(
                "AwsKmsSigner requires boto3. pip install boto3"
            ) from exc

        self._identity = identity
        self._kind = kind
        self._key_id = key_id
        self._signing_algorithm = algorithm
        self._client = boto3.client("kms", region_name=region)
        self._public_key_cache: Optional[bytes] = None

    @property
    def identity(self) -> str:
        return self._identity

    @property
    def kind(self) -> str:
        return self._kind

    @property
    def cert_chain(self) -> list[str]:
        if self._public_key_cache is None:
            resp = self._client.get_public_key(KeyId=self._key_id)
            self._public_key_cache = resp["PublicKey"]
        return [base64.b64encode(self._public_key_cache).decode("ascii")]

    @property
    def algorithm(self) -> str:
        # AWS KMS algorithm string; verifiers must understand this.
        return self._signing_algorithm.lower().replace("_", "-")

    def sign(self, payload: bytes) -> str:
        resp = self._client.sign(
            KeyId=self._key_id,
            Message=payload,
            MessageType="RAW",
            SigningAlgorithm=self._signing_algorithm,
        )
        return base64.b64encode(resp["Signature"]).decode("ascii")

    def verify(self, payload: bytes, signature_b64: str) -> bool:
        try:
            sig_bytes = base64.b64decode(signature_b64)
            resp = self._client.verify(
                KeyId=self._key_id,
                Message=payload,
                MessageType="RAW",
                Signature=sig_bytes,
                SigningAlgorithm=self._signing_algorithm,
            )
            return bool(resp.get("SignatureValid", False))
        except Exception:  # pylint: disable=broad-except
            logger.exception("AWS KMS verify failed")
            return False


# ----------------------------------------------------------------------
# GCP KMS
# ----------------------------------------------------------------------


class GcpKmsSigner(Signer):
    """
    Signer backed by Google Cloud KMS.

    Requires google-cloud-kms. Authenticates via Application Default
    Credentials (workload identity).

    Usage:
        signer = GcpKmsSigner(
            identity="attestation_service",
            key_name=(
                "projects/p/locations/global/keyRings/r/"
                "cryptoKeys/k/cryptoKeyVersions/1"
            ),
        )
    """

    def __init__(
        self,
        identity: str,
        key_name: str,
        kind: str = "service",
    ) -> None:
        try:
            from google.cloud import kms_v1
        except ImportError as exc:
            raise ImportError(
                "GcpKmsSigner requires google-cloud-kms. "
                "pip install google-cloud-kms"
            ) from exc

        self._identity = identity
        self._kind = kind
        self._key_name = key_name
        self._client = kms_v1.KeyManagementServiceClient()
        self._public_key_cache: Optional[str] = None

    @property
    def identity(self) -> str:
        return self._identity

    @property
    def kind(self) -> str:
        return self._kind

    @property
    def cert_chain(self) -> list[str]:
        if self._public_key_cache is None:
            resp = self._client.get_public_key(request={"name": self._key_name})
            # PEM-encoded; strip headers and re-encode for our format.
            pem = resp.pem
            # Strip BEGIN/END lines and whitespace; base64-encode the body.
            body_lines = [
                line for line in pem.splitlines()
                if line and not line.startswith("-----")
            ]
            self._public_key_cache = "".join(body_lines)
        return [self._public_key_cache]

    @property
    def algorithm(self) -> str:
        # Set during key creation; verifiers must understand.
        return "gcp-kms-ec-sha256"  # adjust to actual key algorithm

    def sign(self, payload: bytes) -> str:
        import hashlib as _h
        digest = _h.sha256(payload).digest()
        resp = self._client.asymmetric_sign(
            request={
                "name": self._key_name,
                "digest": {"sha256": digest},
            }
        )
        return base64.b64encode(resp.signature).decode("ascii")

    def verify(self, payload: bytes, signature_b64: str) -> bool:
        # GCP KMS does not expose a verify API; verifiers must use the
        # public key locally with the appropriate algorithm. Defer to
        # an out-of-band verification helper.
        from cogtrust.signing import verify_with_public_key_b64
        return verify_with_public_key_b64(
            self.cert_chain[0], payload, signature_b64
        )


# ----------------------------------------------------------------------
# HashiCorp Vault Transit
# ----------------------------------------------------------------------


class VaultTransitSigner(Signer):
    """
    Signer backed by HashiCorp Vault Transit engine.

    Requires hvac. Authenticates via VAULT_TOKEN env var or AppRole
    (configured on the hvac client).

    Usage:
        client = hvac.Client(url='https://vault.example.com', token=...)
        signer = VaultTransitSigner(
            identity="attestation_service",
            vault_client=client,
            key_name="cogtrust-signing-key",
            mount_point="transit",
        )

    Vault Transit supports ed25519 natively, which makes this the
    preferred KMS choice for matching the in-process reference signer.
    """

    def __init__(
        self,
        identity: str,
        vault_client: Any,
        key_name: str,
        mount_point: str = "transit",
        kind: str = "service",
    ) -> None:
        self._identity = identity
        self._kind = kind
        self._key_name = key_name
        self._mount_point = mount_point
        self._client = vault_client
        self._public_key_cache: Optional[str] = None

    @property
    def identity(self) -> str:
        return self._identity

    @property
    def kind(self) -> str:
        return self._kind

    @property
    def cert_chain(self) -> list[str]:
        if self._public_key_cache is None:
            resp = self._client.secrets.transit.read_key(
                name=self._key_name,
                mount_point=self._mount_point,
            )
            # Read the latest key version's public_key (PEM).
            versions = resp["data"]["keys"]
            latest = max(int(v) for v in versions.keys())
            pem = versions[str(latest)]["public_key"]
            body_lines = [
                line for line in pem.splitlines()
                if line and not line.startswith("-----")
            ]
            self._public_key_cache = "".join(body_lines)
        return [self._public_key_cache]

    @property
    def algorithm(self) -> str:
        return "ed25519"  # adjust to match key type

    def sign(self, payload: bytes) -> str:
        b64_payload = base64.b64encode(payload).decode("ascii")
        resp = self._client.secrets.transit.sign_data(
            name=self._key_name,
            hash_input=b64_payload,
            mount_point=self._mount_point,
            prehashed=False,
        )
        # Vault returns "vault:v1:<base64>" — strip the prefix.
        vault_sig = resp["data"]["signature"]
        _, _, sig_b64 = vault_sig.rsplit(":", 2)
        return sig_b64

    def verify(self, payload: bytes, signature_b64: str) -> bool:
        # Vault has a verify API.
        try:
            b64_payload = base64.b64encode(payload).decode("ascii")
            vault_sig = f"vault:v1:{signature_b64}"
            resp = self._client.secrets.transit.verify_signed_data(
                name=self._key_name,
                hash_input=b64_payload,
                signature=vault_sig,
                mount_point=self._mount_point,
                prehashed=False,
            )
            return bool(resp["data"].get("valid", False))
        except Exception:  # pylint: disable=broad-except
            logger.exception("Vault Transit verify failed")
            return False

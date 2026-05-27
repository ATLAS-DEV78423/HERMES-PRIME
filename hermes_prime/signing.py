from __future__ import annotations

import hmac
import hashlib
from dataclasses import dataclass
from typing import Any

from .utils import canonical_json, normalize_for_json


@dataclass(frozen=True)
class HMACSigner:
    """Local-dev signing helper.

    This is intentionally simple and deterministic. It is sufficient for the
    workspace implementation and tests, while keeping the trust boundary explicit
    for later replacement with a hardware-backed signer.
    """

    identity: str
    secret: bytes

    def sign(self, payload: bytes) -> str:
        digest = hmac.new(self.secret, payload, hashlib.sha256).hexdigest()
        return f"sig:hmac-sha256:{digest}"

    def verify(self, payload: bytes, signature: str) -> bool:
        return hmac.compare_digest(self.sign(payload), signature)

    def sign_json(self, data: Any) -> str:
        return self.sign(canonical_json(normalize_for_json(data)).encode("utf-8"))

    def verify_json(self, data: Any, signature: str) -> bool:
        return self.verify(canonical_json(normalize_for_json(data)).encode("utf-8"), signature)

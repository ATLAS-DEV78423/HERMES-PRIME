from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hermes_prime.llm.client import LLMRequest, LLMResponse
from hermes_prime.utils import hash_struct, new_urn_uuid, utc_now_iso


@dataclass
class InferenceAttestation:
    """Attestation of an LLM inference call."""

    attestation_id: str
    model: str
    timestamp: str
    request_hash: str  # Hash of the full request
    response_hash: str  # Hash of the response
    tokens_used: int
    latency_ms: float
    finish_reason: str
    prompt_hash: str  # Hash of the system + user prompt only
    signature: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "attestation_id": self.attestation_id,
            "model": self.model,
            "timestamp": self.timestamp,
            "request_hash": self.request_hash,
            "response_hash": self.response_hash,
            "tokens_used": self.tokens_used,
            "latency_ms": self.latency_ms,
            "finish_reason": self.finish_reason,
            "prompt_hash": self.prompt_hash,
            "signature": self.signature,
        }


class InferenceLogger:
    """Logs and attests LLM inference calls."""

    @staticmethod
    def create_attestation(
        request: LLMRequest,
        response: LLMResponse,
        signature: str = "",
    ) -> InferenceAttestation:
        """Create signed attestation for inference call."""
        # Hash the request for auditability
        request_dict = {
            "model": request.model,
            "messages": request.messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        request_hash = hash_struct(request_dict)

        # Hash just the prompt (system + user messages)
        prompt_text = "\n".join(
            [msg["content"] for msg in request.messages if msg.get("role") in ("system", "user")]
        )
        prompt_hash = hash_struct({"prompt": prompt_text})

        # Hash the response
        response_hash = hash_struct(response.message_content)

        return InferenceAttestation(
            attestation_id=new_urn_uuid(),
            model=request.model,
            timestamp=utc_now_iso(),
            request_hash=request_hash,
            response_hash=response_hash,
            tokens_used=response.tokens_used,
            latency_ms=response.latency_ms,
            finish_reason=response.finish_reason,
            prompt_hash=prompt_hash,
            signature=signature,
        )

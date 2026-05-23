from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

from hermes_prime.contracts import ActionProposal, CapabilityToken, IntentRoot, SentinelDecision
from hermes_prime.utils import new_urn_uuid, utc_now_iso
from infrastructure.backends import BackendRegistry

from .bundle import PolicyBundle


class OpaUnavailableError(RuntimeError):
    pass


class OpaPolicyAdapter:
    def __init__(self, bundle_root: str | Path) -> None:
        self.bundle = PolicyBundle(bundle_root)
        self.registry = BackendRegistry(self.bundle.root.parent.parent)

    def available(self) -> bool:
        return self.registry.opa_executable() is not None and self.bundle.available()

    def executable_path(self) -> Path | None:
        return self.registry.opa_executable()

    def evaluate(
        self,
        action: ActionProposal,
        intent_root: IntentRoot,
        capability: CapabilityToken | None = None,
        advisory_signals: Optional[list[str]] = None,
    ) -> SentinelDecision:
        if not self.available():
            raise OpaUnavailableError("opa binary or policy bundle unavailable")
        opa_binary = self.executable_path()
        if opa_binary is None:
            raise OpaUnavailableError("opa executable unavailable")
        action_data = action.to_dict()
        action_data["scope"] = Path(action.scope).resolve().as_posix()
        action_data["risk_level"] = action.risk_tier.level
        capability_data = None
        if capability is not None:
            capability_data = capability.to_dict()
            capability_data["scope"] = Path(capability.scope).resolve().as_posix()
            capability_data["risk_tier_ceiling_level"] = capability.risk_tier_ceiling.level
        input_payload = {
            "action": action_data,
            "action_type": action.action_type.value,
            "scope": action_data["scope"],
            "risk_tier": action.risk_tier.value,
            "parameters": action.parameters,
            "capability": capability_data,
            "intent_root": intent_root.to_dict(),
            "workspace_root": self.bundle.root.parent.parent.resolve().as_posix(),
            "advisory_signals": advisory_signals or [],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
            json.dump(input_payload, handle, sort_keys=True)
            input_path = Path(handle.name)
        try:
            proc = subprocess.run(
                [
                    str(opa_binary),
                    "eval",
                    "--v0-compatible",
                    "--format=json",
                    "--data",
                    str(self.bundle.policy_root),
                    "--input",
                    str(input_path),
                    "data.sentinel.decision",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode != 0:
                raise OpaUnavailableError(proc.stderr.strip() or "opa eval failed")
            result = json.loads(proc.stdout)
            expressions = result.get("result", [])
            decision_payload: dict[str, Any] = {}
            for expression in expressions:
                if "expressions" in expression and expression["expressions"]:
                    value = expression["expressions"][0].get("value")
                    if isinstance(value, dict):
                        decision_payload = value
                        break
            if not decision_payload:
                raise OpaUnavailableError("opa returned no decision payload")
            decision_payload.setdefault("decision_id", new_urn_uuid())
            decision_payload.setdefault("timestamp", utc_now_iso())
            return SentinelDecision(**decision_payload)
        finally:
            input_path.unlink(missing_ok=True)

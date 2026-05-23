package sentinel

import data.sentinel.capability
import data.sentinel.execution
import data.sentinel.filesystem
import data.sentinel.injection
import data.sentinel.memory

allow {
  input.action_type == "filesystem.read"
  filesystem.allow
  capability.allow
  not injection.blocked
}

allow {
  input.action_type == "filesystem.write"
  filesystem.allow
  capability.allow
  not injection.blocked
}

allow {
  input.action_type == "filesystem.commit"
  filesystem.allow
  capability.allow
  not injection.blocked
}

allow {
  input.action_type == "execution.command"
  execution.allow
  capability.allow
  not injection.blocked
}

allow {
  input.action_type == "memory.write"
  memory.allow
  capability.allow
  not injection.blocked
}

allow {
  input.action_type == "agent.spawn"
  capability.allow
  not injection.blocked
}

allow {
  input.action_type == "agent.kill"
  capability.allow
  not injection.blocked
}

decision := {
  "action_id": input.action.action_id,
  "permitted": true,
  "risk_tier": input.risk_tier,
  "policy_rule": "sentinel.allow",
  "blocking_layer": null,
  "denial_reason": null,
  "advisory_signals": input.advisory_signals,
  "consent_required": false,
  "audit_written": true,
} {
  allow
}

decision := {
  "action_id": input.action.action_id,
  "permitted": false,
  "risk_tier": input.risk_tier,
  "policy_rule": "sentinel.default_deny",
  "blocking_layer": 1,
  "denial_reason": "policy_denied",
  "advisory_signals": input.advisory_signals,
  "consent_required": true,
  "audit_written": true,
} {
  not allow
}

package sentinel.capability

default allow := false

allow {
  input.capability.intent_root == input.action.intent_root
  startswith(input.action.scope, input.capability.scope)
  input.action.risk_level <= input.capability.risk_tier_ceiling_level
}

deny_reason := "scope_exceeds_token" {
  not startswith(input.action.scope, input.capability.scope)
}

deny_reason := "intent_root_mismatch" {
  input.capability.intent_root != input.action.intent_root
}

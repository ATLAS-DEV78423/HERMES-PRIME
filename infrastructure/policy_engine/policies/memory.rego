package sentinel.memory

default allow := false

allow {
  input.action_type == "memory.write"
  input.tier == "quarantine"
}

deny_reason := "memory_writes_blocked_until_provenance_layer" {
  input.action_type == "memory.write"
  input.tier != "quarantine"
}


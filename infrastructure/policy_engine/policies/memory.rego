package sentinel.memory

default allow := false

allow {
  input.action_type == "memory.write"
  input.tier == "quarantine"
}

allow {
  input.action_type == "memory.write"
  input.tier == "authoritative"
  input.corroborated == true
}

deny_reason := "authoritative_memory_writes_require_promotion" {
  input.action_type == "memory.write"
  input.tier == "authoritative"
  input.corroborated != true
}

deny_reason := "memory_writes_blocked_until_provenance_layer" {
  input.action_type == "memory.write"
  input.tier != "quarantine"
  input.tier != "authoritative"
}

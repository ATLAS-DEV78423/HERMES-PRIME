package sentinel.filesystem

import data.sentinel.common

default allow := false

allow {
  input.action_type == "filesystem.read"
  not common.contains_null_byte(input.scope)
  not common.path_traversal(input.scope)
  not common.shell_metacharacter(input.scope)
  common.in_workspace(input.scope)
  input.risk_tier == "T0"
}

allow {
  input.action_type == "filesystem.write"
  not common.contains_null_byte(input.scope)
  not common.path_traversal(input.scope)
  not common.shell_metacharacter(input.scope)
  common.in_workspace(input.scope)
  input.risk_tier == "T1"
}

allow {
  input.action_type == "filesystem.commit"
  not common.contains_null_byte(input.scope)
  not common.path_traversal(input.scope)
  not common.shell_metacharacter(input.scope)
  common.in_workspace(input.scope)
  input.risk_tier == "T2"
}

deny_reason := "path_traversal_attempt" {
  common.path_traversal(input.scope)
}

deny_reason := "scope_outside_workspace" {
  not common.in_workspace(input.scope)
}

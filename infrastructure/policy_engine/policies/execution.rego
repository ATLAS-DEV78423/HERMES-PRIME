package sentinel.execution

import future.keywords.in

import data.sentinel.common

default allow := false

allow {
  input.action_type == "execution.command"
  input.command in {"python", "python3", "echo"}
  not common.contains_null_byte(input.command)
  not common.shell_metacharacter(input.command)
}

deny_reason := "execution_blocked_until_forge_mvp" {
  input.action_type == "execution.command"
}

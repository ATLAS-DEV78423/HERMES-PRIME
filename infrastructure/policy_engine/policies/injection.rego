package sentinel.injection

import future.keywords.every

import data.sentinel.common

default allow := true

allow {
  not common.contains_null_byte(input.scope)
  not common.shell_metacharacter(input.scope)
  not common.path_traversal(input.scope)
  every v in input.parameters {
    not is_string(v)
  }
}

allow {
  not common.contains_null_byte(input.scope)
  not common.shell_metacharacter(input.scope)
  not common.path_traversal(input.scope)
  every v in input.parameters {
    not common.shell_metacharacter(v)
    not common.contains_null_byte(v)
  }
}

deny_reason := "injection_signature_in_parameter" {
  some v in input.parameters
  is_string(v)
  common.shell_metacharacter(v)
}

deny_reason := "injection_signature_in_parameter" {
  some v in input.parameters
  is_string(v)
  common.contains_null_byte(v)
}

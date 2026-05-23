package sentinel.common

default deny := false

contains_null_byte(s) {
  contains(s, "\u0000")
}

decoded(value) := output {
  output := lower(urlquery.decode(value))
}

path_traversal(value) {
  contains(decoded(value), "..")
}

shell_metacharacter(value) {
  re_match("[;&|`]", value)
}

in_workspace(scope) {
  startswith(scope, input.workspace_root)
}

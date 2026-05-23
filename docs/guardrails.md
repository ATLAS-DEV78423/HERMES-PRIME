# Usage Guardrails and Security Guidelines

This document summarizes runtime guardrails, policy expectations, and CI checks to maintain safe operation.

- **Policy-first enforcement:** All generated actions must be evaluated by Sentinel (OPA) before execution.
- **Fail-closed defaults:** If policy verification or the TrustStore is unreachable, decline to execute high-risk actions.
- **Least privilege:** Mint capability tokens with the narrowest possible scope and shortest TTL.
- **Memory attestation:** Every memory write must include a `MemoryAttestation` and be attached to the `AuditTrace`.
- **Operator consent:** T3+ actions require explicit operator approval; the CLI surfaces clear intent roots and scope.
- **Auditability:** All actions and attestations are recorded in the TrustStore with cryptographic signing.

CI / Automation:
- Add `bandit` security scan to CI for Python code.
- Run `mypy` and `ruff` in CI with `--strict` flags where feasible.
- Ensure tests exercise Sentinel rejection paths and memory attestation attachments.

Runtime Recommendations:
- Run `hermes-prime` inside an isolated container with filesystem quotas and limited network egress.
- Provide a dedicated secrets backend (e.g., Vault) for production signing keys.
- Monitor audit logs for unusual capability mint patterns or repeated Sentinel rejects.

For more architecture-level threat analysis, see [hermes/THREAT_MODEL.md](hermes/THREAT_MODEL.md).

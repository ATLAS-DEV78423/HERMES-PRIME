# Hermes Prime Workspace

This workspace is the local synthesis area for the Hermes Prime architecture.

It combines three layers:

1. `hermes/` - doctrine, invariants, gates, and architecture decisions
2. `claude-code-refrlow/` - bounded retrieval and subagent dispatch
3. `cognitive-trust/` - provenance, attestation, lineage, and revocation

The upstream repositories and reference systems in the broader stack are treated as:

- core implementation targets
- reference architectures
- optional integrations

The goal is not to clone everything first. The goal is to define the primitives, keep the trust boundaries clean, and only pull in external code where it materially helps implementation.

Start here:

- [FOUNDATIONAL_PRIMITIVES.md](FOUNDATIONAL_PRIMITIVES.md)
- [WORKSPACE_MANIFEST.yaml](WORKSPACE_MANIFEST.yaml)
- [MONOREPO_LAYOUT.md](MONOREPO_LAYOUT.md)

Hermes Prime commands:

```bash
hermes-prime doctor
hermes-prime inspect --json
hermes-prime mint --scope <scope> --issued-to <user> --capability <name> --actions filesystem.read
hermes-prime evaluate --intent-root <urn:uuid:...> --token-id <urn:uuid:...> --action-type filesystem.read --scope <scope> --capability <name>
hermes-prime patch --intent-root <urn:uuid:...> --token-id <urn:uuid:...> --path <absolute-or-relative-file> --content "<new content>" --commit
hermes-prime replay --trace-id <urn:uuid:...>
hermes-prime --prompt "read sample"
```

Quick start:

1. Inspect the Sentinel bundle with `hermes-prime inspect`.
2. Check local readiness with `hermes-prime doctor`.
3. Mint an intent root and token with `hermes-prime mint`.
4. Evaluate or patch only with the issued intent root and token.
5. Use `hermes-prime replay` to inspect the stored audit trail.

Hermes Prime will prefer a workspace-local OPA binary at `.hermes-prime/bin/opa.exe` when present, then fall back to the deterministic Python harness only if the native path is unavailable.

Trust model:

- Sentinel decides.
- Forge mutates only after Sentinel approval.
- Miners observe and attest only.
- Capability tokens are scoped to intent roots.
- Replay is part of the product, not an internal debug trick.

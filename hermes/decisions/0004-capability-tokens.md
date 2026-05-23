# ADR 0004: Capability Tokens Instead of Credential Injection

**Status:** Accepted
**Date:** 2026-05-22
**Doctrine references:** P4
**Invariants:** I3, I4

---

## Context

The naive way for an agent to use a credential is to give the agent the credential and let it call the API directly. This means:

- The credential is in the agent's context (often the prompt).
- The credential may be in logs, traces, embeddings, and memory.
- The agent has full credential authority — not just for the intended action.
- Revocation requires rotating the credential.
- A prompt injection that exfiltrates context leaks the credential.

This is incompatible with P4 (the agent never owns secrets) and I3 (secrets never enter model context).

---

## Decision

Hermes never receives raw credentials. Instead, Hermes requests **capability tokens** from Vault. A capability token is a short-lived, narrowly scoped, signed authorization to perform a specific action class.

```json
{
  "capability": "github_push",
  "scope": "repo:org/project",
  "actions": ["commit", "push"],
  "expires_at": "2026-05-22T14:35:00Z",
  "intent_root": "sig:user:abc123:session:xyz",
  "issued_to": "hermes:session:nnn",
  "nonce": "..."
}
```

Token properties:

- **Short-lived.** TTL is determined by risk tier; default is minutes, not hours.
- **Narrowly scoped.** Scope is the minimum required for the declared action.
- **Bound to intent root.** Token references a signed user intent (P3).
- **Signed by Vault.** Forge verifies signature before execution.
- **Non-transferable.** Issued-to binding prevents token reuse across sessions.
- **Revocable.** Vault may invalidate at any time; propagation SLA defined in I14.

Forge holds the underlying credential transiently during execution, in zeroizable memory, and discards it on completion. Hermes never sees the credential itself.

---

## Alternatives Considered

### A. Credential in agent context (naive)
Reject. Violates P4, I3. Catastrophic on prompt injection.

### B. Long-lived OAuth tokens given to agent
Reject. Marginal improvement over A. Still exposes a credential-equivalent to model context. Revocation slow.

### C. Credential broker that proxies all calls
Considered. Functionally equivalent to capability tokens with execution-side enforcement. Capability tokens are a more general abstraction — they work across multiple Forge implementations and allow Vault-side scope verification. Chose capability tokens; broker pattern is a possible Forge implementation detail.

### D. Capability tokens (chosen)
Accept. Achieves P4 (agent never owns secrets), I3 (secrets never in context), I4 (short-lived, scoped), and supports P3 (intent provenance) via the intent_root binding.

---

## Consequences

### Positive
- Prompt injection of Hermes cannot exfiltrate credentials, because Hermes does not have them.
- Capability scope is enforced at Vault, not at the agent's good behavior.
- Revocation is fast (I14): invalidate the token, no need to rotate the underlying credential.
- Audit trail is rich: every capability mint and use is logged with intent_root reference.
- Forge can support multiple credential backends (OAuth, API key, signed request) behind one capability abstraction.

### Negative
- Adds round-trip latency: every privileged action requires capability minting.
- Adds operational complexity: Vault, Sentinel, and Forge must agree on capability schema and lifecycle.
- Token caching to mitigate latency must be carefully bounded — too long and revocation SLA degrades.
- Capability registry growth over time ("capability sprawl") is a known maintenance burden.

### Neutral
- Forces all privileged actions to be enumerable. The capability registry becomes the canonical list of what Hermes can do.

---

## Open Questions

- **Intent verification.** Capability tokens reference an intent root, but verifying that the *specific* capability matches the user's intent (not just that an intent root exists) is the open problem named in doctrine §10.1. Current mitigation: scope must be a subset of intent root scope. Not sufficient against sophisticated intent drift (T7).
- **Capability lifecycle.** Naming, deprecation, and rotation of capabilities over time. Tracked separately.
- **Cross-session capabilities.** Long-running workflows that span sessions need special handling. Deferred.

---

## References

- `DOCTRINE.md` §3.3 (Capability tokens)
- `INVARIANTS.md` I3, I4
- `THREAT_MODEL.md` AC5 (capability escalator), T5
- AWS STS as prior art for short-lived, scoped credentials
- Capability-based security (Lampson 1971)

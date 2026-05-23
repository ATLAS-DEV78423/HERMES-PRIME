# Sentinel Core — Design Document

**Status:** Pre-implementation design  
**Location:** `/infrastructure/policy-engine/`  
**Companion to:** ADR 0002, ADR 0007, ADR 0009, `INVARIANTS.md` I1, I7  
**Gate criterion:** A proposed action with an out-of-scope path is **blocked** deterministically. A valid action is **permitted** deterministically. Both outcomes are reproducible and testable.

---

## 0. What Sentinel Is Not

Before describing what Sentinel does, establishing what it is not prevents drift:

- Not an LLM safety classifier. An LLM classifier inherits prompt injection. Sentinel's blocking layers are immune to prompt injection because they contain no LLM.
- Not a firewall in the network sense. Sentinel operates on structured action proposals, not raw packets.
- Not an audit log. Sentinel makes decisions. The audit log records them. Different components.
- Not a capability minter. Vault mints capability tokens. Sentinel validates them.
- Not a reasoning system. Sentinel evaluates. It does not infer.

---

## 1. What Sentinel Does

Sentinel is the deterministic policy kernel through which every proposed action passes before it reaches Forge execution. It answers one question:

> **Is this specific action, with this specific scope, under this specific capability token, permitted right now?**

The answer is yes or no. It is produced by deterministic code. It does not involve model inference.

---

## 2. Layer Architecture

Sentinel is layered. The layer order is execution order. **Earlier layers block; later layers cannot override earlier blocks.**

```
Incoming Action Proposal
         │
         ▼
┌─────────────────────────────────────────────────────┐
│  Layer 1: Schema Validation                         │  BLOCKING / DETERMINISTIC
│  Does the proposal conform to the Action schema?    │
└─────────────────────┬───────────────────────────────┘
                      │ pass
                      ▼
┌─────────────────────────────────────────────────────┐
│  Layer 2: Capability Token Validation               │  BLOCKING / DETERMINISTIC
│  Is the token present, signed, unexpired, and       │
│  issued by Vault for this session?                  │
└─────────────────────┬───────────────────────────────┘
                      │ pass
                      ▼
┌─────────────────────────────────────────────────────┐
│  Layer 3: Intent Root Verification                  │  BLOCKING / DETERMINISTIC
│  Does a valid, unexpired, user-signed intent root   │
│  exist? Does the action's scope fall within it?     │
└─────────────────────┬───────────────────────────────┘
                      │ pass
                      ▼
┌─────────────────────────────────────────────────────┐
│  Layer 4: OPA Policy Evaluation                     │  BLOCKING / DETERMINISTIC
│  Does Rego policy permit this action_type,          │
│  scope, risk_tier, and capability combination?      │
└─────────────────────┬───────────────────────────────┘
                      │ pass
                      ▼
┌─────────────────────────────────────────────────────┐
│  Layer 5: Entropy / Pattern Scan                    │  BLOCKING / DETERMINISTIC
│  Does the proposal contain credential patterns,     │
│  path traversal attempts, or injection signatures?  │
└─────────────────────┬───────────────────────────────┘
                      │ pass
                      ▼
┌─────────────────────────────────────────────────────┐
│  Layer 6: Resource Ceiling Check                    │  BLOCKING / DETERMINISTIC
│  Is this session within token budget, miner         │
│  dispatch quota, and context size ceiling?          │
└─────────────────────┬───────────────────────────────┘
                      │ pass
                      ▼
┌─────────────────────────────────────────────────────┐
│  Layer 7: Behavioral Anomaly Signal (ADVISORY ONLY) │  ADVISORY / PROBABILISTIC
│  Does this action deviate from session baseline?    │
│  Result is a signal — it cannot block alone.        │
└─────────────────────┬───────────────────────────────┘
                      │
                      ▼
               PERMITTED → forward to Forge
```

Layers 1–6 are blocking and deterministic. Layer 7 is advisory only — it can contribute to a combined score that escalates to a higher risk tier, but it cannot block independently.

**If Sentinel's blocking layers ever contain an LLM call, Sentinel is broken.** This is invariant I7.

---

## 3. The Risk Tier Table

Every permitted action carries a risk tier. The tier determines the consent and logging posture.

| Tier | Label               | Examples                                         | Consent required             |
|------|---------------------|--------------------------------------------------|------------------------------|
| T0   | Read-only, local    | File read, symbol lookup, grep                   | None (audited)               |
| T1   | Reversible, local   | File write inside overlay, temp dir mutation     | Batched approval window      |
| T2   | Persistent mutation | Committed file write, git commit                 | Per-action consent           |
| T3   | Credential impact   | Secret read reference, token scope expansion     | Per-action + 2FA             |
| T4   | External side effect| Network call, API write, email send              | Per-action + explicit scope  |
| T5   | Irreversible        | Deletion, deploy, financial transaction          | Per-action + cooldown + dry-run first |

The risk tier is determined by the OPA policy evaluation (Layer 4), not by the proposing agent.

---

## 4. OPA Policy Structure

OPA evaluates Rego policies. The policy structure is organized by action type. Each policy module answers: given an action proposal, is it permitted, and at what risk tier?

```
/infrastructure/policy-engine/
  policies/
    filesystem.rego         # path scope rules, traversal prevention, extension allowlists
    execution.rego          # command allowlist, argument validation
    network.rego            # domain allowlist, port restrictions, protocol rules
    memory.rego             # Atlas write rules, quarantine enforcement
    capability.rego         # token validation, scope subset check
    risk_tiers.rego         # tier assignment logic
    injection.rego          # prompt injection signatures, exfiltration patterns
  schemas/
    action.json             # Action schema (validated at Layer 1)
    capability_token.json   # Token schema (validated at Layer 2)
    sentinel_decision.json  # Output schema (what Sentinel returns)
  tests/
    filesystem_test.rego    # OPA test suite for filesystem policies
    execution_test.rego
    network_test.rego
    ...
```

OPA policies are versioned, tested, and deployed without a running system. The test suite (`opa test ./policies`) validates all policies before any system starts. A failing policy test is a build failure.

---

## 5. The Sentinel Decision Output Schema

Every action proposal produces exactly one Sentinel decision. The schema is fixed:

```json
{
  "decision_id": "urn:uuid:...",
  "timestamp": "2026-05-23T07:20:00Z",
  "action_id": "urn:uuid:...",
  "permitted": true,
  "risk_tier": "T1",
  "policy_rule": "filesystem.read.workspace_scoped",
  "blocking_layer": null,
  "denial_reason": null,
  "advisory_signals": [],
  "consent_required": false,
  "audit_written": true
}
```

On denial:

```json
{
  "decision_id": "urn:uuid:...",
  "timestamp": "2026-05-23T07:20:00Z",
  "action_id": "urn:uuid:...",
  "permitted": false,
  "risk_tier": null,
  "policy_rule": null,
  "blocking_layer": 4,
  "denial_reason": "path_traversal_attempt: scope '/workspace/../etc' exits workspace root",
  "advisory_signals": [],
  "consent_required": null,
  "audit_written": true
}
```

The audit log entry is always written, permitted or not. Denial attempts are as important as grants.

---

## 6. The Filesystem Scope Rules (MVP Policies)

The MVP Sentinel implementation needs these filesystem rules to pass the Step 1 gate criterion:

### 6.1 Workspace Root Enforcement
All filesystem actions must resolve to a path within the declared workspace root. Path normalization happens before scope check — `..` sequences are resolved, symlinks are checked, and the resolved path is compared against the allowed root.

```
DENY if resolved_path does not start with workspace_root
DENY if path contains null bytes
DENY if path contains encoded traversal sequences (%2e%2e, %252e, etc.)
```

### 6.2 Extension Allowlist (for read operations)
Read operations specify a file type context. Unrecognized extensions in sensitive contexts require elevated tier.

### 6.3 Scope Subset Check
The action's declared scope must be a strict subset of the capability token's scope. A token scoped to `/workspace/project` cannot authorize an action scoped to `/workspace/`.

```
DENY if action.scope is not a subset of capability_token.scope
DENY if action.scope is not a subset of intent_root.scope
```

---

## 7. The Prompt Injection Firewall (Layer 5)

Layer 5 applies deterministic pattern matching to the action proposal. It does not analyze the user's prompt (that is Hermes's job). It analyzes the structured action proposal for indicators that an injection has modified it.

### Detection targets in MVP:

| Pattern class | Examples |
|---|---|
| Path traversal | `../`, `..%2f`, `%252e%252e`, null bytes in path |
| Shell metacharacter injection in scope fields | `;`, `&&`, `\|`, backticks appearing in path arguments |
| Credential-shaped strings in scope | Patterns matching API key formats, PEM headers, JWT structure in unexpected fields |
| Action type mismatch | `action_type: filesystem.read` but `scope` contains a command string |
| Oversized proposals | Proposal payload exceeding declared schema field size limits |

These are not heuristics. They are deterministic pattern checks. A proposal either matches a pattern or it does not.

---

## 8. What the MVP Does Not Include

The MVP Sentinel (Step 1) deliberately excludes:

- **Behavioral anomaly detection (Layer 7).** Advisory signals require baseline modeling. That requires operational data. Build it later.
- **Network policy.** No network actions exist yet. Policy is written when the action class exists.
- **Multi-session correlation.** Each decision is evaluated per-session in the MVP. Cross-session pattern analysis is Phase 7 (reliability engineering).
- **Hardware-backed token verification.** Software signature verification is sufficient for MVP. HSM support is a hardening task.

Adding these prematurely produces complexity before the simple path is validated.

---

## 9. Test Requirements for Gate Criterion

The Step 1 gate criterion requires the following tests to pass before work on Step 2 begins:

| Test | Expected outcome |
|---|---|
| Valid `T0` read action, in-scope path, valid token, valid intent root | PERMITTED, tier T0, audit written |
| Valid `T1` write action, in-scope path, valid token, valid intent root | PERMITTED, tier T1, consent flag set |
| Read action with path traversal (`../etc/passwd`) | DENIED at Layer 4, denial reason includes `path_traversal_attempt` |
| Read action with scope outside capability token scope | DENIED at Layer 2 or 4, denial reason includes `scope_exceeds_token` |
| Action with expired capability token | DENIED at Layer 2 |
| Action with no intent root | DENIED at Layer 3 |
| Action with injection signature in scope field | DENIED at Layer 5 |
| Action exceeding session resource ceiling | DENIED at Layer 6 |
| Two sequential deny-and-retry patterns on same session | Advisory signal emitted at Layer 7 (no block) |

All nine must pass. None of these tests involve an LLM. All are deterministic.

---

## 10. What Success Looks Like

After Step 1, a developer should be able to:

1. Write a Rego policy in under 30 minutes and see it enforced immediately in tests.
2. Submit an arbitrary action proposal and receive a structured Sentinel decision in under 10ms.
3. Run `opa test ./policies` and see 100% pass.
4. Grep any Sentinel code path and find zero LLM client imports.

That is the bar. It is not impressive. It is not an AI system. It is a correctly functioning deterministic policy kernel. That is the correct thing to have built first.

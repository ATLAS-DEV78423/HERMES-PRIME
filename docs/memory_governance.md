# Memory Governance Spec

## Memory Types

| Type | Purpose | Retention | Example |
|------|---------|-----------|---------|
| `working` | In-progress scratchpad | 24h or task end | "Currently processing file X" |
| `episodic` | Observed events, agent actions | 90d | "Agent Y deployed to staging" |
| `reflective` | Post-task consolidation output | 30d | "Task Z failed due to timeout" |
| `semantic` | Extracted facts, constraints | permanent | "API endpoint is at /v2/users" |
| `strategic` | Compressed learnings, operational constraints | permanent | "Avoid Tool X > 5 concurrent calls" |
| `governance` | Policies, trust rules, ACLs | immutable | "Tier T3 actions require attestation" |

## Trust Levels (maps to TrustState)

| Level | TrustState | Meaning |
|-------|------------|---------|
| `unverified` | `UNVERIFIED` | Raw observation, no corroboration |
| `inferred` | `OBSERVED` | Seen multiple times, not yet validated |
| `validated` | `VALIDATED` | Corroborated, contradictions resolved |
| `immutable` | `EXECUTABLE` | Governance records, system-owned |

## Retention Tiers

| Tier | Duration | Types |
|------|----------|-------|
| volatile | 24h | working |
| temporary | 30d | reflective |
| standard | 90d | episodic |
| durable | 365d | semantic |
| permanent | never | strategic, governance |

## Ownership Rules

1. Every memory has a `source_agent` — no anonymous memory
2. Governance memories are system-owned, mutable only by the Governor
3. Agent scratchpads (`working`) are agent-private by default
4. Promotion to `validated` requires confidence >= 0.8 or multiple corroborating sources
5. Cross-agent visibility must be explicitly granted, not default

## Decay Policy (basis for Phase 7)

Factors: age, access frequency, contradiction count, trust score, strategic value.
- Immutable governance: never decays
- Validated strategic: never decays
- Audit lineage: never decays
- All other types: decay based on composite score

## Prohibitions

- No raw chain-of-thought storage
- Only store: decisions, constraints, outcomes, validated reasoning summaries
- No anonymous memory (every record has a source_agent)

# Hermes Capability Registry (Simulation)

**Purpose:** Track the Forge capability registry as it grows across the 60-day simulation. Each capability has a declared schema, risk tier, default TTL, and notes on when it was added and why.

**Risk tiers** (from doctrine §8.1):
- **T1** — read-only, local
- **T2** — mutating, reversible, scoped
- **T3** — mutating, scoped, irreversible
- **T4** — privileged, broad scope
- **T5** — destructive or financial

---

## Registry

### Filesystem

| Capability | Risk | Default TTL | Added | Notes |
|-----------|------|-------------|-------|-------|
| `forge.fs.read` | T1 | 5min | Day 1 | Scoped to project dir; symlink-resistant |
| `forge.fs.write` | T2 | 5min | Day 5 | Requires backup snapshot of target path |
| `forge.fs.delete` | T3 | 1min | Day 11 | Per-action consent; soft-delete with 24h recovery window |
| `forge.fs.rename` | T2 | 5min | Day 16 | Logs both source and target |

### Shell

| Capability | Risk | Default TTL | Added | Notes |
|-----------|------|-------------|-------|-------|
| `forge.shell.exec` | T2 | 2min | Day 2 | Allowlist of commands; sandboxed; output schema enforced |
| `forge.shell.exec.dry_run` | T1 | 5min | Day 9 | Always permitted; never executes, only simulates |

### Git

| Capability | Risk | Default TTL | Added | Notes |
|-----------|------|-------------|-------|-------|
| `forge.git.status` | T1 | 5min | Day 2 | Read-only |
| `forge.git.log` | T1 | 5min | Day 2 | Read-only |
| `forge.git.diff` | T1 | 5min | Day 2 | Read-only |
| `forge.git.commit` | T2 | 5min | Day 4 | Local only; does not push |
| `forge.git.push` | T3 | 2min | Day 8 | Per-action consent; scope is branch + remote |
| `forge.git.pull` | T2 | 5min | Day 6 | Fast-forward only by default; merge requires elevated consent |

### Web

| Capability | Risk | Default TTL | Added | Notes |
|-----------|------|-------------|-------|-------|
| `forge.web.fetch` | T1 | 5min | Day 3 | All output enters Atlas Q tier |
| `forge.web.extract` | T1 | 5min | Day 3 | Content extraction; entropy-scanned |
| `forge.web.search` | T1 | 5min | Day 7 | Search engine query; results enter Q tier |

### Atlas (memory)

| Capability | Risk | Default TTL | Added | Notes |
|-----------|------|-------------|-------|-------|
| `atlas.query` | T1 | 10min | Day 1 | Read; returns evidence with provenance |
| `atlas.query.lineage` | T1 | 10min | Day 6 | "What evidence supports belief X?" |
| `atlas.write.quarantine` | T1 | 10min | Day 3 | Writes to Q tier only |
| `atlas.promote` | T2 | 2min | Day 6 | Promote Q → A; requires corroboration |
| `atlas.contradiction_sweep` | T1 | 10min | Day 30 | Scan for conflicting facts |
| `atlas.source_audit` | T1 | 30min | Day 44 | Source-age and corroboration audit |
| `atlas.bulk_revoke` | T4 | 1min | Day 47 | Bulk revoke by source; per-action consent |

### Email

| Capability | Risk | Default TTL | Added | Notes |
|-----------|------|-------------|-------|-------|
| `forge.email.draft` | T1 | 30min | Day 20 | Draft only; never sends |
| `forge.email.send` | T3 | 1min | Day 20 | Per-action consent; recipients displayed |

### Deploy

| Capability | Risk | Default TTL | Added | Notes |
|-----------|------|-------------|-------|-------|
| `forge.deploy.dry_run` | T1 | 5min | Day 35 | Diff preview only |
| `forge.deploy.execute` | T4 | 1min | Day 35 | Per-action consent + 2FA |
| `forge.health.check` | T1 | 5min | Day 35 | Post-deploy verification |

### Finance

| Capability | Risk | Default TTL | Added | Notes |
|-----------|------|-------------|-------|-------|
| `forge.finance.preview` | T1 | 10min | Day 40 | Preview only; no actual transaction |
| `forge.finance.execute` | T5 | 30sec | Day 40 | Per-action consent + 2FA + cooldown |

### Registry meta

| Capability | Risk | Default TTL | Added | Notes |
|-----------|------|-------------|-------|-------|
| `forge.registry.audit` | T1 | 30min | Day 56 | Self-inspection of registry |

---

## Growth trajectory

| Phase | Capabilities added | Cumulative |
|-------|-------------------|-----------|
| I (Days 1–7) | 11 | 11 |
| II (Days 8–21) | 8 | 19 |
| III (Days 22–35) | 6 | 25 |
| IV (Days 36–49) | 4 | 29 |
| V (Days 50–60) | 2 | 31 |

**Operator note:** Growth rate slows by design. The first phase is dominated by adding baseline capabilities. Later phases focus on refinement, not expansion. A capability registry that keeps growing linearly is capability sprawl (doctrine anti-pattern).

---

## Removed / deprecated capabilities

*(none yet — track here if any are removed)*

---

## Capabilities considered but rejected

| Proposed | Rejected on | Reason |
|---------|-------------|--------|
| `forge.shell.exec.unsanitized` | Day 17 | Would bypass allowlist; violates I9 |
| `forge.atlas.direct_write` | Day 22 | Would bypass quarantine; violates I6 |
| `forge.deploy.auto` | Day 38 | Removes consent gate; violates I8 |
| `forge.vault.read_token` | Day 41 | Would expose raw secret to Hermes; violates P4, I3 |
| `forge.email.send.bulk` | Day 46 | No clear scoping; consent fatigue risk |

These are documented to prevent re-proposal six months from now without context.

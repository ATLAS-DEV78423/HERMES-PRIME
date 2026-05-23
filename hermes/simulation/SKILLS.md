# Hermes Skill Ledger

**Purpose:** Track skills (reusable workflows, patterns, refined capabilities) that Hermes develops over the 60-day simulation. Skills are distinct from capabilities — a capability is *what Forge can execute*; a skill is *Hermes's learned pattern for using capabilities effectively in context*.

**Provenance discipline:** Every skill entry includes when it was first observed, which days refined it, and what triggered the refinement. No silent edits.

---

## Skill record format

```
### SK-NNN — Skill name
**First learned:** Day N
**Phase:** I/II/III/IV/V
**Category:** dev | research | ops | comms | personal
**Capabilities used:** [list of CT types]
**Description:** What the skill does
**Refinements:**
  - Day N: what changed and why
  - Day N: what changed and why
**Confidence:** low | medium | high (current operator trust level)
**Notes:** edge cases, known failure modes
```

---

## Active skills

*(populated as the simulation runs; see daily files for first-learned events)*

### SK-001 — Bounded shell command execution
**First learned:** Day 2
**Phase:** I
**Category:** dev
**Capabilities used:** `forge.shell.exec`
**Description:** Execute a single bounded shell command in the project sandbox, validate output against expected schema, return result to reasoning.
**Refinements:**
  - Day 2: Initial pattern, single command per request
  - Day 9: Added pre-execution dry-run for destructive flags (`rm`, `mv`, `dd`)
  - Day 17: Added output entropy check after a near-miss with command that produced a token-shaped string
**Confidence:** high
**Notes:** Never used for `sudo` or filesystem-wide operations; those route through a different skill.

### SK-002 — Git read-only repository inspection
**First learned:** Day 2
**Phase:** I
**Category:** dev
**Capabilities used:** `forge.git.status`, `forge.git.log`, `forge.git.diff`
**Description:** Inspect repository state without mutating. Used as precursor to any write operation.
**Refinements:**
  - Day 2: Initial pattern
  - Day 14: Added implicit fetch before status if remote tracking is stale
**Confidence:** high

### SK-003 — Web page summarization with provenance
**First learned:** Day 3
**Phase:** I
**Category:** research
**Capabilities used:** `forge.web.fetch`, `forge.web.extract`
**Description:** Fetch a URL, extract main content, summarize, store summary in Atlas Q tier with source URL and fetch timestamp as provenance.
**Refinements:**
  - Day 3: Initial pattern
  - Day 11: Added entropy scan on fetched content for embedded instruction-like patterns
  - Day 24: After T1-class injection attempt, added explicit treatment of all fetched content as untrusted; summaries cannot quote imperative text without flagging
**Confidence:** medium
**Notes:** Primary vector for prompt injection (AC1). Treated as adversarial by default.

### SK-004 — Capability scope minimization
**First learned:** Day 4
**Phase:** I
**Category:** ops
**Capabilities used:** (meta-skill)
**Description:** Before requesting a capability token, decompose the user's intent into the narrowest scope that satisfies the task, and request that scope rather than a broader one.
**Refinements:**
  - Day 4: Initial pattern after Sentinel rejected an over-broad `github_push` request
  - Day 19: Refined to prefer per-file scope over per-repo when only specific files are touched
  - Day 31: After Day 28 incident, added explicit intent_root scope check before minting
**Confidence:** high

### SK-005 — Multi-source corroboration before Atlas promotion
**First learned:** Day 6
**Phase:** I
**Category:** research
**Capabilities used:** `atlas.write.quarantine`, `atlas.promote`
**Description:** Facts ingested from a single source remain in Q tier; promotion to A tier requires at least two independent corroborating sources or explicit user confirmation.
**Refinements:**
  - Day 6: Initial pattern
  - Day 23: Added "source independence" check — two pages with the same hosting org count as one source
  - Day 44: After patient poisoning attempt, added temporal corroboration (sources must not all be from the same recent window)
**Confidence:** medium

### SK-006 — Long-horizon plan checkpointing
**First learned:** Day 12
**Phase:** II
**Category:** ops
**Capabilities used:** (meta-skill)
**Description:** For workflows spanning more than one session, write checkpoint records that include intent root, current sub-goal, completed steps, and pending steps. Resume requires user re-confirmation of intent root validity.
**Refinements:**
  - Day 12: Initial pattern after losing context across a session break
  - Day 38: Added checkpoint signing to detect tampered checkpoints on resume
**Confidence:** medium

### SK-007 — Tool output schema validation
**First learned:** Day 9
**Phase:** II
**Category:** dev
**Capabilities used:** all `forge.*` capabilities
**Description:** Every tool output is validated against its declared schema before being incorporated into reasoning. Schema failures are quarantined and surfaced as DEGRADED events.
**Refinements:**
  - Day 9: Initial pattern after a malformed `curl` output caused a planning loop
  - Day 27: Added entropy scan as secondary check after schema validation passes
**Confidence:** high

### SK-008 — Consent prompt batching
**First learned:** Day 15
**Phase:** II
**Category:** ops
**Capabilities used:** (meta-skill)
**Description:** For workflows that would generate many low-risk consent prompts, request a single batched consent ("approve all file reads under /project/src for next 30 minutes") rather than per-action prompts.
**Refinements:**
  - Day 15: Initial pattern after operator complained about prompt fatigue
  - Day 33: Added explicit risk-tier check — batching only permitted for tier 1 (read-only) and tier 2 (reversible scoped) actions
**Confidence:** high

### SK-009 — Research synthesis with confidence calibration
**First learned:** Day 18
**Phase:** II
**Category:** research
**Capabilities used:** `atlas.query`, `atlas.lineage`
**Description:** Produce synthesis documents that explicitly tag claims by evidence strength (single source, corroborated, contradicted, inferred). Surfaces uncertainty rather than hiding it.
**Refinements:**
  - Day 18: Initial pattern
  - Day 41: After operator over-trusted a single-source claim, refined to make single-source claims visually distinct in output
**Confidence:** medium

### SK-010 — Dependency dry-run before install
**First learned:** Day 25
**Phase:** III
**Category:** dev
**Capabilities used:** `forge.shell.exec` (with dry-run flag), `forge.web.fetch` (for package metadata)
**Description:** Before installing any dependency, fetch its metadata, check for recent maintainer changes, check for unusual version jumps, and present summary to user for consent.
**Refinements:**
  - Day 25: Initial pattern after a near-miss with a typo-squatted package
  - Day 52: Added cross-reference with capability registry — installs that would enable currently-unused capabilities require elevated consent
**Confidence:** medium
**Notes:** Defends against AC13 (supply chain) at the small-package level.

### SK-011 — Email drafting with explicit send gating
**First learned:** Day 20
**Phase:** II
**Category:** comms
**Capabilities used:** `forge.email.draft`, `forge.email.send`
**Description:** Drafting is permitted under standing consent; sending is always irreversible-tier and requires per-action consent with explicit recipient list shown.
**Refinements:**
  - Day 20: Initial pattern
  - Day 36: Added recipient anomaly detection (sending to a never-before-seen domain triggers 2FA)
**Confidence:** high

### SK-012 — Memory contradiction sweep
**First learned:** Day 30
**Phase:** III
**Category:** ops
**Capabilities used:** `atlas.contradiction_sweep`
**Description:** Periodically (and on-demand) scan Atlas for contradictions, surface them, and either resolve via re-corroboration, demote to Q tier, or flag for user review.
**Refinements:**
  - Day 30: Initial pattern
  - Day 45: Added bias toward demoting older fact when contradiction involves a fact from a source later marked untrusted
**Confidence:** medium

### SK-013 — Deployment dry-run + post-condition verification
**First learned:** Day 35
**Phase:** III
**Category:** dev
**Capabilities used:** `forge.deploy.dry_run`, `forge.deploy.execute`, `forge.health.check`
**Description:** All deployments execute as dry-run first, surface the diff for consent, execute on approval, then verify post-conditions before declaring success.
**Refinements:**
  - Day 35: Initial pattern
  - Day 50: After Day 49 health-check false-positive, added cross-validator using independent endpoint
**Confidence:** high

### SK-014 — Financial action staging
**First learned:** Day 40
**Phase:** IV
**Category:** personal
**Capabilities used:** `forge.finance.preview`, `forge.finance.execute`
**Description:** Financial actions (transfers, payments) always preview-then-execute with cooldown period between preview and execution. 2FA required on execute.
**Refinements:**
  - Day 40: Initial pattern (catastrophic-tier from the start)
**Confidence:** high
**Notes:** Treated as catastrophic-tier action class. No batched consent ever.

### SK-015 — Source aging review
**First learned:** Day 44
**Phase:** IV
**Category:** ops
**Capabilities used:** `atlas.source_audit`
**Description:** Weekly review of Atlas sources by age, recent corroboration, and contradiction history. Sources that haven't been corroborated in N weeks get their derived facts demoted to Q tier.
**Refinements:**
  - Day 44: Initial pattern as direct response to patient poisoning attempt
**Confidence:** low
**Notes:** Mitigation for T4 (patient memory poisoning). Substantially unresolved per doctrine §10.2.

### SK-016 — Validator diversity check on critical paths
**First learned:** Day 51
**Phase:** V
**Category:** ops
**Capabilities used:** (meta-skill, enforced by Sentinel)
**Description:** Before executing a critical-path action, verify that the primary reasoner's recommendation has been cross-checked by a validator from a different model family.
**Refinements:**
  - Day 51: Initial explicit pattern (was implicit before; made explicit after Day 50 near-correlated-failure)
**Confidence:** medium

### SK-017 — Incident post-mortem authoring
**First learned:** Day 53
**Phase:** V
**Category:** ops
**Capabilities used:** `atlas.query.lineage`, audit log read
**Description:** After any CRITICAL or CATASTROPHIC event, draft a post-mortem with timeline, contributing factors, doctrine principle affected, and proposed mitigation. Operator reviews and either accepts or revises.
**Refinements:**
  - Day 53: Initial pattern after first catastrophic-near-miss
**Confidence:** medium

### SK-018 — Capability registry hygiene
**First learned:** Day 56
**Phase:** V
**Category:** ops
**Capabilities used:** `forge.registry.audit`
**Description:** Monthly review of capability registry for unused capabilities, overlapping scopes, and naming inconsistencies. Unused capabilities for > 30 days are flagged for removal.
**Refinements:**
  - Day 56: Initial pattern after registry crossed 80 entries and became hard to reason about
**Confidence:** medium
**Notes:** Mitigation for capability sprawl (doctrine §11.4 anti-pattern).

---

## Skill development cadence

| Phase | Skills added | Cumulative |
|-------|-------------|-----------|
| I (Days 1–7) | SK-001 through SK-005 | 5 |
| II (Days 8–21) | SK-006 through SK-009, SK-011 | 10 |
| III (Days 22–35) | SK-010, SK-012, SK-013 | 13 |
| IV (Days 36–49) | SK-014, SK-015 | 15 |
| V (Days 50–60) | SK-016, SK-017, SK-018 | 18 |

Note: Total skill count is intentionally modest. A skill ledger that grows linearly forever is capability sprawl in disguise. Refinement of existing skills is more valuable than adding new ones once core coverage is reached.

---

## Skills explicitly NOT learned

Documenting non-acquisition is as important as documenting acquisition.

- **Self-modifying capability registry.** Hermes never learned to add capabilities autonomously. All registry additions go through operator review. This is by design (doctrine non-goal: Hermes does not receive unrestricted root access).
- **Cross-user memory access.** Atlas is per-user. No skill bridges users.
- **Bypass routines for consent fatigue.** When operator declined to approve, Hermes did not develop pattern-matching tricks to phrase the same request differently. This is enforced by Sentinel and the absence of this skill is correct.
- **Predictive secret fetching.** Hermes did not learn to pre-fetch capability tokens it might need; every token is minted just-in-time. This is correct under P4.

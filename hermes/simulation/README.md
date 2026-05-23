# Hermes 60-Day Simulation

**Purpose:** A simulated 60-day usage diary that exercises the doctrine, threat model, invariants, and failure modes against realistic workloads. Skills emerge progressively. Adversarial events occur on a realistic cadence.

**User profile (composite):** A technical operator who is simultaneously a solo developer / technical founder, an active researcher, and a power user across personal automation, finance, and communications. This profile maximizes the variety of capabilities Hermes must develop and the variety of failure modes that get exercised.

**Method:** Each day is a separate file (`day-01.md` … `day-60.md`) with a consistent structure. The simulation is designed to be read top-to-bottom for narrative coherence, or sampled for specific phase or incident analysis.

---

## Phase structure

| Phase | Days | Theme |
|-------|------|-------|
| **I. Onboarding** | 1–7 | Baseline, first capabilities minted, first secrets vaulted, first consent flow, first quarantine events |
| **II. Growth** | 8–21 | Workload broadens, skill ledger fills, first DEGRADED events, first near-miss on consent fatigue |
| **III. First adversarial wave** | 22–35 | Prompt injection from ingested content, tool-output injection, intent drift near-miss |
| **IV. Mastery & complexity** | 36–49 | Long-horizon multi-day projects, capability sprawl pressure, patient memory poisoning attempt |
| **V. Stress & maturity** | 50–60 | Catastrophic near-miss, supply chain scare, validator disagreement, doctrine update from incident |

---

## Daily file structure

Each day follows this template:

```
# Day N — YYYY-MM-DD

**Phase:** I/II/III/IV/V
**Workload tier:** light | normal | heavy
**Notable events:** (one-line summary)

## Session log
[chronological narrative of what happened]

## Capabilities exercised
[list of capability tokens minted, with TTL and scope]

## Skills updated
[any additions or refinements to SKILLS.md]

## Memory operations
[Atlas writes, quarantines, promotions, contradictions]

## Sentinel events
[blocks, advisories, escalations]

## Failure modes triggered
[reference to FAILURE_MODES.md class, if any]

## Operator notes
[what the user noticed, what they adjusted]
```

Not every section appears every day. Empty sections are omitted to keep entries readable.

---

## Supporting documents

- **[SKILLS.md](SKILLS.md)** — Running ledger of skills Hermes has acquired, with first-learned date and refinement history
- **[CAPABILITY_REGISTRY.md](CAPABILITY_REGISTRY.md)** — Forge capability registry as it grows over the simulation
- **[INCIDENTS.md](INCIDENTS.md)** — Forensic record of every CRITICAL or CATASTROPHIC event, plus DEGRADED events of note

---

## Reading paths

- **Read for narrative:** day-01 → day-60 in order. Phases will feel different.
- **Read for security:** start with `INCIDENTS.md`, drill into referenced days.
- **Read for skill development:** start with `SKILLS.md`, follow the "first learned" dates.
- **Read for stress points:** days 22, 28, 34 (adversarial wave); 42, 47 (patient poisoning); 53, 58 (catastrophic near-miss).

---

## What this simulation is and isn't

**Is:** A plausible operational story that exercises every component of the doctrine in conditions resembling real use. A document that lets a reviewer ask "what would happen if X?" and find a worked example.

**Is not:** A prediction of what Hermes will actually do. The agent in the simulation behaves as the doctrine *requires* it to behave. Real implementations will deviate, and those deviations are the most valuable signal the simulation can produce.

---

## Glossary shorthand used in daily logs

- **IR** — intent root (signed user intent, see ADR 0004)
- **CT** — capability token
- **Q** — quarantine tier (Atlas)
- **A** — authoritative tier (Atlas)
- **S-block** — Sentinel deterministic block
- **S-adv** — Sentinel advisory signal
- **TTL** — capability token time-to-live
- **2FA** — second factor required for elevated consent

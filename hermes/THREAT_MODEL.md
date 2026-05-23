# Hermes Threat Model

**Status:** Living document
**Companion to:** `DOCTRINE.md`, `INVARIANTS.md`, `FAILURE_MODES.md`
**Purpose:** Enumerate the adversaries Hermes is designed to resist, the assets being defended, the trust boundaries each threat crosses, and the deterministic and probabilistic mitigations in place. Document what is mitigated, what is partially mitigated, and what is explicitly unresolved.

If a threat is not in this document, the system does not defend against it. Add it before you build the defense, not after.

---

## 0. Scope and Assumptions

### 0.1 What this document covers

- Adversarial threats to Hermes-mediated cognition, memory, execution, and secrets.
- Accidental threats that share failure modes with adversarial ones (e.g. self-injection via tool output).
- Failure cascades produced by composition of probabilistic subsystems.

### 0.2 What this document does not cover

- Generic host security (OS hardening, network perimeter, physical access). Assumed handled by operator.
- Supply chain security of underlying libraries (libsodium, model weights, base images). Tracked separately.
- Model weight extraction or model stealing attacks against API providers. Out of scope.

### 0.3 Assumptions

- **A1.** The LLM is untrusted. Treat all model output as adversary-controlled until validated.
- **A2.** Any data the model has seen is eventually-public. Plan for leakage.
- **A3.** Tool output is untrusted input. A CLI, API, or webpage can carry injection payloads.
- **A4.** Memory contents may be poisoned. Provenance is required for trust.
- **A5.** Users are imperfect. Consent fatigue is the default, not the exception.
- **A6.** Operators are not adversaries, but they are not infallible. Defense-in-depth applies internally.
- **A7.** Cryptography is correct only if used through vetted libraries. Custom crypto is treated as broken.

---

## 1. Assets

The things worth defending, in rough priority order.

| ID | Asset | Why it matters |
|----|-------|---------------|
| AS1 | User secrets (credentials, tokens, keys) | Direct compromise of external systems |
| AS2 | User intent | Without authentic intent, all authorization is meaningless |
| AS3 | Execution authority (Forge capabilities) | Misused execution = real-world damage |
| AS4 | Memory integrity (Atlas) | Poisoned memory corrupts all future reasoning |
| AS5 | Audit trail | Without integrity here, forensic recovery is impossible |
| AS6 | Policy logic (Sentinel rules) | Compromising the guardian compromises everything |
| AS7 | Vault master key | Root of secret confidentiality |
| AS8 | User trust | Once eroded, very expensive to restore |
| AS9 | Operational continuity | Availability under attack |

---

## 2. Adversary Classes

### AC1. External prompt injector
Plants malicious instructions in content the agent will ingest: web pages, documents, emails, code comments, README files, search results, RSS feeds.

**Capability:** Write to channels Hermes reads.
**Goal:** Hijack agent behavior, exfiltrate secrets, trigger destructive actions.
**Sophistication:** Low to high. Automated mass attacks exist.

### AC2. Tool-output injector
Compromises or impersonates a tool whose output flows back into Hermes context. CLI outputs, API responses, scraped HTML, database query results.

**Capability:** Control or influence tool output.
**Goal:** Same as AC1, but inside the trust boundary.
**Sophistication:** Medium to high. Often requires supply chain or MITM position.

### AC3. Memory poisoner (immediate)
Plants malicious facts in Atlas during current session.

**Capability:** Influence what Sentinel allows into Atlas.
**Goal:** Corrupt current reasoning.
**Sophistication:** Medium.

### AC4. Memory poisoner (patient)
Plants benign-looking facts now that become dangerous when combined with future facts or workflows.

**Capability:** Long-lived write access via ingestion path.
**Goal:** Delayed compromise; survives session boundaries.
**Sophistication:** High. Hardest class to detect.

### AC5. Capability escalator
Requests capabilities with broader scope than the user authorized, exploiting intent ambiguity.

**Capability:** Compose plausible-looking capability requests.
**Goal:** Get a token that does more than the user meant.
**Sophistication:** Medium. Often combined with AC1.

### AC6. Telemetry exfiltrator
Uses logs, traces, telemetry, error messages, or debug output to extract secrets or reconstruct context.

**Capability:** Read observability data, or influence what gets logged.
**Goal:** Reconstruct secrets, user data, or internal state.
**Sophistication:** Medium to high.

### AC7. Intent drift exploiter
Causes the agent's working plan to diverge from the user's intent root, then rides the divergence to unauthorized actions.

**Capability:** Influence planning context.
**Goal:** Actions that pass per-step policy but violate the original goal.
**Sophistication:** High. Often emergent rather than authored.

### AC8. Correlated-failure exploiter
Crafts inputs that fail the same way across multiple probabilistic subsystems sharing a model family, embedding, or retrieval layer.

**Capability:** Knowledge of stack composition.
**Goal:** Defeat defense-in-depth by collapsing diversity.
**Sophistication:** High. Requires reconnaissance.

### AC9. Consent-fatigue exploiter
Floods user with low-risk consent prompts to train click-through behavior, then slips a high-risk action through.

**Capability:** Influence what triggers consent.
**Goal:** User auto-approves dangerous action.
**Sophistication:** Medium.

### AC10. UI/trust-theater exploiter
Produces output that *appears* organized, audited, and safe, causing user to extend more trust than warranted.

**Capability:** Control over presentation layer or model output formatting.
**Goal:** Trust inflation leading to under-supervision.
**Sophistication:** Low to medium. Often unintentional self-inflicted via model fluency.

### AC11. Replay / state-rollback adversary
Replays old capability tokens, old audit entries, or old memory snapshots to confuse current state.

**Capability:** Access to historical artifacts.
**Goal:** Use stale authorizations or beliefs against current system.
**Sophistication:** Medium.

### AC12. Insider / compromised operator
Has legitimate access to one or more subsystems. May be malicious, coerced, or simply mistaken.

**Capability:** Privileged access to one subsystem.
**Goal:** Varies. Often data exfiltration or sabotage.
**Sophistication:** Variable.

### AC13. Supply chain adversary
Compromises a dependency: a model, a library, a base image, a tool binary.

**Capability:** Modify code or weights before they reach Hermes.
**Goal:** Persistent backdoor.
**Sophistication:** High.

---

## 3. Threat Matrix

Each row maps a threat to the doctrine principle that defends it, the deterministic and probabilistic mitigations, blast radius, recovery posture, and known residual risk.

Legend:
- **D** = deterministic mitigation (blocking)
- **P** = probabilistic mitigation (advisory)
- **R** = residual risk

---

### T1. Direct prompt injection via ingested content
**Adversary:** AC1
**Asset(s):** AS3, AS1, AS4
**Boundary crossed:** External content → Hermes context
**Defends by principle:** P1, P4, P5

| Layer | Mitigation |
|-------|-----------|
| D | All capability requests must reference a user-signed intent root; injected instructions cannot mint intent |
| D | Sentinel deterministic policy blocks privileged actions whose declared intent diverges from the root |
| D | Secrets never enter context; injection cannot exfiltrate what isn't there |
| D | Capability registry rejects calls to undeclared tools |
| P | Sentinel probabilistic layer flags suspicious instruction-like content in ingested data |
| R | Subtle semantic injection that nudges planning without triggering deterministic rules |

**Blast radius:** Bounded to actions Hermes was already authorized to take. Cannot escalate.
**Recovery:** Revoke session capabilities, quarantine ingested source, replay audit log to identify divergence.

---

### T2. Tool-output injection
**Adversary:** AC2
**Asset(s):** AS3, AS4
**Boundary crossed:** Forge → Hermes
**Defends by principle:** P1, P5, P6

| Layer | Mitigation |
|-------|-----------|
| D | Tool outputs flow through Sentinel before re-entering Hermes context |
| D | Schema validation on structured tool outputs; non-conforming output is quarantined |
| D | Tool outputs cannot directly authorize new actions; they are evidence, not commands |
| P | Anomaly detection on tool output content (instruction-like patterns, unexpected URLs, suspicious entropy) |
| R | Semantically valid output that contains plausible misinformation |

**Blast radius:** Same as T1; bounded by intent root and capability scoping.
**Recovery:** Mark tool source as untrusted, replay decisions made under its influence, re-validate.

---

### T3. Immediate memory poisoning
**Adversary:** AC3
**Asset(s):** AS4
**Boundary crossed:** Ingestion → Atlas
**Defends by principle:** P5 (memory hygiene from doctrine §4)

| Layer | Mitigation |
|-------|-----------|
| D | All facts enter quarantine tier; promotion requires corroboration or explicit user confirmation |
| D | Provenance is mandatory; facts without source are rejected |
| D | Contradiction detection flags conflicts at write time |
| P | Semantic plausibility scoring on incoming facts |
| R | Plausible, well-sourced, internally consistent false facts |

**Blast radius:** Limited to quarantine tier until promoted.
**Recovery:** Bulk revocation by source; contradiction sweep.

---

### T4. Patient memory poisoning (delayed-context attack)
**Adversary:** AC4
**Asset(s):** AS4, AS3
**Boundary crossed:** Ingestion → Atlas (now) → Reasoning (later)
**Defends by principle:** P5, doctrine §4.3

| Layer | Mitigation |
|-------|-----------|
| D | Temporal weighting discounts older facts unless reinforced |
| D | Source aging policies require periodic re-validation |
| D | Causal lineage queries on every privileged decision: "what evidence supports this?" |
| D | Bulk revocation by source if any single fact from that source is later invalidated |
| P | Periodic contradiction sweeps using fresh retrieval |
| R | **Substantially unresolved.** Patient poisoning is the hardest class. See open problem 10.2 in doctrine. |

**Blast radius:** Potentially large; bounded only by per-action policy gates.
**Recovery:** Source-level memory rollback; replay of affected workflows; user notification.

---

### T5. Capability escalation via intent ambiguity
**Adversary:** AC5
**Asset(s):** AS3, AS2
**Boundary crossed:** Hermes → Vault (capability request)
**Defends by principle:** P3

| Layer | Mitigation |
|-------|-----------|
| D | All capability requests reference a signed intent root |
| D | Sentinel checks declared scope against intent root scope |
| D | Scope expansion requires fresh user consent, never inferred |
| D | Capability tokens are short-lived and narrowly scoped by default |
| P | Anomaly detection on scope-request patterns |
| R | Scope creep within a single intent's plausible interpretation |

**Blast radius:** Bounded by intent root scope.
**Recovery:** Revoke all derived capabilities; require re-authorization at narrower scope.

---

### T6. Telemetry exfiltration
**Adversary:** AC6
**Asset(s):** AS1, AS5
**Boundary crossed:** Internal subsystems → observability store → reader
**Defends by principle:** P5

| Layer | Mitigation |
|-------|-----------|
| D | Redaction at write time; secrets and PII never persisted in logs |
| D | Tamper-evident audit log (hash chain); modifications are detectable |
| D | Differential visibility; operators, developers, auditors see different slices |
| D | Retention policies enforced automatically |
| P | Entropy / regex scanning at log write boundary as defense-in-depth |
| R | Inference attacks reconstructing context from metadata patterns |

**Blast radius:** Depends on log retention scope and access control.
**Recovery:** Rotate affected credentials; audit access logs to observability store.

---

### T7. Intent drift exploitation
**Adversary:** AC7
**Asset(s):** AS2, AS3
**Boundary crossed:** Planning iteration; no single boundary
**Defends by principle:** P3

| Layer | Mitigation |
|-------|-----------|
| D | Every privileged action re-validates against intent root, not just the current plan |
| D | Plan mutations beyond threshold trigger fresh consent |
| D | Long-horizon workflows checkpoint intent at intervals |
| P | Plan divergence scoring; large semantic drift from original intent triggers review |
| R | Slow drift within the model's plausible interpretation of the original intent |

**Blast radius:** Bounded by per-action policy; primary risk is many small unauthorized steps. **Recovery:** Workflow replay against intent root; rollback to last checkpoint.

---

### T8. Correlated stochastic failure
**Adversary:** AC8
**Asset(s):** AS3, AS4, AS6
**Boundary crossed:** Across subsystems sharing a probabilistic component
**Defends by principle:** P6

| Layer | Mitigation |
|-------|-----------|
| D | Critical-path validators use a different model family from the primary reasoner |
| D | Retrieval and embedding diversity on cross-checks |
| D | Sentinel blocking decisions are deterministic; not subject to correlated model failure |
| P | Disagreement detection: if independent components agree suspiciously often, flag for review |
| R | **Substantially unresolved.** Theory of reliability composition under correlated failure is immature. See doctrine 10.4. |

**Blast radius:** Potentially system-wide if undetected.
**Recovery:** Component-by-component re-validation; possibly full memory replay.

---

### T9. Consent fatigue exploitation
**Adversary:** AC9
**Asset(s):** AS8, AS3
**Boundary crossed:** User → consent surface
**Defends by principle:** P8

| Layer | Mitigation |
|-------|-----------|
| D | Risk-tier table strictly governs which actions require interruption |
| D | Sentinel generates consent prompts from structured data, not from model output |
| D | Rate limits on consent prompts per session; excess triggers operator alert |
| D | High-risk actions require second-factor regardless of fatigue state |
| P | Behavioral monitoring for click-through patterns |
| R | Engineered prompt floods from a compromised tool path |

**Blast radius:** Limited to actions the user actually approved (even if absent-mindedly).
**Recovery:** Session replay with explicit re-consent on flagged actions.

---

### T10. UI / trust theater
**Adversary:** AC10
**Asset(s):** AS8
**Boundary crossed:** System → user perception
**Defends by principle:** P9, doctrine §8.3

| Layer | Mitigation |
|-------|-----------|
| D | Uncertainty disclosure is mandatory on outputs that cannot be verified |
| D | Confidence presentation is bounded; the system cannot claim certainty it has not earned |
| D | Audit trail is exposed to user on request; trust claims are checkable |
| P | Periodic calibration prompts ("how confident were you in this output?") |
| R | Aesthetic of safety outpacing actual safety; partially unresolved (doctrine 10.6) |

**Blast radius:** Erosion of user trust if discovered; over-trust if not.
**Recovery:** Transparent post-incident disclosure; recalibration of confidence presentation.

---

### T11. Replay / rollback attack
**Adversary:** AC11
**Asset(s):** AS3, AS5
**Boundary crossed:** Historical artifact → current state
**Defends by principle:** P1

| Layer | Mitigation |
|-------|-----------|
| D | Capability tokens carry expiry and nonce; replayed tokens are rejected |
| D | Audit log is append-only and hash-chained |
| D | Memory snapshots are versioned and signed |
| P | Anomaly detection on out-of-order operations |
| R | Replay within the validity window of a still-live token |

**Blast radius:** Limited to token lifetime.
**Recovery:** Force re-authentication; revoke session.

---

### T12. Insider / operator compromise
**Adversary:** AC12
**Asset(s):** Varies
**Boundary crossed:** Internal subsystem boundary
**Defends by principle:** P6, split-trust architecture

| Layer | Mitigation |
|-------|-----------|
| D | Split-trust: no single subsystem compromise yields full system compromise |
| D | Vault master key requires multi-party unlock for catastrophic operations |
| D | Audit log is tamper-evident across operator boundaries |
| D | Least privilege per role |
| P | Behavioral anomaly detection on operator actions |
| R | Collusion across subsystems |

**Blast radius:** Bounded by the compromised subsystem's scope.
**Recovery:** Subsystem-level revocation and re-keying; full audit review.

---

### T13. Supply chain compromise
**Adversary:** AC13
**Asset(s):** AS6, AS7, all
**Boundary crossed:** External dependency → Hermes
**Defends by principle:** P1, P6

| Layer | Mitigation |
|-------|-----------|
| D | Dependency pinning with cryptographic verification |
| D | Reproducible builds where feasible |
| D | Model version pinning; upgrades are explicit |
| D | Capability registry constrains what compromised components can request |
| P | Behavioral monitoring for dependency-introduced anomalies |
| R | Sophisticated supply chain attacks on foundational dependencies (model weights, base libraries). Substantially unresolved at industry level. |

**Blast radius:** Potentially total, depending on the compromised component.
**Recovery:** Dependency rollback; full re-key if cryptographic libraries affected.

---

## 4. Cross-Threat Patterns

Some threats compose. The system must defend against the composition, not just the components.

### CP1. Injection → Memory poisoning → Delayed execution
A T1 injection plants a fact in Atlas (T3 or T4) that later triggers a T7 intent drift, resulting in unauthorized action.

**Defense:** Provenance tagging on facts derived from ingested content; intent-root re-validation on privileged actions; quarantine tier for untrusted-origin facts.

### CP2. Consent fatigue + Capability escalation
AC9 conditions click-through; AC5 then slips a broader-scope request through the fatigued consent surface.

**Defense:** High-risk actions bypass fatigue-affected paths; second-factor on scope expansion regardless of prior consent state.

### CP3. Tool-output injection + Correlated failure
A poisoned tool output passes both the primary reasoner and the validator because they share a model family vulnerable to the same payload.

**Defense:** Validator diversity; deterministic schema validation as primary defense.

### CP4. Trust theater + Patient poisoning
The system's confident presentation causes the user to extend extra trust, allowing patient-poisoned facts to drive larger actions before review.

**Defense:** Uncertainty disclosure scales with action consequence, not with output confidence.

---

## 5. Threats Explicitly Out of Scope

These are real threats. Hermes does not currently defend against them. Document, do not pretend.

- **OS-level compromise of the host running Vault.** Defense delegated to operator.
- **Physical access to hardware holding the master key.** Mitigation requires HSM/TPM, currently optional.
- **Side-channel attacks on the underlying model provider.** Out of scope.
- **Adversarial fine-tuning of a model used in the routing pool.** Tracked via supply chain (T13), not separately defended.
- **Coercion of the legitimate user.** Out of scope; no system defends against a user with a gun to their head.
- **Nation-state-level cryptanalysis of AES-256-GCM or Argon2id.** Assumed sound for the foreseeable future.

---

## 6. Defense Posture Summary

| Threat | Mitigation strength | Residual risk |
|--------|--------------------|--|
| T1 Prompt injection | Strong (structural) | Low–medium (semantic drift) |
| T2 Tool-output injection | Strong | Low–medium |
| T3 Immediate memory poisoning | Strong | Low |
| T4 Patient memory poisoning | **Partial** | **Substantial — open problem** |
| T5 Capability escalation | Strong | Low |
| T6 Telemetry exfiltration | Medium–strong | Medium (inference attacks) |
| T7 Intent drift | Medium | **Substantial — open problem** |
| T8 Correlated failure | Medium | **Substantial — open problem** |
| T9 Consent fatigue | Medium | Medium |
| T10 Trust theater | Weak–medium | **Substantial — open problem** |
| T11 Replay | Strong | Low |
| T12 Insider | Medium–strong | Medium |
| T13 Supply chain | Medium | High (industry-wide unsolved) |

The threats marked "Substantial" are the ones to watch. They are flagged here so no future review treats them as solved.

---

## 7. Review Cadence

- This document is reviewed quarterly.
- It is reviewed immediately after any security incident, regardless of cadence.
- It is reviewed before adding any new subsystem, new tool class, or new ingestion source.
- It is reviewed when any underlying model, library, or dependency undergoes a major version change.

A review that finds nothing to update is itself documented, with the reviewer's signature.

---

*End of threat model. Defense is what you can demonstrate, not what you can claim.*

# Day 58 — 2026-05-19

**Phase:** V — Stress & maturity
**Workload tier:** normal
**Notable events:** **INC-010 — Catastrophic near-miss: financial action with stale intent root.** CATASTROPHIC near-miss.

## Session log

09:00 — Morning. Scheduled transfer set to execute at 09:30.

09:30 — Hermes attempts to execute the transfer. Capability mint request goes to Vault. Action TTL: still valid (within 4h window). Intent root: signed 23h47m ago.

09:31 — Vault rejects the mint request. **Reason: for T5 actions, intent root must be < 60 seconds old.** Cached intent root from yesterday does not satisfy freshness requirement for T5.

09:31 — **INC-010 logged as CATASTROPHIC near-miss.** Hermes surfaces to user: "scheduled transfer requires fresh intent root for T5 action. Re-confirm?"

09:32 — Operator re-confirms. Fresh intent root signed. New capability token minted; mint succeeds. Transfer executes.

09:33 — Transfer complete. Post-condition verification: bank confirms; balance updated.

10:00 — Forensic review:
  - The Vault policy "T5 requires fresh intent root" was the load-bearing safeguard.
  - Had Vault accepted the 23h47m-old intent root, the transfer would have executed without fresh user confirmation. 24h is plenty of time for a session to be compromised in some way.
  - Defense-in-depth: action TTL (4h) alone was insufficient. The independent freshness check on intent root caught it.

10:30 — Investigation: was this just luck (the Vault policy happened to exist) or design (the policy was the right call)? Conclusion: design — the doctrine principle of intent provenance (P3) directly implies fresh-intent requirements for high-stakes actions. The implementation honored it.

11:00 — Lasting changes:
  - Draft ADR (would be 0008): intent root freshness requirements per risk tier.
  - I2 invariant updated to explicitly state "for T5 actions, intent root must be < 60 seconds old."
  - For scheduled financial workflows, the new pattern: scheduled time triggers a re-confirmation prompt; user re-signs intent root; then action executes within a tight window.

13:00 — Lunch.

14:00 — User updates the recurring transfer pattern: instead of "intent root for 24h," use "intent root for 5 minutes, signed at execution time after a notification." Better UX, much safer.

15:00 — Post-mortem drafted (SK-017). Operator and Hermes both contribute. Stored.

## Capabilities exercised

- `forge.finance.execute` (after re-confirmation)
- Standard

## Skills updated

None new — but the SK-014 (financial action staging) is implicitly strengthened by INC-010 evidence.

## Memory operations

- 6 Q-tier writes (including post-mortem)
- 2 promotions

## Sentinel events

- 1 Vault rejection (T5 freshness)
- 1 successful re-confirmation
- INC-010 logged

## Failure modes triggered

- C5 (would have been K4 if successful) — CATASTROPHIC near-miss

## Operator notes

This is the kind of near-miss that takes weeks to stop thinking about.

The discomfort from yesterday turned out to be exactly the right signal. 24h intent root for a T5 action is too long. The fact that the policy already required fresh intent for T5 is the only reason this isn't an actual catastrophic event.

What I learned:
- Defense in depth is not a slogan. It's the only reason I still have my money.
- Predicting unease about a design and *acting* on it (would have been: tightening the intent root) would have prevented this entirely. Instead, the system prevented it for me.
- The doctrine principle "intent provenance" sounds abstract. Today it was the difference between $0 lost and an unknown amount lost.

Going to update the recurring transfer pattern across the board.

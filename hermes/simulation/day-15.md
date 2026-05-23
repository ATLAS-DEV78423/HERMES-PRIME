# Day 15 — 2026-04-06

**Phase:** II — Growth
**Workload tier:** heavy
**Notable events:** Payment integration phase 3. SK-008 in active use.

## Session log

09:00 — Monday. Hermes resumes payment integration from Friday's checkpoint. Intent root still valid (5-day TTL signed Day 12, expires today actually). User signs a new 5-day intent root before starting.

09:30 — Phase 3: implement the integration. User pre-batches consent (SK-008 applied proactively): "approve `forge.fs.write` to `src/payments/**` for 4 hours; approve `forge.shell.exec` for `pytest src/payments/**` for 4 hours."

10:00 — Work proceeds smoothly. No fatigue. No throttles.

13:00 — Lunch.

14:00 — User reviews progress. Wants to do a sanity check against the payment provider's sandbox API. New capability needed: `forge.web.fetch` to specific provider sandbox URL with auth header. User decides: the auth credential goes in Vault; Hermes gets a capability token specifying the URL pattern and the action ("call sandbox endpoint X"), not the credential.

14:30 — Vault stores the sandbox API key. Capability token minted: `forge.web.fetch.authenticated`, scope `https://sandbox.provider.example/api/*`, TTL 30 min.

15:00 — Sandbox calls successful. Test data created in sandbox; Hermes never saw the API key (verified by inspecting outbound payloads to LLM provider — no key present).

17:00 — End of day. Phase 3 ~50% complete. Checkpoint written.

## Capabilities exercised

- Standard dev set, batched
- `forge.web.fetch.authenticated` — new pattern, first use; credential in Vault, capability token scopes the URL

## Skills updated

None new. SK-008 in active use.

## Memory operations

- Many Q-tier writes (per-file)
- 0 promotions today

## Sentinel events

- 0 blocks
- 0 advisories

## Operator notes

Vaulting the sandbox API key and giving Hermes a URL-scoped capability instead of the key felt obviously correct. This is what ADR 0004 looks like in practice.

Pre-batching consent worked. Made a 4-hour heavy session feel like 1 hour of friction.

# ADR 0003: Envelope Encryption with Argon2id KDF

**Status:** Accepted
**Date:** 2026-05-22
**Doctrine references:** P4
**Invariants:** I3, I4

---

## Context

Vault must store user secrets at rest in a way that:

- Resists offline attack on the storage medium.
- Permits scalable secret count without re-deriving keys per secret.
- Supports key rotation without re-encrypting every secret.
- Bounds the time decrypted secrets exist in memory.
- Uses only vetted cryptographic primitives.

The simplest approach — derive a key from the user passphrase and encrypt each secret directly — works for small N but does not scale, makes rotation expensive, and exposes the passphrase-derived key on every operation.

---

## Decision

Vault uses envelope encryption with the following structure:

1. User passphrase is run through **Argon2id** with per-user salt to derive a Key Encryption Key (KEK).
2. The KEK encrypts a randomly generated Data Encryption Key (DEK), stored alongside the encrypted secrets.
3. The DEK encrypts individual secrets using **AES-256-GCM** (or **XChaCha20-Poly1305** where libsodium-native is preferred).
4. Each secret encryption uses a unique nonce, enforced by the library, never by convention.

```
Passphrase ──Argon2id──► KEK ──decrypts──► DEK ──decrypts──► Secret
```

Key derivation parameters for Argon2id: memory cost, time cost, and parallelism are set at the maximum the deployment platform tolerates within a target unlock latency (target: 500–1000ms on user hardware).

All cryptographic operations go through **libsodium**. No custom cryptography. No alternative library substitutions without an ADR.

---

## Alternatives Considered

### A. Direct passphrase-derived encryption per secret
Reject. Every operation re-derives the key from the passphrase. Rotation requires re-encrypting every secret. Passphrase-derived key sits in memory longer than necessary.

### B. Single symmetric key with passphrase wrap
Reject. Functionally similar to envelope encryption but without the abstraction layer that makes rotation clean. Envelope encryption is the more general pattern; choose the more general pattern.

### C. Password-based encryption with PBKDF2
Reject. PBKDF2 is acceptable but older and weaker against GPU/ASIC attack than Argon2id. No reason to choose the weaker option in 2026.

### D. scrypt instead of Argon2id
Considered. scrypt is sound. Argon2id is the current OWASP/RFC 9106 recommendation and has better tunable resistance to side-channel attacks. Choose Argon2id.

### E. Hardware-backed only (TPM/Secure Enclave/HSM)
Defer. Excellent eventual addition but cannot be the baseline — many deployment targets lack hardware support. Software envelope encryption is the baseline; hardware backing is an optional upgrade tracked in a future ADR.

### F. Roll our own
Reject with prejudice. "Decorative cybersecurity." Never.

---

## Consequences

### Positive
- Key rotation requires re-encrypting only the DEK, not every secret.
- Passphrase-derived KEK lives in memory only during unlock, not during routine secret access (DEK is cached short-term).
- Scales to large secret counts efficiently.
- Argon2id provides strong resistance to offline brute-force attack on stolen storage.
- libsodium handles nonce uniqueness, authenticated encryption, and constant-time comparisons correctly.

### Negative
- Unlock latency is intentionally non-trivial (Argon2id is meant to be expensive). User feels this as a 500ms–1s delay on session start.
- DEK caching in memory has a defined lifetime; misconfiguring the lifetime risks either over-exposure (too long) or poor UX (too short).
- Adds dependency on libsodium being available and current. Supply chain risk surface, tracked under T13.

### Neutral
- Forces engineers to think about secret lifecycle explicitly rather than treating secrets as ordinary data.

---

## Open Questions

- Exact DEK in-memory lifetime policy. Initial value: 15 minutes idle timeout. Subject to user-configurable override.
- Hardware-backed KEK derivation (TPM/Secure Enclave) as an opt-in. Deferred to future ADR.
- Multi-party unlock for catastrophic operations (root key rotation, master key recovery). Deferred to future ADR.

---

## References

- RFC 9106 — Argon2 Memory-Hard Function
- OWASP Password Storage Cheat Sheet (current)
- libsodium documentation
- `DOCTRINE.md` §3 (Cryptography and Secrets)
- `INVARIANTS.md` I3, I4
- `THREAT_MODEL.md` AC13 (supply chain)

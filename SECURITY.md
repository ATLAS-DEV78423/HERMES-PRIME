# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.2.x   | :white_check_mark: |
| < 0.2   | :x:                |

## Reporting a Vulnerability

Hermes Prime is a governance engine for autonomous AI operations. Security is the top priority.

To report a vulnerability, please email **security@hermes-prime.dev** or open a GitHub Security Advisory at:

https://github.com/ATLAS-DEV78423/HERMES-PRIME/security/advisories/new

You should receive a response within 48 hours. If you don't, follow up via the same channel.

### What to include
- Description of the vulnerability
- Steps to reproduce
- Affected versions
- Any potential impact or exploit scenarios

### Scope
The following areas are in-scope for security reports:
- Sentinel policy engine bypasses
- Capability/authority escalation
- Memory fabric integrity violations
- Credential or secret leakage
- Sandbox escape via Forge

### Out of scope
- Dependency CVEs (report to upstream)
- Theoretical attacks requiring physical access
- Denial of service on non-critical paths

## Disclosure Policy

We follow **Coordinated Vulnerability Disclosure**:
1. Reporter submits finding (private)
2. Team acknowledges within 48h
3. Fix developed and tested
4. Patch released with advisory
5. Public disclosure after 90 days or by mutual agreement

## Security Features

Hermes Prime includes these built-in security mechanisms:
- **Sentinel Core**: 7-layer blocking engine with OPA policy enforcement
- **Capability Vault**: Bounded authority tokens with intent-root scoping
- **Provenance Linker**: Signed attestations for all memory operations
- **Recursion Watchdog**: Depth-limited agent spawning with chain termination
- **Recovery Module**: Safe signal handling and crash-resistant execution

## Recognition

We maintain a Hall of Fame for validated security reports. Contributors will be credited in release notes (unless anonymity is requested).

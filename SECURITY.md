# Security Policy

If you believe you've found a security vulnerability in HERMES-PRIME, please report it promptly by opening an issue labeled "security" or emailing atlas@hermes-prime.dev. Do not include exploit details in public issue trackers.

Responsible disclosure:
- Provide reproduction steps and impact assessment.
- Attach PoC code privately when possible.
- Allow maintainers 90 days to respond and mitigate before public disclosure.

Security contact: atlas@hermes-prime.dev

## Hardening Recommendations
- Run `hermes-prime` under a dedicated least-privilege OS user.
- Restrict network access for hosts running the service; do not expose management APIs to public networks.
- Use hardware-backed key storage for signing keys when available.
- Rotate HMAC secrets and capability tokens regularly.
- Enforce CI checks for static analysis (bandit), linters (`ruff`), and type checks (`mypy`).

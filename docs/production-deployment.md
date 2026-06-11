# Production Deployment Guide

> **Audience:** DevOps engineers, SREs, and operators deploying Hermes-Prime to production.

## Prerequisites

- Python 3.12+ (3.11 and 3.13 also supported per CI matrix)
- Git (for submodule initialization)
- Docker and Docker Compose (for containerized deployment)
- OPA binary (optional but recommended for performance)

## 1. Clone and Initialize Submodules

```bash
git clone https://github.com/ATLAS-DEV78423/HERMES-PRIME.git
cd HERMES-PRIME
git submodule update --init --recursive
```

This initializes all 26 external submodules. The `external/hermes-agent` module is required for the CLI to function. The remaining submodules provide optional backends, miners, and policy engines.

## 2. Set Secrets

Copy the env template and fill in production secrets:

```bash
cp .env.example .env
# Edit .env — change every HERMES_SECRET_* to a random 64-character hex string
# Generate with: openssl rand -hex 32
```

Source the env file before running:

```bash
export $(cat .env | xargs)
```

### Secret Rotation

Secrets are HMAC keys used for signing audit traces, capabilities, intents, and memory entries. To rotate:

1. Update the env var with the new secret
2. Restart all Hermes-Prime processes
3. Old signatures remain verifiable but new signatures use the new key
4. Periodic rotation: every 90 days recommended

## 3. Docker Deployment

### Build the image

```bash
docker build -t hermes-prime:latest .
```

### Run with secrets

```bash
docker run -d \
  --name hermes-prime \
  -v /path/to/workspace:/hermes \
  --env-file .env \
  hermes-prime:latest \
  hermes-prime --workspace /hermes <command>
```

### Docker Compose

Create `docker-compose.yml`:

```yaml
version: "3.9"
services:
  hermes-prime:
    build: .
    volumes:
      - ./workspace:/hermes
      - ./data:/hermes/.hermes-prime
    env_file: .env
    command: ["hermes-prime", "--workspace", "/hermes", "run", "--model", "mistral"]
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 2G
```

## 4. First-time Setup

```bash
# Initialize workspace databases
hermes-prime --workspace /path/to/workspace repair

# Verify everything is healthy
hermes-prime --workspace /path/to/workspace doctor --strict
```

Expected output (healthy):
```
[PASS] Workspace exists and is accessible
[PASS] .hermes-prime layout initialized
[PASS] SQLite stores accessible
[PASS] Policy bundle loaded and compiled
[PASS] Sentinel service responding
[PASS] Trust store operational
```

## 5. Production Configuration

### Workspace Config (`/path/to/workspace/.hermes-prime/config.yaml`):

```yaml
provider: ollama
model: mistral
ollama_url: http://ollama:11434
rate_limit:
  enabled: true
  requests_per_minute: 30.0
  burst_size: 5
  concurrency_limit: 3
```

### Environment variables for production:

| Variable | Required | Default | Description |
|---|---|---|---|
| `HERMES_SECRET_MEMORY_STORE` | Yes | `hermes-prime-memory-store-secret` | Memory store HMAC key |
| `HERMES_SECRET_MEMORY_PROVENANCE` | Yes | `hermes-prime-memory-provenance-secret` | Provenance signing key |
| `HERMES_SECRET_AUTONOMOUS` | Yes | `default-dev-secret` | Autonomous executor signing key |
| `HERMES_SECRET_GOVERNANCE` | Yes | `hermes-prime-governance` | Governance hook signing key |
| `HERMES_SECRET_GOVERNED_AGENT` | Yes | `hermes-prime-governance` | Governed agent signing key |
| `HERMES_SECRET_LEARNING` | Yes | `hermes-prime-learning-secret` | Learning engine signing key |
| `HERMES_SECRET_SENTINEL` | Yes | `default-dev-secret` | Sentinel policy enforcement key |
| `HERMES_SECRET_VAULT` | Yes | `default-dev-secret` | Vault capability signing key |
| `HERMES_SECRET_MINER` | Yes | `default-dev-secret` | Miner attestation key |
| `HERMES_PROVIDER` | No | `""` | Default LLM provider |
| `HERMES_MODEL` | No | `mistral` | Default LLM model |

## 6. Health Checks

### CLI-based:

```bash
hermes-prime doctor --strict --json
```

Returns JSON checks. All checks passing = healthy.

### Docker health check:

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD hermes-prime doctor --strict --json || exit 1
```

## 7. Backup and Restore

### What to back up:

| Path | Contents | Backup frequency |
|---|---|---|
| `workspace/.hermes-prime/trust.db` | Audit traces, intents, capabilities | Daily |
| `workspace/.hermes-prime/memory.db` | SQLite memory store | Daily |
| `workspace/.hermes-prime/profiles/` | Multi-instance profiles | Weekly |
| `~/.hermes/config.yaml` | Global settings | After each change |

### Backup script:

```bash
#!/bin/bash
BACKUP_DIR="/var/backups/hermes-prime/$(date +%Y%m%d)"
mkdir -p "$BACKUP_DIR"
cp /path/to/workspace/.hermes-prime/trust.db "$BACKUP_DIR/"
cp /path/to/workspace/.hermes-prime/memory.db "$BACKUP_DIR/"
echo "Backup complete: $BACKUP_DIR"
```

### Restore:

```bash
hermes-prime repair --force  # reinitializes empty DBs
cp /path/to/backup/trust.db /path/to/workspace/.hermes-prime/
cp /path/to/backup/memory.db /path/to/workspace/.hermes-prime/
```

## 8. Monitoring and Alerting

### Log levels by component:

| Component | Logger name | Level |
|---|---|---|
| Code sandbox | `hermes_prime.agent.tools.code_exec` | WARNING+ |
| Memory backends | `hermes_prime.memory.backends.*` | WARNING+ |
| LLM adapters | `hermes_prime.llm.*` | WARNING+ |
| Vault client | `hermes_prime.vault.vault_client` | WARNING+ |
| Brain maintenance | `hermes_prime.brain.maintenance` | WARNING+ |

### Key metrics to monitor:

- `hermes-prime doctor --strict --json` exit code
- Docker container restart count
- Disk usage of `.hermes-prime/` directory
- LLM provider response times

## 9. Troubleshooting

### "No module named 'hermes_cli'" on startup

The `external/hermes-agent` submodule is not initialized:
```bash
git submodule update --init external/hermes-agent
```

### "Using default dev secret 'default-dev-secret'" in logs

Set the corresponding `HERMES_SECRET_*` environment variable:
```bash
export HERMES_SECRET_SENTINEL=$(openssl rand -hex 32)
```

### OPA policy evaluation failing

Verify the policy bundle compiles:
```bash
hermes-prime inspect --json
```

If bundle is empty, run:
```bash
hermes-prime repair
```

## 10. Security Considerations

1. **Code execution sandbox** runs code in a subprocess with restricted builtins and a 10-second timeout. It is NOT a full container sandbox — do not run untrusted code from unknown sources.
2. **Secrets are HMAC keys**, not passwords. They sign data structures locally. If compromised, an attacker can forge audit traces, intents, and capabilities.
3. **SQLite databases** are not encrypted at rest. Use filesystem-level encryption (LUKS, eCryptfs) for production data.
4. **The gateway** supports Slack, Discord, and Telegram. Bot tokens for these platforms should be stored in environment variables, not in config files.
5. **Rate limiting** is enabled by default in production configuration. Disable only if you have external rate limiting.

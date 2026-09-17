# ADR 0004: Security Shield, API-Key Authentication, and VPS Production Hardening

- **Status**: Accepted
- **Date**: 2026-09-17
- **Deciders**: Lead Systems Architect & Core Developer
- **Consulted**: Security & Infrastructure Engineering

---

## 1. Context & Problem Statement

Gatekeeper operates as a high-speed execution gateway between autonomous AI trading agents and the Solana blockchain. Exposing this middleware publicly without authentication poses severe risks:
1. **Denial-of-Wallet & RPC Quota Exhaustion**: Unauthorized actors could flood the simulation engine, exhausting paid RPC credits and CPU cycles.
2. **Unauthorized Trade Submission**: Malicious entities could attempt to route unauthorized intents through the middleware.
3. **Telemetry & Strategy Leakage**: The `/metrics/savings` endpoint reveals financial savings and trade frequency, which must be confidential to the operator.

---

## 2. Architectural Decisions

### 2.1 Header-Based API-Key Authentication (`X-Gatekeeper-Key`)
- All endpoints under `/api/v1/` are protected by a mandatory dependency (`verify_api_key`).
- **Timing-Attack Resistance**: Verification uses `secrets.compare_digest(api_key, expected_key)` to eliminate timing side-channel vulnerabilities.
- **Fail-Fast**: Requests missing or supplying an invalid `X-Gatekeeper-Key` header are immediately rejected with `HTTP 401 Unauthorized` before any simulation tasks or database queries are invoked.
- **Exemptions**: The `/health` endpoint remains open without authentication to allow external uptime checkers and VPS load balancers to poll system health.

### 2.2 Defense-in-Depth VPS Architecture
The production topology follows a 3-tier boundary:

```
[ Internet / Autonomous AI Agents ]
               │
               ▼  (HTTPS Port 443 / HTTP Port 80)
┌─────────────────────────────────────────────────────────────┐
│ 1. UFW Firewall                                             │
│    - ALLOW: 22 (SSH), 80 (HTTP), 443 (HTTPS)                │
│    - DENY: 8000 (Uvicorn direct port is dropped externally) │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Nginx Reverse Proxy (Frontend Webserver)                 │
│    - Rate Limiting: 50 req/sec (burst=20, nodelay)          │
│    - Max Body Size: 2 MB limit                              │
│    - Security Headers (X-Frame-Options, X-Content-Type)     │
│    - Proxy Pass to 127.0.0.1:8000                           │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Gatekeeper Daemon (Systemd / Uvicorn)                    │
│    - Bound strictly to loopback: 127.0.0.1:8000             │
│    - Runs as non-root user: gatekeeper                      │
│    - Sandboxed: ProtectSystem=full, PrivateTmp=true         │
│    - Enforces X-Gatekeeper-Key authentication               │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 Automated Provisioning Bundle (`deploy/`)
- `gatekeeper.service`: Ensures auto-restart on crash (`Restart=always`, `RestartSec=3`) and file descriptor limits (`LimitNOFILE=65535`).
- `nginx_gatekeeper.conf`: Standardized reverse-proxy and rate-limiting template.
- `setup_vps.sh`: Idempotent bash script installing requirements, creating dedicated user, configuring firewall, generating a cryptographically secure 32-character API key, and activating services.

---

## 3. Consequences

### Positive
- Strict access control prevents unauthorized intent evaluations and metrics scraping.
- Rate-limiting at Nginx layer shields the Python event loop from volumetric floods.
- Complete operational setup can be deployed onto a clean VPS in under 3 minutes.

### Negative / Trade-offs
- Static API keys require manual rotation via `.env` and service restart. (Sufficient and optimal for low-latency agent architectures).

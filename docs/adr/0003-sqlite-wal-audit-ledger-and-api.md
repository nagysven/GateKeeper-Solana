# ADR 0003: SQLite WAL Persistence and FastAPI Service Layer

- **Status**: Accepted
- **Date**: 2026-09-17
- **Deciders**: Lead Systems Architect & Core Developer
- **Consulted**: DevOps & Middleware Operations

---

## 1. Context & Problem Statement

Gatekeeper must persist high-frequency transaction evaluations, candidate telemetry, and financial audit metrics without degrading pre-flight arbitration speeds. 

Traditional production architectures often mandate multi-node database clusters (e.g. PostgreSQL, CockroachDB) or in-memory caches (Redis). On a VPS dedicated to low-latency crypto middleware, running heavy database background services consumes vital memory and CPU cycles while introducing network socket serialization delays.

---

## 2. Architectural Decisions

### 2.1 SQLite with Write-Ahead Logging (WAL)
- We adopt an embedded SQLite engine using `aiosqlite` configured with:
  ```sql
  PRAGMA journal_mode=WAL;
  PRAGMA synchronous=NORMAL;
  PRAGMA foreign_keys=ON;
  ```
- **Concurrency**: WAL mode allows concurrent readers (e.g., monitoring dashboards or Prometheus collectors) to query metrics simultaneously without taking exclusive locks on the database file, ensuring writes complete in microsecond timeframes.
- **Reliability**: Single-file storage simplifies backups, snapshots, and state migration on the VPS.

### 2.2 Relational DDL Schema
Four core tables capture the lifecycle of every intent:
1. `intents`: Records declarative agent intentions, Pubkeys, amounts, and TTL bounds.
2. `route_candidates`: Stores the 2–3 alternative execution paths (Direct, Split, Multi-Hop).
3. `simulations`: Captures raw execution telemetry (consumed CUs, simulated delta out, logs, latency, slot).
4. `fee_savings_ledger`: Records the deterministic arbitration verdict (`DISPATCH` vs `HARD_ABORT`), capturing:
   - `base_fee_saved_lamports`
   - `priority_fee_saved_lamports`
   - `jito_tip_saved_lamports`
   - `capital_saved_lamports`
   - `clamped_cu_saved_units`

### 2.3 REST Gateway via FastAPI
- **`POST /api/v1/intent/evaluate`**:
  - Accepts an `IntentRequest` or `IntentEvaluationRequest`.
  - Automatically synthesizes 2 candidate routes (Raydium Direct, Orca Multi-Hop) if omitted.
  - Executes simulation, arbitrates verdict, commits audit ledger, and returns `ValidationResult`.
- **`GET /api/v1/metrics/savings`**:
  - Aggregates total prevented reverts, fees saved (Lamports and SOL), and mean decision latency.
- **`GET /health`**:
  - Standard liveness probe for VPS container orchestrators.

---

## 3. Consequences

### Positive
- Zero external database services to install, manage, or keep running.
- Sub-millisecond persistence directly from Python's async event loop.
- Immediate verifiable accountability for trading profits and prevented losses.

### Negative / Trade-offs
- Vertical scaling limit: SQLite is bounded by the VPS disk I/O. Mitigated by `synchronous=NORMAL` and WAL mode, capable of handling 5,000+ writes/sec on modern NVMe drives.

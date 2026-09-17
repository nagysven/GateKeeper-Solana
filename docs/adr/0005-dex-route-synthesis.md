# ADR 0005: Live Route Synthesis via Jupiter v6 DEX Aggregator

- **Status**: Accepted
- **Date**: 2026-09-17
- **Deciders**: Lead Systems Architect & Core Developer
- **Consulted**: Trading Systems Team

---

## 1. Context & Problem Statement

In early phases, Gatekeeper utilized simulated route plans. While sufficient for testing internal arbitration rules and database persistence, simulating real on-chain behavior against live Solana state requires authentic unsigned `VersionedTransaction` wire payloads containing:
- Exact AMM program IDs (Raydium CPMM/AMMv4, Orca Whirlpools, Meteora DLMM).
- Exact writable and readonly account vectors.
- Real token transfer instruction data.

---

## 2. Architectural Decisions

### 2.1 Jupiter v6 Integration (`JupiterClient`)
We integrate the Jupiter v6 API (`https://quote-api.jup.ag/v6`) to synthesize authentic Solana transactions:
- **`GET /quote`**: Obtains pricing, price impact, and AMM routing plans.
- **`POST /swap`**: Converts a quote into an unsigned Base64-encoded `VersionedTransaction` wire payload configured with:
  - `wrapAndUnwrapSol: true`
  - `dynamicComputeUnitLimit: false` (Gatekeeper handles dynamic clamping autonomously)
  - `prioritizationFeeLamports: 0` (Gatekeeper determines priority fees deterministically)

### 2.2 Dual-Candidate Strategy
For every `IntentRequest`, Gatekeeper synthesizes two structurally distinct execution paths:
1. **Candidate A (Direct Route)**:
   - Query: `onlyDirectRoutes=true`
   - Yields a single-hop swap over the largest liquidity pool.
   - Assigned the direct clamping buffer (default $+12\%$).
2. **Candidate B (Multi-Hop / Optimal Yield Route)**:
   - Query: `onlyDirectRoutes=false`
   - Yields split or multi-hop paths to capture optimal yield across liquidity fragmented over multiple pools.
   - Assigned the multi-hop clamping buffer (default $+20\%$).

### 2.3 Parallel Two-Stage Execution (`asyncio.gather`)
To maintain minimal latency overhead:
1. Stage 1: `direct_quote` and `multihop_quote` are requested concurrently via `asyncio.gather`.
2. Stage 2: Unsigned swap transactions for both routes are requested concurrently via `asyncio.gather`.

### 2.4 Resilient Aggregator Fallback
If the Jupiter API suffers from rate-limits (HTTP 429), outages, or timeouts:
- The `RouteCandidateGenerator` catches `JupiterApiError`.
- It activates `fallback_to_synthetic`, generating standard candidate structures. This guarantees that Gatekeeper's API layer remains responsive and resilient under third-party downtime.

---

## 3. Consequences

### Positive
- Gatekeeper simulates real Solana wire transactions with actual account write-locks and instruction layouts.
- Preserves zero-loss guarantees with actual liquidity pool states.
- 100% testable without network calls via `httpx.MockTransport`.

### Negative / Trade-offs
- External dependency on Jupiter quote latency (~15–30 ms). Mitigated by parallel HTTP requests and graceful fallback.

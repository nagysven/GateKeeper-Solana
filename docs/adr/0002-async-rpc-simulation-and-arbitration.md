# ADR 0002: Asynchronous RPC Simulation Loop and Deterministic Arbitration Engine

- **Status**: Accepted
- **Date**: 2026-09-17
- **Deciders**: Lead Systems Architect & Core Developer
- **Consulted**: Trading Systems Team

---

## 1. Context & Problem Statement

Autonomous Solana trading agents face two fatal traps:
1. **Serial Evaluation Latency**: Simulating multiple route alternatives serially adds 50–150 ms per hop, making simulated state stale before dispatch.
2. **Probabilistic Blind Execution**: Firing trades without verifying post-execution token balances on the live state frequently lands transactions in reverting blocks (e.g. slippage breach, lock contention, compute budget exhaustion).

To solve both issues, Gatekeeper needs an asynchronous, concurrent simulation engine and a deterministic arbitrator that acts as a non-probabilistic gatekeeper.

---

## 2. Architectural Decisions

### 2.1 Concurrent Multi-Path Simulation (`asyncio.gather`)
- Up to 3 route candidates are simulated concurrently against Solana RPC using `asyncio.gather`.
- Simulation latency equals `max(latency_route_1, latency_route_2, latency_route_3)` rather than the sum, keeping execution times under tight deadlines.

### 2.2 Layered Response Parsing & Fallback Extraction
- Solana RPC responses vary depending on node version and client options.
- The `PreFlightSimulator`:
  - Extracts `unitsConsumed` directly or parses `Program ... consumed X of Y compute units` from program logs if units are unreported.
  - Inspects `preTokenBalances` vs `postTokenBalances` to calculate exact simulated output deltas for the target wallet.
  - Analyzes both top-level RPC `err` objects and embedded Anchor/AMM log strings (e.g. `0x1771`, `AccountInUse`).

### 2.3 Deterministic Arbitration Rules
The `GatekeeperArbitrator` applies strict decision stages:
1. **Slot & Blockhash TTL Check**: If `current_slot > valid_until_slot` or blockhash age $\ge 120$ slots, immediately trigger `HARD_ABORT` with `ERR_BLOCKHASH_EXPIRED`.
2. **Candidate Viability Filter**: Only candidates with `success == True` and `simulated_delta_out >= min_amount_out` qualify.
3. **Route Selection & Compute Unit Clamping**:
   - Optimal route is chosen by highest `simulated_delta_out`, with lower CU consumption breaking ties.
   - Dynamic Clamping Buffer:
     $$\text{Clamped CU} = \text{clamp}\left(\text{consumed\_units} \times \text{buffer}, 1000, 1400000\right)$$
     where $\text{buffer} = 1.12$ for single-hop direct swaps and $1.20$ for multi-hop/split routes.
4. **Hard-Abort & Fee Protection**:
   - If all paths fail, no on-chain transaction is dispatched.
   - Preserved resources are recorded: Base Fee (5,000 Lamports), Priority Fee (based on unspent CUs), Jito Tip (100% saved), and Principal Capital.

---

## 3. Consequences

### Positive
- Zero priority fees, signature fees, or Jito tips are burned on failing transactions.
- Accurate dynamic compute limits prevent transaction drops without overpaying priority fees.
- Pure Python execution with zero external network dependencies during mock testing.

### Negative / Trade-offs
- Simulation reflects state at simulation slot; high volatility can still cause drift if latency between simulation and leader inclusion is excessive (countered by 12–20% CU clamping buffers).

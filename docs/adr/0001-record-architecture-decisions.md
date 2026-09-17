# ADR 0001: Architecture Decisions & Pre-Flight Design for Project Gatekeeper

- **Status**: Accepted
- **Date**: 2026-09-17
- **Deciders**: Lead Systems Architect & Core Developer
- **Consulted**: Autonomous Trading Stakeholders

---

## 1. Context & Problem Statement

Autonomous trading bots and AI agents on Solana frequently suffer severe capital depletion and degraded execution efficiency due to the probabilistic nature of transaction dispatch. Under high network congestion and market volatility:

1. **Burned Priority Fees & Jito Tips**: Failed or reverting transactions (e.g. AMM slippage exceeded, pool state updated between quote and land) still consume full signature fees, dynamic compute unit priority fees, and bundled Jito validator tips.
2. **Compute Unit Over-allocation vs. Exhaustion**: Unclamped transactions either request the maximum 1,400,000 Compute Units (CU)—incurring massive priority fee penalties—or default to 200,000 CU and fail due to `ComputeBudgetExceeded` when AMM tick-arrays require deeper iteration.
3. **Write-Lock Contention**: Submitting transactions targeting heavily contended AMM vaults during volatility causes transactions to stall and expire in the leader queue.
4. **Expired Blockhashes**: Latency in multi-hop route building results in transactions reaching leaders after the blockhash TTL (typically ~150 slots) has elapsed.

**Project Gatekeeper** resolves these failure modes by operating as a deterministic, low-overhead middleware layer on a VPS, sitting between AI agents and the Solana network.

---

## 2. Decision Drivers

- **Zero-Loss Guarantee on Reverts**: No transaction that would fail on-chain must ever be dispatched.
- **Minimal Latency Overhead**: The pre-flight inspection and arbitration must execute concurrently within low double-digit milliseconds.
- **Lightweight VPS Footprint**: High-throughput persistence without heavy multi-node database clusters (Postgres/Redis).
- **Verifiable Auditability**: Every aborted transaction must prove exactly how much capital, base fee, priority fee, and Jito tip were saved.
- **TDD & Testability**: Complete testability via mocked RPC responses and real Solana error dumps without needing live Devnet/Mainnet capital.

---

## 3. Key Architectural Decisions

### 3.1 Strict Separation of Probabilistic Intents vs. Deterministic Gatekeeping
- Autonomous agents submit declarative `IntentRequest` payloads (Token In, Token Out, Amount, Min Out, Max Slippage, Max Fee, Slot TTL).
- The Gatekeeper engine handles candidate generation, simulation, validation, and clamping in a strictly deterministic pipeline.

### 3.2 Parallel Pre-Flight Simulation via `asyncio.gather`
- Up to 3 route candidates (Direct Pool, Split Route, Multi-Hop) are simulated concurrently against high-speed RPC nodes using `simulateTransaction`.
- RPC parameters: `sigVerify: false`, `accounts: { encoding: "base64" }`, `replaceRecentBlockhash: false`.

### 3.3 Dynamic Compute-Budget Clamping with Configurable Safety Buffers
- Consumed compute units are extracted directly from simulation logs: `Program ... consumed X of Y compute units`.
- To absorb live AMM state drift (e.g., tick-array shifts in Raydium CPMM or Orca Whirlpools):
  - **Direct single-hop swaps**: Consumed CU $\times$ `1.12` (+12% safety margin).
  - **Multi-hop and split routes**: Consumed CU $\times$ `1.20` (+20% safety margin).
- The dynamically clamped value is injected via `ComputeBudgetProgram.setComputeUnitLimit`.

### 3.4 Comprehensive Deterministic Abort Matrix
An immediate `HARD_ABORT` is triggered (preventing any on-chain dispatch) if any of the following criteria trigger:
- `ERR_BLOCKHASH_EXPIRED`: Slot TTL exceeded or blockhash age $\ge 120$ slots.
- `ERR_SLIPPAGE_EXCEEDED`: Simulated post-balance delta is lower than `min_amount_out`.
- `ERR_ACCOUNT_CONTENTION`: Simulation returns `AccountInUse` or writable locks conflict with hotspot accounts.
- `ERR_CU_EXHAUSTION`: Consumed CUs exceed transaction or intent budget limits.
- `ERR_RENT_NON_EXEMPT`: Fee-payer SOL balance falls below rent exemption threshold.
- `ERR_INSUFFICIENT_FUNDS`: Quell-Token balance is insufficient to fund input amount.
- `ERR_CUSTOM_PROGRAM_FAIL`: Program logs reveal known DEX revert codes (e.g., Raydium `0x1771`).

### 3.5 Complete Fee & Tip Savings Accounting
The audit ledger measures:
$$\text{Saved Fees} = \text{Base Fee (5,000 Lamports)} + \left(\frac{\text{Clamped CU} \times \text{Priority Rate}}{10^6}\right) + \text{Jito Tip (Lamports)}$$
This captures both Solana validator priority fees and Jito block-engine tips that would have been burned upon block inclusion.

### 3.6 VPS Storage Engine: SQLite in WAL Mode
- High performance, single-file ACID persistence using Write-Ahead Logging (`PRAGMA journal_mode=WAL;`).
- Provides microsecond append-only writes, allowing concurrent readers (monitoring dashboards, Prometheus exporters) without blocking pre-flight arbitration.

---

## 4. Consequences

### Positive
- Prevents 100% of avoidable priority fee and Jito tip burning on predictable reverts.
- Optimizes transaction inclusion probability via precise CU clamping.
- Complete transparency for capital allocation and bot performance.
- Ultra-low VPS CPU/RAM resource footprint.

### Negative / Trade-offs
- Adds a small pre-flight RPC round-trip latency (~15–60 ms depending on RPC locality).
- Highly volatile pools may experience state changes in the ~400ms between simulation and block leader processing; mitigated by the 12–20% dynamic CU buffer and strict slippage bounds.

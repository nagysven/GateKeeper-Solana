# 🛡️ Project Gatekeeper: The Deterministic Firewall for Solana AI Agents

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0+-blue.svg)](https://www.typescriptlang.org/)
[![Tests: 47/47](https://img.shields.io/badge/tests-47%20passed-brightgreen.svg)](tests/)
[![Gateway: Live](https://img.shields.io/badge/Gateway-gk.ai--futures--bot.pro-green.svg)](https://gk.ai-futures-bot.pro)

> **Every autonomous AI agent signing raw Solana transactions burns 8–15% of its capital on slippage spikes, DEX reverts (`0x1771`), and account contention.**  
> **Gatekeeper intercepts every intent before broadcast and guarantees ZERO gas burned on failed trades.**

---

## 📊 Verifiable Production Benchmarks

Measured on live Ubuntu Linux VPS (`85.215.195.247`) via HTTPS reverse proxy:

| Metric | Industry Standard (Raw Broadcast) | With Project Gatekeeper | Impact |
| :--- | :--- | :--- | :--- |
| **Failed Transaction Cost** | 5,000–250,000 Lamports ($0.01–$0.05) | **0 Lamports ($0.00)** | **100% Capital Preservation** |
| **Pre-Flight Arbitration Latency** | N/A (Blind Submit) | **55 – 79 ms** | **Sub-100ms Fast Path** |
| **Compute Budget per Swap** | 200,000 CU (Over-provisioned) | **49,078 CU (Dynamically Clamped)** | **~150,922 CU Saved / Swap** |
| **DEX Slippage Reverts (`0x1771`)** | Reverted On-Chain (Fee Burned) | **Hard-Aborted Off-Chain** | **Zero Fee Burn** |
| **Audit Logging Performance** | None | **Sub-ms SQLite WAL Ledger** | **Full Audit Trail** |

---

## ⚡ Pipeline Architecture

```
[ AI Agent / Trading Bot ]
             │  (IntentRequest: In, Out, Amount, Max Slippage, TTL)
             ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. INGESTION & NORMALIZER (FastAPI / Pydantic v2)           │
│  - Slot-Synchronisation & Blockhash Time-to-Live Validation │
└──────────────────────────┬──────────────────────────────────┘
                           │
            ┌──────────────┴──────────────┐
            ▼                             ▼
┌──────────────────────────┐  ┌───────────────────────────────┐
│ 2. JUPITER ROUTE SYNTH   │  │ 3. SOLANA CLUSTER MONITOR     │
│  - Route A: Direct Swap  │  │  - WSS Slot & Blockhash State │
│  - Route B: Multi-Hop/DEX│  │  - Contended Accounts Cache   │
└───────────┬──────────────┘  └───────────────┬───────────────┘
            │                                 │
            └──────────────┬──────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. PARALLEL PRE-FLIGHT SIMULATION (asyncio.gather)          │
│  - Concurrent simulateTransaction against live cluster state│
│  - Token balance delta verification & Log error extraction  │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. DETERMINISTIC ARBITRATION & CLAMPING MATRIX              │
│  - Evaluates Slippage (0x1771), Contention (AccountInUse)   │
│  - Dynamic CU Limit Clamping = (Consumed Units * 1.12)      │
└──────────────┬───────────────────────────────┬──────────────┘
               │                               │
      (Valid Route Found)             (All Routes Reverted)
               ▼                               ▼
┌──────────────────────────────┐ ┌─────────────────────────────┐
│ 6. DISPATCH GATEWAY          │ │ 7. HARD-ABORT INTERCEPT     │
│  - Optimal Transaction Return│ │  - Immediate Drop: 0 Gas    │
│  - Minimal Priority Fee      │ │  - Saved Fee Ledger Record  │
└──────────────┬───────────────┘ └─────────────┬───────────────┘
               │                               │
               └───────────────┬───────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 8. PERSISTENT AUDIT LEDGER (SQLite / WAL Mode)              │
│  - Sub-millisecond logging of all intents, CUs & savings    │
└─────────────────────────────────────────────────────────────┘
```

---

## 🛡️ Deterministic Abort Matrix

Gatekeeper strictly enforces a **Zero-Tolerance Abort Policy**. Transactions are immediately dropped off-chain if any criterion is triggered:

| Abort Code | Failure Mechanism | Root Cause & Detection | Action Taken |
| :--- | :--- | :--- | :--- |
| `ERR_SLIPPAGE_EXCEEDED` | DEX Revert `0x1771` / `0x1770` | Simulated price impact exceeds agent tolerance | **HARD_ABORT** (0 Gas) |
| `ERR_BLOCKHASH_EXPIRED` | Stale Transaction | Slot buffer `< 10` slots before blockhash expiration | **HARD_ABORT** (0 Gas) |
| `ERR_ACCOUNT_CONTENTION`| Lock Conflict | Simulation throws `AccountInUse` or hot pool lock | **HARD_ABORT** (0 Gas) |
| `ERR_CU_EXHAUSTION` | Compute Unit Cap | Simulation consumed `> max_compute_units` limit | **HARD_ABORT** (0 Gas) |
| `ERR_RENT_NON_EXEMPT` | SOL Depletion | Post-fee SOL balance falls below rent-exempt threshold | **HARD_ABORT** (0 Gas) |

---

## 🚀 Quickstart: Python SDK (`gatekeeper-py`)

### 1. Installation

```bash
pip install gatekeeper-py
```

### 2. Protect Your Agent in 5 Lines of Code

```python
import asyncio
from gatekeeper_py import GatekeeperAsyncClient

async def main():
    gk = GatekeeperAsyncClient(
        api_key="gk_your_api_key",
        base_url="https://gk.ai-futures-bot.pro"
    )

    verdict = await gk.evaluate_intent(
        token_in="So11111111111111111111111111111111111111112",   # SOL
        token_out="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
        amount_in=100_000_000,                                   # 0.1 SOL
        max_slippage_bps=50,                                     # 0.50%
    )

    if verdict.is_approved:
        print(f"✅ Approved in {verdict.execution_time_ms}ms! Route: {verdict.selected_route}")
        print(f"Optimal CU: {verdict.clamped_compute_units} (Saved: {verdict.clamped_cu_saved} CU)")
        # Broadcast safely with clamped compute budget
    else:
        print(f"🛡️ HARD-ABORT: {verdict.rejection_reason}")
        print(f"💰 Saved: {verdict.fees_saved_sol} SOL in wasted fees!")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 🌐 Quickstart: TypeScript SDK (`@gatekeeper/solana-sdk`)

### 1. Installation

```bash
npm install @gatekeeper/solana-sdk
```

### 2. Node.js / ElizaOS Integration

```typescript
import { GatekeeperClient } from "@gatekeeper/solana-sdk";

const gk = new GatekeeperClient({
  apiKey: process.env.GATEKEEPER_API_KEY!,
  baseUrl: "https://gk.ai-futures-bot.pro"
});

const verdict = await gk.evaluateIntent({
  token_in: "So11111111111111111111111111111111111111112",
  token_out: "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
  amount_in: 100000000,
  max_slippage_bps: 50,
});

if (verdict.decision === "APPROVED") {
  console.log(`✅ Approved in ${verdict.execution_time_ms}ms via ${verdict.selected_route}`);
} else {
  console.warn(`🛡️ Hard Abort: ${verdict.rejection_reason} - Saved ${verdict.fees_saved_lamports} lamports`);
}
```

---

## 🎬 Live Interactive Demo

Run the included live verification script against the production VPS:

```bash
python examples/demo_revert_intercept.py
```

Sample output:
```text
======================================================================
  PROJECT GATEKEEPER: THE DETERMINISTIC FIREWALL FOR SOLANA AI AGENTS  
  Live Gateway: https://gk.ai-futures-bot.pro                         
======================================================================

[1/3] Gateway Liveness Probe...
  [OK] Connected to gatekeeper (version 0.1.0, status: healthy)

[2/3] SCENARIO A: Valid AI Agent Swap Intent (SOL -> USDC)
  Intent: Swap 0.1 SOL for USDC (max slippage: 50 bps = 0.5%)
  >>> VERDICT: APPROVED (DISPATCH)
      • Pre-Flight Latency: 77.7 ms
      • Selected Route:     RAYDIUM (Hops: 1)
      • Clamped CU Limit:   49078 CU (150,922 CU preserved vs standard limit)

[3/3] SCENARIO B: Volatile/Contended Intent (Pre-Flight Revert Intercept)
  Intent: High-Frequency Swap with extreme slippage boundary (1 bp = 0.01%)
  >>> VERDICT: REJECTED (HARD_ABORT)
      • Pre-Flight Latency: 55.94 ms
      • Abort Code:         ERR_SLIPPAGE_EXCEEDED
      • Root Cause:         Slippage tolerance exceeded: (0x1771)
      • On-Chain Gas Paid:  0 LAMPORT (0.00 SOL verbrannt)
      • Saved Fees & Tip:   7,556 Lamports preserved in wallet
```

---

## 🏛️ Architecture Decision Records (ADRs)

Every design decision is documented and auditable:
- [ADR-0001: Architecture Decisions & Pipeline Design](docs/adr/0001-record-architecture-decisions.md)
- [ADR-0002: Async RPC Simulation & Arbitration](docs/adr/0002-async-rpc-simulation-and-arbitration.md)
- [ADR-0003: SQLite WAL Audit Ledger & API](docs/adr/0003-sqlite-wal-audit-ledger-and-api.md)
- [ADR-0004: API Key Authentication & VPS Hardening](docs/adr/0004-api-key-auth-and-vps-hardening.md)
- [ADR-0005: DEX Route Synthesis via Jupiter v6](docs/adr/0005-dex-route-synthesis.md)

---

## 📜 License

Project Gatekeeper is open source under the [MIT License](LICENSE).
Proprietary cloud infrastructure and high-speed multi-mempool routing are operated via managed gateway.

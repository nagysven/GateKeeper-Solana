# gatekeeper-solana

[![PyPI version](https://img.shields.io/pypi/v/gatekeeper-solana.svg)](https://pypi.org/project/gatekeeper-solana/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)
[![Gateway Status](https://img.shields.io/badge/Gateway-Live-emerald.svg)](https://gk.ai-futures-bot.pro)

**The Deterministic Pre-Flight Transaction Security & Gas Firewall for Autonomous Solana AI Agents.**

`gatekeeper-solana` protects autonomous AI trading agents, treasury bots, and algorithmic swappers on Solana from burning capital on failed on-chain transactions. It intercepts swap intents off-chain, simulates execution against live cluster state, verifies slippage and contention limits, dynamically clamps compute units (`CU`), and rejects failing routes before any transaction is signed or broadcast.

> **Zero Gas Burned on Reverts. Guaranteed.**

---

## ⚡ Key Features

- **🛡️ 0 Gas Burned on Fails**: Catches DEX slippage spikes (e.g. Raydium `0x1771`), expired blockhashes, and account contention *off-chain* before priority fees are paid.
- **⚡ Sub-80ms Latency**: High-throughput pre-flight evaluation pipeline benchmarked at `~74-79ms` in production.
- **✂️ Dynamic CU Clamping**: Automatically injects exact compute unit limits (`simulated + 12% safety buffer`), saving over 150,000 unneeded compute units per trade.
- **📊 Real-Time Metrics**: Full audit trail of saved priority fees, base fees, and protected treasury capital via public and private endpoints.
- **🔄 Async & Sync Clients**: Full support for both `asyncio` high-throughput agent loops and synchronous Python bots.

---

## 📦 Installation

```bash
pip install gatekeeper-solana
```

*(Note: `import gatekeeper_py` is also supported for backward compatibility).*

---

## 🚀 Quickstart

### 1. Asynchronous Agent Integration (Recommended)

```python
import asyncio
from gatekeeper_solana import GatekeeperAsyncClient

async def main():
    gk = GatekeeperAsyncClient(
        api_key="gk_your_api_key",
        base_url="https://gk.ai-futures-bot.pro"
    )

    # Pre-flight check before building/signing transaction
    evaluation = await gk.evaluate_intent(
        token_in="So11111111111111111111111111111111111111112",   # SOL
        token_out="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
        amount_in=100_000_000,                                   # 0.1 SOL (Lamports)
        max_slippage_bps=50,                                     # 0.50%
        priority_fee_cap_lamports=100_000,
    )

    if evaluation.is_approved:
        print(f"✅ Trade APPROVED in {evaluation.execution_time_ms:.1f}ms")
        print(f"Optimal Route: {evaluation.selected_route}")
        print(f"Clamped CU Limit: {evaluation.clamped_compute_units} (Saved: {evaluation.clamped_cu_saved:,} units)")
        # Proceed with on-chain dispatch with clamped compute units
    else:
        print(f"🛑 Trade HARD_ABORT: {evaluation.rejection_reason}")
        print(f"Details: {evaluation.rejection_details}")
        print(f"💰 Preserved: {evaluation.fees_saved_sol:.6f} SOL in wasted fees!")
        # Stop execution - 0 gas burned on-chain!

if __name__ == "__main__":
    asyncio.run(main())
```

---

### 2. Synchronous Integration

```python
from gatekeeper_solana import GatekeeperClient

gk = GatekeeperClient(
    api_key="gk_your_api_key",
    base_url="https://gk.ai-futures-bot.pro"
)

evaluation = gk.evaluate_intent(
    token_in="So11111111111111111111111111111111111111112",
    token_out="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    amount_in=100_000_000,
    max_slippage_bps=50,
)

if evaluation.is_approved:
    print(f"Safe to broadcast with {evaluation.clamped_compute_units} CU limit.")
else:
    print(f"Intercepted: {evaluation.rejection_reason}. 0 gas burned.")
```

---

## 🔍 Pre-Flight Evaluation Model

| Attribute | Type | Description |
| :--- | :--- | :--- |
| `is_approved` | `bool` | `True` if trade passes off-chain simulation safely |
| `decision` | `str` | `"APPROVED"` or `"REJECTED"` |
| `action` | `str` | `"DISPATCH"` or `"HARD_ABORT"` |
| `clamped_compute_units` | `int` | Exact CU limit to set in transaction instruction |
| `clamped_cu_saved` | `int` | Number of unneeded CUs saved vs Solana default (200k) |
| `fees_saved_sol` | `float` | Amount of SOL preserved on abort |
| `rejection_reason` | `str | None` | E.g. `ERR_SLIPPAGE_EXCEEDED`, `ERR_BLOCKHASH_EXPIRED` |
| `execution_time_ms` | `float` | Gateway evaluation latency in milliseconds |

---

## 🌐 Ecosystem & Live Portal

- **Live Developer Portal & Savings Dashboard**: [https://gk.ai-futures-bot.pro](https://gk.ai-futures-bot.pro)
- **GitHub Repository**: [https://github.com/nagysven/GateKeeper-Solana](https://github.com/nagysven/GateKeeper-Solana)
- **Solana Agent Kit (SendAI) Adapter**: `@gatekeeper/solana-agent-kit`
- **ElizaOS Plugin**: `@gatekeeper/plugin-solana`

---

## 📜 License

MIT License. See [LICENSE](https://github.com/nagysven/GateKeeper-Solana/blob/master/LICENSE) for details.

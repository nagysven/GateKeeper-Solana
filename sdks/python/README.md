# gatekeeper-py

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)

**The Deterministic Firewall for Autonomous Solana AI Agents.**

`gatekeeper-py` protects AI trading agents, automated swappers, and treasury bots from burning capital on Solana. It intercepts swap intents, simulates them concurrently against live RPC cluster state, verifies against a deterministic abort matrix, dynamically clamps compute budget limits, and rejects failing routes before any transaction is broadcast to the network.

**Zero Gas Burned on Reverts. Guaranteed.**

---

## ⚡ Key Features

- **🛡️ 0 Gas Burned on Fails**: Catches DEX slippage errors (e.g. Raydium `0x1771`), expired blockhashes, and account contention *off-chain* before priority fees are paid.
- **⚡ Ultra-Low Latency**: Sub-80ms evaluation pipeline (`~76-79ms` production benchmark).
- **✂️ Dynamic CU Clamping**: Automatically injects exact compute unit limits (`simulated + 12% safety buffer`), saving over 150,000 unneeded compute units per trade.
- **📊 Verifiable Savings Ledger**: Full audit trail of saved priority fees, base fees, and protected capital.

---

## 🚀 Quickstart

### Installation

```bash
pip install gatekeeper-py
```

### Usage (Sync or Async)

```python
import asyncio
from gatekeeper_py import GatekeeperAsyncClient

async def main():
    gk = GatekeeperAsyncClient(
        api_key="gk_your_production_key",
        base_url="https://gk.ai-futures-bot.pro"
    )

    evaluation = await gk.evaluate_intent(
        token_in="So11111111111111111111111111111111111111112",   # SOL
        token_out="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
        amount_in=100_000_000,                                   # 0.1 SOL
        max_slippage_bps=50,                                     # 0.50%
        priority_fee_cap_lamports=100_000,
    )

    if evaluation.is_approved:
        print(f"✅ Trade APPROVED in {evaluation.execution_time_ms}ms")
        print(f"Optimal route: {evaluation.selected_route}")
        print(f"Clamped CU: {evaluation.clamped_compute_units} (Saved: {evaluation.clamped_cu_saved} units)")
    else:
        print(f"❌ Trade REJECTED: {evaluation.rejection_reason}")
        print(f"Details: {evaluation.rejection_details}")
        print(f"💰 Saved: {evaluation.fees_saved_sol} SOL in wasted fees!")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 📜 License

MIT License.

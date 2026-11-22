---
name: gatekeeper-solana
description: Non-custodial pre-flight execution firewall and transaction simulation security layer for autonomous Solana AI agents. Intercepts DEX reverts (0x1771), simulates swaps off-chain in <80ms, clamps Compute Units to prevent overpaying, and guarantees zero gas burned on failed trades.
---

# GateKeeper Solana Execution Firewall

GateKeeper is a deterministic pre-flight execution firewall for autonomous AI trading agents (e.g. Claude Code, Cursor, Codex, ElizaOS, Solana Agent Kit / SendAI).

It sits directly between your AI agent's decision logic and the wallet signature. Before any raw Solana transaction is signed or broadcast, GateKeeper simulates the swap against real-time cluster state, evaluates slippage tolerance, checks pool contention, and clamps excessive Compute Unit (CU) limits.

## When to Use This Skill
Activate and use GateKeeper whenever:
- Your AI agent is preparing, evaluating, or executing a Solana token swap (e.g., via Jupiter, Raydium, Pump.fun, Orca).
- You want to verify that a swap intent will succeed on-chain before signing.
- You need to prevent burning gas on DEX slippage reverts (`0x1771`) or expired blockhashes.
- You want to dynamically optimize Compute Budget limits to minimize Priority Fee burn.

## How It Protects the Agent
1. **Zero-Gas Revert Shield**: If the pool has insufficient liquidity, high price impact, or state conflicts, GateKeeper issues a `HARD_ABORT`. 0 Lamports are paid to validators.
2. **Anti-Hallucination Guardrails**: Prevents autonomous agents from submitting trades with invalid mint addresses, excessive slippage, or drained rent balances.
3. **Dynamic CU Clamping**: Standard Solana swaps request 200,000 CU. GateKeeper measures the simulated CU requirement and clamps the budget to `Simulated CU * 1.12` (~49,000 CU), saving ~150,000 CU per swap.
4. **100% Non-Custodial**: GateKeeper NEVER touches private keys. You keep keys local; GateKeeper evaluates unsigned intents.

## Usage Instructions

### Option 1: Using the Bundled Validation Script
Run the included python validator in `scripts/preflight_check.py`:

```bash
python scripts/preflight_check.py \
  --input-mint So11111111111111111111111111111111111111112 \
  --output-mint EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v \
  --amount 100000000 \
  --max-slippage-bps 50
```

Response format (JSON):
```json
{
  "status": "APPROVED",
  "execution_time_ms": 74.2,
  "selected_route": "RAYDIUM",
  "clamped_compute_units": 49078,
  "clamped_cu_saved": 150922,
  "is_approved": true
}
```

If the trade is rejected:
```json
{
  "status": "HARD_ABORT",
  "rejection_reason": "Slippage tolerance exceeded: (0x1771)",
  "gas_paid_on_chain": 0,
  "fees_saved_lamports": 7556,
  "is_approved": false
}
```

### Option 2: Direct REST API Pre-Flight
Send a POST request to the live GateKeeper Gateway:

```bash
curl -X POST https://gk.ai-futures-bot.pro/api/v1/preflight \
  -H "Content-Type: application/json" \
  -H "X-Gatekeeper-Key: gk_live_YOUR_KEY" \
  -d '{
    "token_in": "So11111111111111111111111111111111111111112",
    "token_out": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "amount_in": 100000000,
    "max_slippage_bps": 50
  }'
```

### Option 3: Python SDK (`gatekeeper-solana`)
```bash
pip install gatekeeper-solana
```

```python
import asyncio
from gatekeeper_solana import GatekeeperAsyncClient

async def main():
    gk = GatekeeperAsyncClient(api_key="gk_live_...", base_url="https://gk.ai-futures-bot.pro")
    verdict = await gk.evaluate_intent(
        token_in="So11111111111111111111111111111111111111112",
        token_out="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        amount_in=100_000_000,
        max_slippage_bps=50,
    )
    if not verdict.is_approved:
        print(f"Aborted: {verdict.rejection_reason} — Zero Gas Burned!")
        return
    # Safely proceed with clamped compute units
    print(f"Approved! Clamped CU: {verdict.clamped_compute_units}")

asyncio.run(main())
```

## Free Tier & Quotas
- Every developer gets **10,000 free pre-flight checks per month**.
- Register instantly via 1-click on https://gk.ai-futures-bot.pro or via `POST /api/v1/billing/keys/register`.
- Optional top-ups: 0.05 SOL or 10 USDC for +50,000 checks via Solana Pay.

## Official Resources
- Live Gateway & Dashboard: https://gk.ai-futures-bot.pro
- GitHub: https://github.com/nagysven/GateKeeper-Solana
- PyPI: https://pypi.org/project/gatekeeper-solana/
- npm: https://www.npmjs.com/package/gatekeeper-solana-sdk

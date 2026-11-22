# GateKeeper Solana Execution Firewall Reference

## Core Abort Matrix

| Abort Code | Cause | Action | Impact |
| :--- | :--- | :--- | :--- |
| `ERR_SLIPPAGE_EXCEEDED` | Price impact exceeds agent tolerance (`0x1771`) | HARD_ABORT | 0 Gas Burned on-chain |
| `ERR_BLOCKHASH_EXPIRED` | Recent blockhash is older than safe window | HARD_ABORT | 0 Gas Burned on-chain |
| `ERR_ACCOUNT_CONTENTION` | Pool or account locked by competing transaction | HARD_ABORT | 0 Gas Burned on-chain |
| `ERR_CU_EXHAUSTION` | Execution requires more CU than safe limit | HARD_ABORT | 0 Gas Burned on-chain |
| `ERR_RENT_NON_EXEMPT` | Post-swap balance drops below rent exemption | HARD_ABORT | 0 Gas Burned on-chain |

## Dynamic Compute Unit Clamping
GateKeeper measures exact execution units from RPC simulation and applies an optimal 1.12x multiplier (1.20x on multi-hop routes). This replaces default 200,000 CU limits with ~49,000 CU, preserving ~150,000 CU per swap and protecting the agent from excessive Priority Fee burn.

## Links
- Live Portal: https://gk.ai-futures-bot.pro
- GitHub: https://github.com/nagysven/GateKeeper-Solana
- PyPI: https://pypi.org/project/gatekeeper-solana/
- npm: https://www.npmjs.com/package/gatekeeper-solana-sdk

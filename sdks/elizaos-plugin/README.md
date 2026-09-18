# gatekeeper-plugin-solana

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![ElizaOS](https://img.shields.io/badge/ElizaOS-Plugin-purple.svg)](https://github.com/elizaos/eliza)
[![npm version](https://img.shields.io/badge/npm-v0.1.0-blue.svg)](https://www.npmjs.com/package/gatekeeper-plugin-solana)

**Deterministic Pre-Flight Transaction Security & Gas Firewall Plugin for ElizaOS AI Agents.**

Protect your autonomous ElizaOS agents from burning treasury SOL on failed swaps, DEX slippage reverts (`0x1771`), and account contention. Gatekeeper simulates swap intents off-chain before signing, dynamically clamps compute units (`CU`), and guarantees **0 gas burned** on failed transactions.

---

## ⚡ Features

- **🛡️ 0 Gas Burned on Reverts**: Catches slippage errors (e.g. Raydium `0x1771`), expired blockhashes, and account locking *off-chain* before priority fees are paid.
- **✂️ Dynamic Compute Budget Clamping**: Automatically injects exact compute unit limits (`simulated + 12% safety buffer`), saving over 150,000 unneeded compute units per swap.
- **⚡ Sub-80ms Latency**: Ultra-fast off-chain simulation against live Solana cluster state.
- **📊 Context Provider for Agents**: Supplies your ElizaOS agent with real-time stats on preserved fees and protected capital.

---

## 📦 Installation

```bash
npm install gatekeeper-plugin-solana
```

Or with `pnpm`:
```bash
pnpm add gatekeeper-plugin-solana
```

---

## ⚙️ Environment Variables

Configure your ElizaOS character file or `.env` with the following variables:

| Variable | Description | Default |
| :--- | :--- | :--- |
| `GATEKEEPER_API_KEY` | *(Required for production)* Your secret Gatekeeper API Key | `gk_...` |
| `GATEKEEPER_API_URL` | Gatekeeper Gateway Base URL | `https://gk.ai-futures-bot.pro` |

---

## 🚀 Quickstart: Integrating into ElizaOS Runtime

### 1. Character File Configuration (`character.json`)

```json
{
  "name": "SolanaTreasuryGuard",
  "plugins": ["@gatekeeper/plugin-solana"],
  "settings": {
    "secrets": {
      "GATEKEEPER_API_KEY": "gk_your_production_api_key",
      "GATEKEEPER_API_URL": "https://gk.ai-futures-bot.pro"
    }
  }
}
```

### 2. Direct Programmatic Registration

```typescript
import { AgentRuntime } from "@elizaos/core";
import { gatekeeperPlugin } from "@gatekeeper/plugin-solana";

const runtime = new AgentRuntime({
  character: myCharacter,
  plugins: [
    gatekeeperPlugin,
    // ...other plugins (e.g. solana trading)
  ],
});

await runtime.initialize();
```

---

## 🔍 How it Works

1. When a user requests a swap (e.g. *"Swap 0.5 SOL for USDC"*), the `GATEKEEPER_PREFLIGHT` action intercepts the trading parameters.
2. The plugin submits a pre-flight intent to the Gatekeeper Gateway (`https://gk.ai-futures-bot.pro/api/v1/preflight`).
3. If valid, the trade is **APPROVED** with an exact clamped compute budget (e.g. 49,078 CU instead of 200,000 CU).
4. If invalid (e.g. DEX revert `0x1771`), Gatekeeper returns **`HARD_ABORT`** off-chain:
   ```text
   🛡️ [Gatekeeper Pre-Flight] HARD_ABORT triggered in 54ms!
   • Reason: ERR_SLIPPAGE_EXCEEDED (0x1771)
   • On-Chain Gas Paid: 0 Lamports (0.00 SOL verbrannt)
   • Preserved Fees: 0.007556 SOL saved in agent treasury.
   ```

---

## 🧪 Testing

Run the included smoke test suite:

```bash
npm test
```

---

## 📜 License

MIT License. See [LICENSE](../../LICENSE) for details.

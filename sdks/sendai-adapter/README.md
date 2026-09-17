# @gatekeeper/solana-agent-kit

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![SendAI](https://img.shields.io/badge/SendAI-Solana--Agent--Kit-blue.svg)](https://github.com/sendaifun/solana-agent-kit)
[![npm version](https://img.shields.io/badge/npm-v0.1.0-blue.svg)](https://www.npmjs.com/package/@gatekeeper/solana-agent-kit)

**Deterministic Pre-Flight Transaction Security & Gas Firewall Adapter for Solana Agent Kit (SendAI).**

Equip autonomous AI agents using SendAI's `solana-agent-kit` with deterministic pre-flight transaction protection. Gatekeeper intercepts swap intents, simulates execution off-chain against live RPC state, clamps compute budget limits (`CU`), and guarantees **0 gas burned** on failed transactions.

---

## ⚡ Features

- **🛡️ Zero Gas Burned on Fails**: Catches DEX slippage spikes (e.g. Raydium `0x1771`), expired blockhashes, and account contention *off-chain* before any transaction is signed.
- **✂️ Dynamic Compute Budget Clamping**: Injects exact compute unit limits (`simulated + 12% safety buffer`), saving over 150,000 unneeded compute units per trade.
- **⚡ Sub-80ms Latency**: Ultra-fast off-chain simulation against live Solana cluster state.
- **🔌 Native SendAI Action Interface**: Works seamlessly with LangChain, LangGraph, and SolanaAgentKit tool runners.

---

## 📦 Installation

```bash
npm install @gatekeeper/solana-agent-kit
```

Or with `pnpm`:
```bash
pnpm add @gatekeeper/solana-agent-kit
```

---

## ⚙️ Environment Variables

Set the following variables in your `.env` or agent configuration:

| Variable | Description | Default |
| :--- | :--- | :--- |
| `GATEKEEPER_API_KEY` | *(Required for production)* Your secret Gatekeeper API Key | `gk_...` |
| `GATEKEEPER_API_URL` | Gatekeeper Gateway Base URL | `https://gk.ai-futures-bot.pro` |

---

## 🚀 Quickstart: Integrating into Solana Agent Kit

```typescript
import { SolanaAgentKit, createSolanaTools } from "solana-agent-kit";
import { createGatekeeperTools } from "@gatekeeper/solana-agent-kit";

// 1. Initialize the Solana Agent Kit
const agent = new SolanaAgentKit(
  process.env.SOLANA_PRIVATE_KEY!,
  process.env.RPC_URL!,
  process.env.OPENAI_API_KEY!
);

// 2. Create Gatekeeper pre-flight tools
const gatekeeperTools = createGatekeeperTools({
  apiKey: process.env.GATEKEEPER_API_KEY,
  baseUrl: process.env.GATEKEEPER_API_URL || "https://gk.ai-futures-bot.pro",
});

// 3. Combine with standard Solana tools for LangChain/Agent execution
const allTools = [
  ...createSolanaTools(agent),
  ...gatekeeperTools,
];

console.log("🛡️ Agent armed with Gatekeeper Pre-Flight Firewall!");
```

---

## 🔍 How It Works

1. Prior to broadcasting a DEX swap, the agent calls the `gatekeeper_preflight` action:
   ```json
   {
     "inputMint": "So11111111111111111111111111111111111111112",
     "outputMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
     "amount": 100000000,
     "maxSlippageBps": 50
   }
   ```
2. If safe, Gatekeeper returns **`APPROVED`** with clamped compute units (`49,078 CU` vs standard `200,000 CU`).
3. If unsafe (e.g. slippage exceed `0x1771`), Gatekeeper enforces **`HARD_ABORT`**:
   ```json
   {
     "success": false,
     "decision": "REJECTED",
     "action": "HARD_ABORT",
     "rejectionReason": "ERR_SLIPPAGE_EXCEEDED",
     "gasPaidOnChain": 0,
     "feesSavedLamports": 7556,
     "message": "Gatekeeper HARD_ABORT triggered in 55ms! 0 gas burned on-chain. Preserved 0.007556 SOL in treasury."
   }
   ```

---

## 🧪 Testing

Run the automated test harness:

```bash
npm test
```

---

## 📜 License

MIT License. See [LICENSE](../../LICENSE) for details.

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
import { Keypair } from "@solana/web3.js";
import { SolanaAgentKit, createSolanaTools } from "solana-agent-kit";
import { createGatekeeperTools } from "@gatekeeper/solana-agent-kit";
import bs58 from "bs58";

// 1. Initialize SolanaAgentKit (via Keypair or Base58 Secret Key)
const keypair = Keypair.fromSecretKey(bs58.decode(process.env.SOLANA_PRIVATE_KEY!));
const agent = SolanaAgentKit.fromKeypair(
  keypair,
  process.env.RPC_URL || "https://api.mainnet-beta.solana.com",
  { OPENAI_API_KEY: process.env.OPENAI_API_KEY }
);

// 2. Instantiate Gatekeeper pre-flight action
const gatekeeperTools = createGatekeeperTools({
  apiKey: process.env.GATEKEEPER_API_KEY,
  baseUrl: process.env.GATEKEEPER_API_URL || "https://gk.ai-futures-bot.pro",
});

// 3. Combine with standard Solana tools for LangChain / LangGraph execution
const allTools = [
  ...createSolanaTools(agent),
  ...gatekeeperTools,
];

console.log("🛡️ Agent armed with Gatekeeper Pre-Flight Firewall (gatekeeper_preflight_check)!");
```

---

## 🔍 Tool: `gatekeeper_preflight_check`

Prior to broadcasting any DEX swap, the agent invokes `gatekeeper_preflight_check`:

```json
{
  "inputMint": "So11111111111111111111111111111111111111112",
  "outputMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
  "amount": 100000000,
  "maxSlippageBps": 50
}
```

### Response Scenarios:

#### 1. Scenario: Safe Execution (`APPROVED`)
Gatekeeper optimizes execution parameters and clamps compute units dynamically:
```json
{
  "status": "APPROVED",
  "decision": "APPROVED",
  "action": "DISPATCH",
  "clampedComputeUnits": 49078,
  "clampedCuSaved": 150922,
  "selectedRoute": "RAYDIUM_CLMM",
  "gasPaidOnChain": 0,
  "message": "Gatekeeper Pre-Flight APPROVED in 68.4ms via RAYDIUM_CLMM. Clamped CU Limit: 49078 (Saved: 150,922 CU vs default). Safe to dispatch."
}
```

#### 2. Scenario: Revert Prevented (`HARD_ABORT`)
When slippage spike or liquidity crunch is detected off-chain (e.g. `0x1771`), Gatekeeper intercepts the trade:
```json
{
  "status": "HARD_ABORT",
  "decision": "REJECTED",
  "action": "HARD_ABORT",
  "rejectionReason": "ERR_SLIPPAGE_EXCEEDED",
  "gasPaidOnChain": 0,
  "feesSavedLamports": 7556,
  "feesSavedSol": "0.000008",
  "message": "Gatekeeper HARD_ABORT triggered in 48.9ms! Revert prevented: ERR_SLIPPAGE_EXCEEDED. 0 gas burned on-chain. Preserved 0.000008 SOL in treasury."
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

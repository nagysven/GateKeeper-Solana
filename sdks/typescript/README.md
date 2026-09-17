# @gatekeeper/solana-sdk

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0+-blue.svg)](https://www.typescriptlang.org/)

**The Deterministic Firewall for Autonomous Solana AI Agents.**

`@gatekeeper/solana-sdk` provides native TypeScript client support for AI trading agents, ElizaOS plugins, and autonomous bots to intercept swap intents, simulate execution off-chain against live RPC state, and prevent failed transactions from burning gas on Solana.

---

## ⚡ Quickstart

### Installation

```bash
npm install @gatekeeper/solana-sdk
```

### Usage

```typescript
import { GatekeeperClient } from "@gatekeeper/solana-sdk";

const gk = new GatekeeperClient({
  apiKey: "gk_your_production_key",
  baseUrl: "https://gk.ai-futures-bot.pro"
});

async function run() {
  const verdict = await gk.evaluateIntent({
    token_in: "So11111111111111111111111111111111111111112",   // SOL
    token_out: "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  // USDC
    amount_in: 100000000,                                      // 0.1 SOL
    max_slippage_bps: 50,
  });

  if (verdict.decision === "APPROVED") {
    console.log(`✅ Approved in ${verdict.execution_time_ms}ms! Route: ${verdict.selected_route}`);
    console.log(`Clamped CU: ${verdict.clamped_compute_units} (Saved: ${verdict.clamped_cu_saved} units)`);
  } else {
    console.warn(`❌ Rejected: ${verdict.rejection_reason} - ${verdict.rejection_details}`);
    console.log(`💰 Saved: ${verdict.fees_saved_lamports} lamports in wasted fees.`);
  }
}

run();
```

---

## 📜 License

MIT License.

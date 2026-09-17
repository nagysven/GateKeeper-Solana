# @gatekeeper/elizaos-plugin

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![ElizaOS](https://img.shields.io/badge/ElizaOS-Plugin-purple.svg)](https://github.com/elizaos/eliza)

**Deterministic Pre-Flight Transaction Security & Gas Firewall Plugin for ElizaOS AI Agents.**

Protect your autonomous ElizaOS agents from burning treasury SOL on failed swaps, DEX reverts (`0x1771`), and account contention.

---

## ⚡ Features

- **🛡️ 0 Gas Burned on Reverts**: Catches slippage and contention errors before transactions are signed or broadcast.
- **✂️ Dynamic Compute Budget Clamping**: Injects exact compute unit limits (`simulated + 12% safety buffer`), preserving ~150k CU per trade.
- **⚡ Sub-80ms Latency**: Ultra-fast off-chain simulation against live Solana state.
- **📊 ElizaOS Context Provider**: Supplies your agent with live stats on saved gas and protected treasury capital.

---

## 🚀 Installation & Setup

### 1. Installation

```bash
npm install @gatekeeper/elizaos-plugin
```

### 2. Register in Character Configuration

Add the plugin to your ElizaOS character file:

```json
{
  "name": "DeFiGuardian",
  "plugins": ["@gatekeeper/elizaos-plugin"],
  "settings": {
    "secrets": {
      "GATEKEEPER_API_KEY": "gk_your_production_key",
      "GATEKEEPER_BASE_URL": "https://gk.ai-futures-bot.pro"
    }
  }
}
```

---

## 📜 License

MIT License.

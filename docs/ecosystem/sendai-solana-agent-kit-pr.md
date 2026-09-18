# 🛡️ Official Integration: Project Gatekeeper for Solana Agent Kit (SendAI)

> **Pull Request / Issue Proposal for [sendaifun/solana-agent-kit](https://github.com/sendaifun/solana-agent-kit)**

---

### **PR Title**:
`feat(security): Add Project Gatekeeper Pre-Flight Firewall & Dynamic CU Clamping (@gatekeeper-solana-agent-kit)`

---

### **Problem Statement**:
When autonomous AI agents execute token swaps on Solana (via Raydium, Orca, or Jupiter), they suffer from three critical pain points:
1. **Capital Burn on DEX Reverts:** When market conditions shift between LLM inference and on-chain inclusion, DEX transactions fail due to slippage violation (e.g. Raydium `0x1771`). Despite failing, the agent pays base fees, priority fees, and Jito tips. For high-frequency agents, this burns **8–15% of the total treasury balance**.
2. **Compute Budget Waste:** Default Solana SDK transactions request **200,000 Compute Units (CU)**, even when a simple swap consumes only ~43,000 CU. This artificially drives up priority fees and congests the block.
3. **No Off-Chain Arbitration:** Agents blindly broadcast raw transactions without verifying cluster contention, expired blockhashes, or price impact before signature.

---

### **Solution: Project Gatekeeper**:
We built **`gatekeeper-solana-agent-kit`** — the deterministic off-chain pre-flight transaction firewall and CU clamp for autonomous Solana AI agents.

* **🛡️ 0 Gas Burned on Fails:** Simulates the proposed swap off-chain against live RPC cluster state. If slippage violation or contention is detected, it triggers a `HARD_ABORT` *before* the agent signs, preserving 100% of transaction fees and tips.
* **✂️ Dynamic CU Clamping:** Measures simulated compute consumption and injects an exact limit (`simulated + 12% safety buffer`), saving ~150,000 unneeded compute units per swap.
* **⚡ Sub-80ms Fast Path:** Benchmark latency of `~74.8ms` on production infrastructure.
* **📦 Live npm Package:** [`gatekeeper-solana-agent-kit`](https://www.npmjs.com/package/gatekeeper-solana-agent-kit) (v0.1.1)

---

### **Integration Options**:

#### Option 1: Standard Tools Injection (LangChain & Vercel AI SDK)
```typescript
import { SolanaAgentKit, createSolanaTools } from "solana-agent-kit";
import { createGatekeeperTools } from "gatekeeper-solana-agent-kit";

const agent = SolanaAgentKit.fromKeypair(keypair, rpcUrl);

// Instantiate Gatekeeper Pre-Flight Firewall
const gatekeeperTools = createGatekeeperTools({
  apiKey: process.env.GATEKEEPER_API_KEY,
  baseUrl: "https://gk.ai-futures-bot.pro", // High-speed gateway (10,000 free checks/month)
});

// Combine with standard tools
const tools = [
  ...createSolanaTools(agent),
  ...gatekeeperTools,
];
```

#### Option 2: Solana Agent Kit v2 Plugin Architecture
```typescript
import { SolanaAgentKit } from "solana-agent-kit";
import { GatekeeperPlugin } from "gatekeeper-solana-agent-kit";

const agent = new SolanaAgentKit(...)
  .use(GatekeeperPlugin({
    apiKey: process.env.GATEKEEPER_API_KEY,
  }));
```

---

### **Tool Action Interface**:

* **Action Name**: `gatekeeper_preflight_check`
* **Input Schema (Zod)**:
  - `inputMint`: Base58 mint address of source token
  - `outputMint`: Base58 mint address of destination token
  - `amount`: Token quantity in atomic units (Lamports)
  - `maxSlippageBps`: Slippage tolerance in basis points (default: 50 bps = 0.5%)
  - `priorityFeeCapLamports`: Optional maximum fee cap

* **Execution Verdicts**:
  - **`APPROVED`**: Swap is cleared for on-chain broadcast. Returns exact `clampedComputeUnits` (e.g. `49,078 CU`) and `clampedCuSaved` (e.g. `150,922 CU`).
  - **`HARD_ABORT`**: Swap would fail on-chain. Returns `gasPaidOnChain: 0` and exact `feesSavedLamports`, halting execution before signature.

---

### **Verifiable Production Benchmarks**:
- **Gateway**: Live at [https://gk.ai-futures-bot.pro](https://gk.ai-futures-bot.pro)
- **Public Metrics API**: `GET https://gk.ai-futures-bot.pro/api/v1/public/metrics`
- **Audit Ledger**: SQLite-WAL logging sub-ms execution metrics.
- **Test Suite**: Automated unit & smoke tests passing (`npm test` in `gatekeeper-solana-agent-kit`).

### **Links & Resources**:
- npm Package: [https://www.npmjs.com/package/gatekeeper-solana-agent-kit](https://www.npmjs.com/package/gatekeeper-solana-agent-kit)
- Python SDK on PyPI: [https://pypi.org/project/gatekeeper-solana/](https://pypi.org/project/gatekeeper-solana/)
- Core Repository: [https://github.com/nagysven/GateKeeper-Solana](https://github.com/nagysven/GateKeeper-Solana)
- Developer Portal: [https://gk.ai-futures-bot.pro](https://gk.ai-futures-bot.pro)

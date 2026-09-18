/**
 * Project Gatekeeper + Solana Agent Kit (SendAI) Example
 * ======================================================
 * Demonstrates how an autonomous AI agent created with SolanaAgentKit
 * is shielded by the Gatekeeper Pre-Flight Firewall (gatekeeper-solana-agent-kit).
 *
 * Requirements:
 *   npm install solana-agent-kit gatekeeper-solana-agent-kit
 */

import { Keypair } from "@solana/web3.js";
import { SolanaAgentKit, createSolanaTools } from "solana-agent-kit";
import { createGatekeeperTools, GatekeeperPlugin } from "gatekeeper-solana-agent-kit";
import bs58 from "bs58";

async function main() {
  console.log("==========================================================");
  console.log("🛡️  INITIALIZING SOLANA AGENT KIT WITH GATEKEEPER FIREWALL ");
  console.log("==========================================================");

  // 1. Mock Keypair for demonstration (use process.env.SOLANA_PRIVATE_KEY in production)
  const keypair = Keypair.generate();
  console.log(`🤖 Agent Public Key: ${keypair.publicKey.toBase58()}`);

  // 2. Initialize the Solana Agent Kit
  const agent = SolanaAgentKit.fromKeypair(
    keypair,
    process.env.RPC_URL || "https://api.mainnet-beta.solana.com",
    { OPENAI_API_KEY: process.env.OPENAI_API_KEY || "mock-key" }
  );

  // 3. Instantiate Gatekeeper Pre-Flight Firewall Tools
  // Free tier included: 10,000 checks/month at https://gk.ai-futures-bot.pro
  const gatekeeperTools = createGatekeeperTools({
    apiKey: process.env.GATEKEEPER_API_KEY || "gk_production_key",
    baseUrl: "https://gk.ai-futures-bot.pro",
  });

  // 4. Combine standard Solana tools with Gatekeeper Firewall actions
  const allTools = [
    ...createSolanaTools(agent),
    ...gatekeeperTools,
  ];

  console.log(`✅ Loaded ${allTools.length} tools into Agent Runtime.`);
  console.log(`🛡️  Action 'gatekeeper_preflight_check' is active.`);

  // 5. Example Execution: Test Pre-Flight Evaluation
  const preflightAction = gatekeeperTools[0];
  console.log("\n🧪 Executing Pre-Flight Check on proposed Swap (SOL -> USDC)...");

  const verdict = await preflightAction.handler(agent, {
    inputMint: "So11111111111111111111111111111111111111112",
    outputMint: "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    amount: 100_000_000, // 0.1 SOL
    maxSlippageBps: 50,  // 0.50%
  });

  console.log("\n--- Gatekeeper Verdict ---");
  console.log(`Status:               ${verdict.status}`);
  console.log(`Clamped Compute Units: ${verdict.clampedComputeUnits} CU`);
  console.log(`Compute Units Saved:   ${verdict.clampedCuSaved} CU`);
  console.log(`Message:              ${verdict.message}`);
  console.log("--------------------------");
}

main().catch(console.error);

import { GatekeeperApiClient } from "../client";
import { Action, HandlerCallback, IAgentRuntime, Memory, State } from "../types";

export const evaluateIntentAction: Action = {
  name: "GATEKEEPER_PREFLIGHT",
  similes: [
    "CHECK_SWAP_SAFETY",
    "VERIFY_TRANSACTION",
    "PREFLIGHT_SWAP",
    "SIMULATE_INTENT",
    "GATEKEEPER_CHECK",
  ],
  description:
    "Simulates a proposed Solana swap off-chain via Gatekeeper. Dynamically clamps compute budget limits and aborts failing routes before broadcasting to Solana, preserving 100% of gas fees on reverts.",

  validate: async (runtime: IAgentRuntime, message: Memory, _state?: State): Promise<boolean> => {
    const text = message.content.text.toLowerCase();
    return (
      text.includes("swap") ||
      text.includes("trade") ||
      text.includes("preflight") ||
      text.includes("gatekeeper") ||
      text.includes("buy") ||
      text.includes("sell")
    );
  },

  handler: async (
    runtime: IAgentRuntime,
    message: Memory,
    state?: State,
    _options?: any,
    callback?: HandlerCallback
  ): Promise<boolean> => {
    const apiKey = runtime.getSetting("GATEKEEPER_API_KEY");
    const baseUrl =
      runtime.getSetting("GATEKEEPER_API_URL") ||
      runtime.getSetting("GATEKEEPER_BASE_URL") ||
      "https://gk.ai-futures-bot.pro";

    const client = new GatekeeperApiClient(apiKey, baseUrl);

    // Default parameters if not parsed from state
    const tokenIn = state?.tokenIn || "So11111111111111111111111111111111111111112"; // SOL
    const tokenOut = state?.tokenOut || "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"; // USDC
    const amountIn = Number(state?.amountIn || 100_000_000); // 0.1 SOL
    const maxSlippageBps = Number(state?.maxSlippageBps || 50);

    try {
      const verdict = await client.evaluatePreflight({
        token_in: tokenIn,
        token_out: tokenOut,
        amount_in: amountIn,
        max_slippage_bps: maxSlippageBps,
      });

      if (verdict.decision === "APPROVED") {
        const responseText = `🛡️ [Gatekeeper Pre-Flight] APPROVED in ${verdict.execution_time_ms}ms via ${verdict.selected_route || "DEX"}.\n• Clamped CU Limit: ${verdict.clamped_compute_units} (Saved: ${verdict.clamped_cu_saved.toLocaleString()} CU vs standard limit).\n• Ready for safe on-chain dispatch.`;

        if (callback) {
          await callback({
            text: responseText,
            content: { verdict },
            action: "GATEKEEPER_APPROVED",
          });
        }
        return true;
      } else {
        const feesSol = (verdict.fees_saved_lamports / 1e9).toFixed(6);
        const responseText = `🛡️ [Gatekeeper Pre-Flight] HARD_ABORT triggered in ${verdict.execution_time_ms}ms!\n• Reason: ${verdict.rejection_reason || "REVERT_PREVENTED"}\n• Details: ${verdict.rejection_details || "Slippage or contention violation"}\n• On-Chain Gas Paid: 0 Lamports (0.00 SOL verbrannt)\n• Preserved Fees: ${feesSol} SOL saved in agent treasury.`;

        if (callback) {
          await callback({
            text: responseText,
            content: { verdict },
            action: "GATEKEEPER_REJECTED",
          });
        }
        return false;
      }
    } catch (err: any) {
      if (callback) {
        await callback({
          text: `⚠️ Gatekeeper evaluation failed: ${err.message}`,
          content: { error: err.message },
        });
      }
      return false;
    }
  },

  examples: [
    [
      {
        user: "{{user1}}",
        content: { text: "Swap 0.5 SOL for USDC with maximum 0.5% slippage" },
      },
      {
        user: "{{agentName}}",
        content: {
          text: "Running deterministic pre-flight evaluation via Gatekeeper...",
          action: "GATEKEEPER_PREFLIGHT",
        },
      },
    ],
  ],
};

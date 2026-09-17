import { z } from "zod";
import { GatekeeperClient } from "../client";
import { GatekeeperConfig, SendAIAction } from "../types";

export const GatekeeperPreflightInputSchema = z.object({
  inputMint: z
    .string()
    .describe("Base58 mint address of the source token to swap from (e.g. So11111111111111111111111111111111111111112 for SOL)"),
  outputMint: z
    .string()
    .describe("Base58 mint address of the destination token to receive (e.g. EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v for USDC)"),
  amount: z
    .number()
    .positive()
    .describe("Amount of input tokens in base atomic units (e.g. Lamports for SOL)"),
  maxSlippageBps: z
    .number()
    .min(1)
    .max(10000)
    .default(50)
    .describe("Maximum allowed slippage in basis points (50 bps = 0.5%)"),
  priorityFeeCapLamports: z
    .number()
    .nonnegative()
    .default(100000)
    .optional()
    .describe("Maximum priority fee in Lamports the agent is willing to pay"),
  userWallet: z
    .string()
    .optional()
    .describe("Optional trader wallet address"),
});

export type GatekeeperPreflightInput = z.infer<typeof GatekeeperPreflightInputSchema>;

export function createGatekeeperPreflightAction(config?: GatekeeperConfig): SendAIAction {
  const client = new GatekeeperClient(
    config?.apiKey || process.env.GATEKEEPER_API_KEY,
    config?.baseUrl || process.env.GATEKEEPER_API_URL || "https://gk.ai-futures-bot.pro"
  );

  return {
    name: "gatekeeper_preflight_check",
    description:
      "Deterministic Pre-Flight Transaction Security & Gas Firewall. Simulates a proposed Solana swap off-chain via Gatekeeper to prevent burned gas on DEX reverts (0x1771), dynamically clamps compute budget limits, and guarantees 0 gas burned on failed trades.",
    similes: [
      "verify_solana_swap",
      "check_swap_revert",
      "preflight_solana_trade",
      "gatekeeper_preflight",
      "safe_swap_check",
    ],
    schema: GatekeeperPreflightInputSchema,
    examples: [
      [
        {
          input: {
            inputMint: "So11111111111111111111111111111111111111112",
            outputMint: "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            amount: 100000000,
            maxSlippageBps: 50,
          },
          output: {
            status: "APPROVED",
            decision: "APPROVED",
            clampedComputeUnits: 49078,
            clampedCuSaved: 150922,
            feesSavedLamports: 0,
            message: "Trade intent approved: 150,922 compute units saved via dynamic clamping. Safe to dispatch.",
          },
          explanation: "Pre-flight evaluation clears swap for on-chain dispatch with clamped compute budget.",
        },
      ],
    ],
    handler: async (_agent: any, input: Record<string, any>) => {
      // Normalize snake_case or camelCase
      const normalizedInput = {
        inputMint: input.inputMint || input.input_mint,
        outputMint: input.outputMint || input.output_mint,
        amount: input.amount,
        maxSlippageBps: input.maxSlippageBps || input.max_slippage_bps || input.max_slippage || 50,
        priorityFeeCapLamports:
          input.priorityFeeCapLamports || input.priority_fee_cap_lamports || 100000,
        userWallet: input.userWallet || input.user_wallet,
      };

      const parsed = GatekeeperPreflightInputSchema.parse(normalizedInput);

      const verdict = await client.evaluatePreflight({
        token_in: parsed.inputMint,
        token_out: parsed.outputMint,
        amount_in: parsed.amount,
        max_slippage_bps: parsed.maxSlippageBps,
        priority_fee_cap_lamports: parsed.priorityFeeCapLamports,
        user_wallet: parsed.userWallet,
      });

      if (verdict.decision === "APPROVED") {
        return {
          status: "APPROVED",
          decision: "APPROVED",
          action: "DISPATCH",
          executionTimeMs: verdict.execution_time_ms,
          clampedComputeUnits: verdict.clamped_compute_units,
          clampedCuSaved: verdict.clamped_cu_saved,
          selectedRoute: verdict.selected_route,
          estimatedHops: verdict.estimated_hops,
          feesSavedLamports: 0,
          feesSavedSol: "0.000000",
          gasPaidOnChain: 0,
          message: `Gatekeeper Pre-Flight APPROVED in ${verdict.execution_time_ms}ms via ${verdict.selected_route || "DEX"}. Clamped CU Limit: ${verdict.clamped_compute_units} (Saved: ${verdict.clamped_cu_saved.toLocaleString()} CU vs default). Safe to dispatch.`,
          verdict,
        };
      } else {
        const feesSol = (verdict.fees_saved_lamports / 1e9).toFixed(6);
        return {
          status: "HARD_ABORT",
          decision: "REJECTED",
          action: "HARD_ABORT",
          executionTimeMs: verdict.execution_time_ms,
          rejectionReason: verdict.rejection_reason || "REVERT_PREVENTED",
          rejectionDetails: verdict.rejection_details || "Slippage or contention violation",
          clampedComputeUnits: 0,
          clampedCuSaved: 0,
          feesSavedLamports: verdict.fees_saved_lamports,
          feesSavedSol: feesSol,
          gasPaidOnChain: 0,
          message: `Gatekeeper HARD_ABORT triggered in ${verdict.execution_time_ms}ms! Revert prevented: ${verdict.rejection_reason}. 0 gas burned on-chain. Preserved ${feesSol} SOL in treasury.`,
          verdict,
        };
      }
    },
  };
}

import { z } from "zod";

// Solana Agent Kit Action Interface
export interface SendAIActionExample {
  input: Record<string, any>;
  output: Record<string, any>;
  explanation?: string;
}

export interface SendAIAction {
  name: string;
  description: string;
  similes?: string[];
  examples?: SendAIActionExample[][];
  schema: z.ZodObject<any>;
  handler: (agent: any, input: Record<string, any>) => Promise<any>;
}

// Gatekeeper Client Types
export interface GatekeeperConfig {
  apiKey?: string;
  baseUrl?: string;
}

export interface GatekeeperPreflightRequest {
  token_in: string;
  token_out: string;
  amount_in: number;
  max_slippage_bps?: number;
  priority_fee_cap_lamports?: number;
  user_wallet?: string;
  min_amount_out?: number;
  created_at_slot?: number;
  valid_until_slot?: number;
}

export interface GatekeeperVerdict {
  intent_id: string;
  decision: "APPROVED" | "REJECTED";
  action: "DISPATCH" | "HARD_ABORT";
  simulated_compute_units: number;
  clamped_compute_units: number;
  execution_time_ms: number;
  selected_route?: string | null;
  estimated_hops: number;
  clamped_cu_saved: number;
  fees_saved_lamports: number;
  rejection_reason?: string | null;
  rejection_details?: string | null;
  candidates_evaluated: number;
}

export interface GatekeeperSavingsMetrics {
  total_evaluations: number;
  total_dispatched: number;
  total_hard_aborts: number;
  total_fees_saved_lamports: number;
  total_fees_saved_sol: number;
  base_fee_saved_lamports: number;
  priority_fee_saved_lamports: number;
  jito_tip_saved_lamports: number;
  capital_saved_lamports: number;
  capital_saved_sol: number;
  clamped_cu_saved_units: number;
  avg_decision_latency_ms: number;
}

// ElizaOS Core Interfaces
export interface Memory {
  id?: string;
  userId?: string;
  agentId?: string;
  createdAt?: number;
  content: {
    text: string;
    action?: string;
    source?: string;
    [key: string]: any;
  };
  roomId?: string;
  embedding?: number[];
}

export interface State {
  bio?: string;
  lore?: string;
  messageDirections?: string;
  postDirections?: string;
  roomId?: string;
  actors?: string;
  recentMessages?: string;
  recentMessagesData?: Memory[];
  [key: string]: any;
}

export interface IAgentRuntime {
  getSetting(key: string): string | undefined;
  composeState?(message: Memory, additionalKeys?: Record<string, any>): Promise<State>;
  updateRecentMessageState?(state: State): Promise<State>;
  [key: string]: any;
}

export type HandlerCallback = (
  response: {
    text: string;
    content?: any;
    action?: string;
  },
  files?: any[]
) => Promise<any>;

export interface ActionExample {
  user: string;
  content: {
    text: string;
    action?: string;
    [key: string]: any;
  };
}

export interface Action {
  name: string;
  similes: string[];
  description: string;
  validate: (runtime: IAgentRuntime, message: Memory, state?: State) => Promise<boolean>;
  handler: (
    runtime: IAgentRuntime,
    message: Memory,
    state?: State,
    options?: any,
    callback?: HandlerCallback
  ) => Promise<boolean | any>;
  examples: ActionExample[][];
}

export interface Provider {
  get: (runtime: IAgentRuntime, message: Memory, state?: State) => Promise<string | null>;
}

export interface Plugin {
  name: string;
  description: string;
  actions: Action[];
  evaluators?: any[];
  providers?: Provider[];
  services?: any[];
}

// Gatekeeper Specific Models
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

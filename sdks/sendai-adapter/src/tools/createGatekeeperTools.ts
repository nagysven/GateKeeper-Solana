import { createGatekeeperPreflightAction } from "../actions/gatekeeperPreflight";
import { GatekeeperConfig, SendAIAction } from "../types";

/**
 * Creates and registers Gatekeeper security actions for SendAI / Solana Agent Kit.
 *
 * Usage with SolanaAgentKit:
 * ```typescript
 * import { SolanaAgentKit } from "solana-agent-kit";
 * import { createGatekeeperTools } from "@gatekeeper/solana-agent-kit";
 *
 * const agent = new SolanaAgentKit(...);
 * const gatekeeperTools = createGatekeeperTools({
 *   apiKey: process.env.GATEKEEPER_API_KEY,
 *   baseUrl: "https://gk.ai-futures-bot.pro"
 * });
 * ```
 */
export function createGatekeeperTools(config?: GatekeeperConfig): SendAIAction[] {
  return [createGatekeeperPreflightAction(config)];
}

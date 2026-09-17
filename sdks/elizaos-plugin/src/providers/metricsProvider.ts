import { GatekeeperApiClient } from "../client";
import { IAgentRuntime, Memory, Provider, State } from "../types";

export const gatekeeperSavingsProvider: Provider = {
  get: async (runtime: IAgentRuntime, _message: Memory, _state?: State): Promise<string | null> => {
    const apiKey = runtime.getSetting("GATEKEEPER_API_KEY");
    const baseUrl = runtime.getSetting("GATEKEEPER_BASE_URL") || "https://gk.ai-futures-bot.pro";

    try {
      const client = new GatekeeperApiClient(apiKey, baseUrl);
      const metrics = await client.getSavingsMetrics();

      return `[Gatekeeper Security Layer Active]
- Total Protected Evaluations: ${metrics.total_evaluations}
- Hard Aborts Intercepted (0 Gas Burned): ${metrics.total_hard_aborts}
- Compute Units Preserved: ${metrics.clamped_cu_saved_units.toLocaleString()} CU
- Preserved Capital: ${metrics.capital_saved_sol.toFixed(4)} SOL
- Average Firewall Latency: ${metrics.avg_decision_latency_ms.toFixed(1)}ms`;
    } catch (err) {
      return null;
    }
  },
};

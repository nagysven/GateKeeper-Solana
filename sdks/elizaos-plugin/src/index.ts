import { evaluateIntentAction } from "./actions/evaluateIntent";
import { gatekeeperSavingsProvider } from "./providers/metricsProvider";
import { Plugin } from "./types";

export const gatekeeperPlugin: Plugin = {
  name: "gatekeeper",
  description:
    "Deterministic Pre-Flight Transaction Security & Gas Firewall for Autonomous Solana AI Agents. Intercepts DEX reverts, clamps compute limits, and guarantees 0 gas burned on failed intents.",
  actions: [evaluateIntentAction],
  providers: [gatekeeperSavingsProvider],
  evaluators: [],
};

export default gatekeeperPlugin;
export * from "./types";
export * from "./client";
export * from "./actions/evaluateIntent";
export * from "./providers/metricsProvider";

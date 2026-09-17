import { GatekeeperAuthError, GatekeeperError, GatekeeperRateLimitError } from "./errors";
import { GatekeeperConfig, PreflightRequest, PreflightResponse, SavingsMetrics } from "./types";

export class GatekeeperClient {
  private apiKey: string;
  private baseUrl: string;
  private timeoutMs: number;

  constructor(config: GatekeeperConfig) {
    if (!config.apiKey) {
      throw new GatekeeperError("API key is required to instantiate GatekeeperClient.");
    }
    this.apiKey = config.apiKey.trim();
    this.baseUrl = (config.baseUrl || "https://gk.ai-futures-bot.pro").replace(/\/+$/, "");
    this.timeoutMs = config.timeoutMs || 10000;
  }

  private getHeaders(): Record<string, string> {
    return {
      "Content-Type": "application/json",
      "X-Gatekeeper-Key": this.apiKey,
      "User-Agent": "@gatekeeper/solana-sdk/0.1.0",
    };
  }

  public async checkHealth(): Promise<{ status: string; service: string; version: string }> {
    const res = await fetch(`${this.baseUrl}/health`, {
      method: "GET",
      signal: AbortSignal.timeout(this.timeoutMs),
    });
    if (!res.ok) {
      throw new GatekeeperError(`Health check failed with HTTP ${res.status}`);
    }
    return res.json() as Promise<{ status: string; service: string; version: string }>;
  }

  public async evaluateIntent(request: PreflightRequest): Promise<PreflightResponse> {
    const res = await fetch(`${this.baseUrl}/api/v1/preflight`, {
      method: "POST",
      headers: this.getHeaders(),
      body: JSON.stringify(request),
      signal: AbortSignal.timeout(this.timeoutMs),
    });

    if (res.status === 401) {
      throw new GatekeeperAuthError();
    }
    if (res.status === 429) {
      throw new GatekeeperRateLimitError();
    }
    if (!res.ok) {
      const errText = await res.text();
      throw new GatekeeperError(`Gatekeeper API error (HTTP ${res.status}): ${errText}`);
    }

    return res.json() as Promise<PreflightResponse>;
  }

  public async getMetrics(): Promise<SavingsMetrics> {
    const res = await fetch(`${this.baseUrl}/api/v1/metrics/savings`, {
      method: "GET",
      headers: this.getHeaders(),
      signal: AbortSignal.timeout(this.timeoutMs),
    });

    if (res.status === 401) {
      throw new GatekeeperAuthError();
    }
    if (!res.ok) {
      throw new GatekeeperError(`Failed to fetch savings metrics (HTTP ${res.status})`);
    }

    return res.json() as Promise<SavingsMetrics>;
  }
}

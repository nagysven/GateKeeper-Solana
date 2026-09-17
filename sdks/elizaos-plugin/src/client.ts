import { GatekeeperPreflightRequest, GatekeeperSavingsMetrics, GatekeeperVerdict } from "./types";

export class GatekeeperApiClient {
  private apiKey: string;
  private baseUrl: string;

  constructor(apiKey?: string, baseUrl: string = "https://gk.ai-futures-bot.pro") {
    this.apiKey = (apiKey || "").trim();
    this.baseUrl = baseUrl.replace(/\/+$/, "");
  }

  private getHeaders(): Record<string, string> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      "User-Agent": "@gatekeeper/elizaos-plugin/0.1.0",
    };
    if (this.apiKey) {
      headers["X-Gatekeeper-Key"] = this.apiKey;
    }
    return headers;
  }

  public async evaluatePreflight(request: GatekeeperPreflightRequest): Promise<GatekeeperVerdict> {
    const url = `${this.baseUrl}/api/v1/preflight`;
    const res = await fetch(url, {
      method: "POST",
      headers: this.getHeaders(),
      body: JSON.stringify(request),
    });

    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`Gatekeeper API error HTTP ${res.status}: ${errText}`);
    }

    return res.json() as Promise<GatekeeperVerdict>;
  }

  public async getSavingsMetrics(): Promise<GatekeeperSavingsMetrics> {
    // Try public endpoint first, fall back to authenticated savings route
    let res = await fetch(`${this.baseUrl}/api/v1/public/metrics`, {
      method: "GET",
      headers: this.getHeaders(),
    });

    if (!res.ok) {
      res = await fetch(`${this.baseUrl}/api/v1/metrics/savings`, {
        method: "GET",
        headers: this.getHeaders(),
      });
    }

    if (!res.ok) {
      throw new Error(`Failed to fetch Gatekeeper metrics (HTTP ${res.status})`);
    }

    return res.json() as Promise<GatekeeperSavingsMetrics>;
  }
}

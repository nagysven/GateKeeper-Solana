import { GatekeeperPreflightRequest, GatekeeperSavingsMetrics, GatekeeperVerdict } from "./types";

export class GatekeeperClient {
  private apiKey: string;
  private baseUrl: string;

  constructor(apiKey?: string, baseUrl: string = "https://gk.ai-futures-bot.pro") {
    this.apiKey = (apiKey || "").trim();
    this.baseUrl = baseUrl.replace(/\/+$/, "");
  }

  private getHeaders(): Record<string, string> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      "User-Agent": "@gatekeeper/solana-agent-kit/0.1.0",
    };
    if (this.apiKey) {
      headers["X-Gatekeeper-Key"] = this.apiKey;
    }
    return headers;
  }

  public async evaluatePreflight(request: GatekeeperPreflightRequest): Promise<GatekeeperVerdict> {
    let url: string;
    if (this.baseUrl.includes("/preflight") || this.baseUrl.includes("/evaluate")) {
      url = this.baseUrl;
    } else if (this.baseUrl.endsWith("/api/v1")) {
      url = `${this.baseUrl}/preflight`;
    } else {
      url = `${this.baseUrl}/api/v1/preflight`;
    }

    const res = await fetch(url, {
      method: "POST",
      headers: this.getHeaders(),
      body: JSON.stringify(request),
    });

    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`Gatekeeper API error HTTP ${res.status}: ${errText}`);
    }

    const data: any = await res.json();
    const isApproved =
      data.decision === "APPROVED" ||
      data.action === "DISPATCH" ||
      data.is_valid === true;

    return {
      intent_id: data.intent_id || "intent-sendai",
      decision: isApproved ? "APPROVED" : "REJECTED",
      action: isApproved ? "DISPATCH" : "HARD_ABORT",
      simulated_compute_units:
        data.simulated_compute_units || data.clamped_compute_units || 0,
      clamped_compute_units: data.clamped_compute_units || 0,
      execution_time_ms: data.execution_time_ms || data.decision_latency_ms || 0,
      selected_route:
        data.selected_route ||
        (data.selected_candidate ? data.selected_candidate.dex_type : null),
      estimated_hops: data.estimated_hops || 1,
      clamped_cu_saved: data.clamped_cu_saved || data.clamped_cu_saved_units || 0,
      fees_saved_lamports:
        data.fees_saved_lamports ||
        (data.base_fee_saved_lamports
          ? data.base_fee_saved_lamports + (data.priority_fee_saved_lamports || 0)
          : 0),
      rejection_reason: data.rejection_reason || data.abort_reason || null,
      rejection_details: data.rejection_details || data.abort_details || null,
      candidates_evaluated: data.candidates_evaluated || 1,
    };
  }

  public async getSavingsMetrics(): Promise<GatekeeperSavingsMetrics> {
    const base = this.baseUrl.replace(/\/api\/v1.*$/, "");
    let res = await fetch(`${base}/api/v1/public/metrics`, {
      method: "GET",
      headers: this.getHeaders(),
    });

    if (!res.ok) {
      res = await fetch(`${base}/api/v1/metrics/savings`, {
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

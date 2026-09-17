export class GatekeeperError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "GatekeeperError";
  }
}

export class GatekeeperAuthError extends GatekeeperError {
  constructor(message: string = "Invalid or missing X-Gatekeeper-Key.") {
    super(message);
    this.name = "GatekeeperAuthError";
  }
}

export class GatekeeperRateLimitError extends GatekeeperError {
  constructor(message: string = "Monthly quota or rate limit exceeded.") {
    super(message);
    this.name = "GatekeeperRateLimitError";
  }
}

export class GatekeeperRejectionError extends GatekeeperError {
  public reason: string;
  public details?: string;
  public feesSavedLamports: number;

  constructor(reason: string, details?: string, feesSavedLamports: number = 0) {
    super(`Trade intent rejected by Gatekeeper: ${reason} (${details || "No details"})`);
    this.name = "GatekeeperRejectionError";
    this.reason = reason;
    this.details = details;
    this.feesSavedLamports = feesSavedLamports;
  }
}

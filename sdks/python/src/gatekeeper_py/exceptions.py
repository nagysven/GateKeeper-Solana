class GatekeeperError(Exception):
    """Base exception for all Gatekeeper SDK errors."""
    pass


class GatekeeperAuthError(GatekeeperError):
    """Raised when API key is missing, invalid, or unauthorized (HTTP 401)."""
    pass


class GatekeeperRateLimitError(GatekeeperError):
    """Raised when request quota or rate limit is exceeded (HTTP 429)."""
    pass


class GatekeeperConnectionError(GatekeeperError):
    """Raised when communication with the Gatekeeper gateway fails."""
    pass


class GatekeeperRejectionError(GatekeeperError):
    """Raised when a pre-flight evaluation rejects the trade intent."""

    def __init__(
        self,
        reason: str,
        details: str | None = None,
        cu_saved: int = 0,
        fees_saved: int = 0,
    ):
        super().__init__(f"Trade intent rejected by Gatekeeper: {reason} ({details or 'No details'})")
        self.reason = reason
        self.details = details
        self.cu_saved = cu_saved
        self.fees_saved = fees_saved

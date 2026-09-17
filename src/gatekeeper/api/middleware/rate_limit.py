import time
from typing import Dict, Optional, Set
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class TokenBucket:
    """In-memory Token-Bucket rate limiter per client/API-key."""

    def __init__(
        self,
        capacity: float = 5.0,
        refill_rate: float = 5.0,
        monthly_quota: int = 10_000,
    ):
        self.capacity = float(capacity)
        self.refill_rate = float(refill_rate)
        self.tokens = float(capacity)
        self.last_update = time.time()
        self.monthly_quota = int(monthly_quota)
        self.month_key = time.strftime("%Y-%m")
        self.monthly_count = 0

    def consume(self) -> tuple[bool, Optional[str], float, int]:
        """Consumes a token if available.

        Returns:
            (allowed: bool, reason: str | None, retry_after: float, remaining_monthly: int)
        """
        now = time.time()
        # 1. Check & roll over monthly counter
        current_month = time.strftime("%Y-%m")
        if current_month != self.month_key:
            self.month_key = current_month
            self.monthly_count = 0

        # 2. Check monthly quota
        if self.monthly_count >= self.monthly_quota:
            return (
                False,
                f"Monthly quota of {self.monthly_quota:,} requests exceeded.",
                86400.0,
                0,
            )

        # 3. Refill bucket based on elapsed time
        elapsed = max(0.0, now - self.last_update)
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_update = now

        # 4. Check peak capacity (5 req/s)
        if self.tokens < 1.0:
            retry_after = round((1.0 - self.tokens) / self.refill_rate, 2)
            remaining_monthly = max(0, self.monthly_quota - self.monthly_count)
            return (
                False,
                f"Peak burst rate limit exceeded (max {int(self.capacity)} req/s).",
                max(0.1, retry_after),
                remaining_monthly,
            )

        # 5. Consume token & increment monthly count
        self.tokens -= 1.0
        self.monthly_count += 1
        remaining_monthly = max(0, self.monthly_quota - self.monthly_count)
        return True, None, 0.0, remaining_monthly


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI/Starlette middleware enforcing Token-Bucket rate limits."""

    def __init__(
        self,
        app,
        capacity: float = 5.0,
        refill_rate: float = 5.0,
        monthly_quota: int = 10_000,
        exempt_paths: Optional[Set[str]] = None,
    ):
        super().__init__(app)
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.monthly_quota = monthly_quota
        self.exempt_paths = exempt_paths or {
            "/",
            "/health",
            "/favicon.ico",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/api/v1/public/metrics",
        }
        self.buckets: Dict[str, TokenBucket] = {}

    def _get_client_key(self, request: Request) -> str:
        """Determines client identifier: API key or remote IP."""
        api_key = request.headers.get("X-Gatekeeper-Key")
        if api_key:
            return f"key:{api_key.strip()}"
        client_host = request.client.host if request.client else "unknown"
        return f"ip:{client_host}"

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Exempt public routes
        path = request.url.path
        if path in self.exempt_paths:
            return await call_next(request)

        client_key = self._get_client_key(request)
        if client_key not in self.buckets:
            self.buckets[client_key] = TokenBucket(
                capacity=self.capacity,
                refill_rate=self.refill_rate,
                monthly_quota=self.monthly_quota,
            )

        bucket = self.buckets[client_key]
        allowed, reason, retry_after, remaining = bucket.consume()

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "TooManyRequests",
                    "detail": reason,
                    "retry_after_seconds": retry_after,
                },
                headers={
                    "X-RateLimit-Limit": str(self.monthly_quota),
                    "X-RateLimit-Remaining": str(remaining),
                    "Retry-After": str(int(retry_after) + 1),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.monthly_quota)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response

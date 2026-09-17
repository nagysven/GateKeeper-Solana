import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from gatekeeper.api.middleware.rate_limit import RateLimitMiddleware, TokenBucket


def test_token_bucket_consume():
    bucket = TokenBucket(capacity=3.0, refill_rate=1.0, monthly_quota=10)
    allowed, reason, retry_after, remaining = bucket.consume()
    assert allowed is True
    assert remaining == 9

    allowed, _, _, remaining = bucket.consume()
    assert allowed is True
    assert remaining == 8

    allowed, _, _, remaining = bucket.consume()
    assert allowed is True
    assert remaining == 7

    # 4th request without delay should hit burst limit
    allowed, reason, retry_after, remaining = bucket.consume()
    assert allowed is False
    assert "Peak burst" in reason
    assert retry_after > 0


def test_token_bucket_monthly_quota():
    bucket = TokenBucket(capacity=100.0, refill_rate=100.0, monthly_quota=2)
    allowed, _, _, _ = bucket.consume()
    assert allowed is True
    allowed, _, _, _ = bucket.consume()
    assert allowed is True

    # 3rd request exceeds monthly quota
    allowed, reason, retry_after, _ = bucket.consume()
    assert allowed is False
    assert "Monthly quota" in reason


def test_rate_limit_middleware_headers():
    async def sample_endpoint(request):
        return JSONResponse({"status": "ok"})

    app = Starlette(
        routes=[Route("/test", sample_endpoint)],
    )
    app.add_middleware(
        RateLimitMiddleware,
        capacity=2.0,
        refill_rate=1.0,
        monthly_quota=10,
    )

    client = TestClient(app)
    resp1 = client.get("/test", headers={"X-Gatekeeper-Key": "test_user"})
    assert resp1.status_code == 200
    assert resp1.headers["X-RateLimit-Limit"] == "10"
    assert resp1.headers["X-RateLimit-Remaining"] == "9"

    resp2 = client.get("/test", headers={"X-Gatekeeper-Key": "test_user"})
    assert resp2.status_code == 200
    assert resp2.headers["X-RateLimit-Remaining"] == "8"

    # 3rd request immediately should trigger 429
    resp3 = client.get("/test", headers={"X-Gatekeeper-Key": "test_user"})
    assert resp3.status_code == 429
    assert resp3.json()["error"] == "TooManyRequests"


def test_exempt_paths_not_rate_limited():
    async def health_endpoint(request):
        return JSONResponse({"status": "healthy"})

    app = Starlette(
        routes=[Route("/health", health_endpoint)],
    )
    app.add_middleware(
        RateLimitMiddleware,
        capacity=1.0,
        refill_rate=0.1,
        monthly_quota=2,
    )

    client = TestClient(app)
    # Multiple requests to /health should never be throttled
    for _ in range(5):
        resp = client.get("/health")
        assert resp.status_code == 200

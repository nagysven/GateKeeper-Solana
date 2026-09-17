import secrets
from typing import Optional

from fastapi import HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from gatekeeper.config import settings

API_KEY_HEADER_NAME = "X-Gatekeeper-Key"
api_key_header = APIKeyHeader(name=API_KEY_HEADER_NAME, auto_error=False)


async def verify_api_key(
    request: Request,
    api_key: Optional[str] = Security(api_key_header),
) -> str:
    """Validates the incoming X-Gatekeeper-Key against the configured master key.

    Uses constant-time comparison (secrets.compare_digest) to prevent timing-attack leakage.
    Raises:
        HTTPException (401 Unauthorized): When header is absent or invalid.
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required authentication header: X-Gatekeeper-Key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Allow overriding settings from request.app.state if present (useful in test harnesses)
    expected_key = getattr(getattr(request.app, "state", None), "api_key", settings.API_KEY)

    if not secrets.compare_digest(api_key, expected_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid X-Gatekeeper-Key provided",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return api_key

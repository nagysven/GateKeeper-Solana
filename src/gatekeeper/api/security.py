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
    """Validates incoming X-Gatekeeper-Key against master key or SQLite billing ledger.

    Supports:
    1. Master API key (constant-time check).
    2. Registered Developer API keys (with monthly quota and Solana Pay bonus credits check).
    Raises:
        HTTPException (401 Unauthorized): When key is missing or invalid.
        HTTPException (429 Too Many Requests): When developer quota is exhausted.
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required authentication header: X-Gatekeeper-Key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    clean_key = api_key.strip()

    # 1. Check Master Key (constant-time comparison)
    expected_key = getattr(getattr(request.app, "state", None), "api_key", settings.API_KEY)
    if secrets.compare_digest(clean_key, expected_key):
        return clean_key

    # 2. Check SQLite Registered Developer API Keys
    try:
        from gatekeeper.storage.billing_repository import BillingRepository
        from gatekeeper.storage.database import DatabaseManager

        db_manager = getattr(request.app.state, "db_manager", None) or DatabaseManager(config=settings)
        billing_repo = BillingRepository(db_manager, settings)

        allowed, key_info = await billing_repo.check_and_increment_usage(clean_key)
        if not allowed:
            if "exhausted" in key_info.get("reason", "").lower():
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Quota of {key_info.get('allowance', 10000):,} requests exhausted. Top up credits with Solana Pay at https://gk.ai-futures-bot.pro",
                )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid X-Gatekeeper-Key (key not found or deactivated)",
                headers={"WWW-Authenticate": "ApiKey"},
            )

        request.state.api_key_data = key_info
        return clean_key

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"API key authentication error: {e}",
            headers={"WWW-Authenticate": "ApiKey"},
        )

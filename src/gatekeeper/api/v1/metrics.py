from typing import Any, Dict
from fastapi import APIRouter, Depends, Request

from gatekeeper.storage.repository import AuditLedgerRepository

router = APIRouter()


def get_repository(request: Request) -> AuditLedgerRepository:
    """Retrieves repository from app state or creates a default instance."""
    if hasattr(request.app.state, "repository"):
        return request.app.state.repository
    from gatekeeper.storage.database import DatabaseManager

    return AuditLedgerRepository(DatabaseManager())


@router.get("/savings", response_model=Dict[str, Any])
async def get_savings_metrics(
    repo: AuditLedgerRepository = Depends(get_repository),
) -> Dict[str, Any]:
    """Returns aggregated audit metrics detailing fees, tips, and capital preserved by Gatekeeper."""
    return await repo.get_savings_metrics()

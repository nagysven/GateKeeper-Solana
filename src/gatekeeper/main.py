import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from gatekeeper.api.v1 import api_v1_router
from gatekeeper.config import settings
from gatekeeper.engine.arbitrator import GatekeeperArbitrator
from gatekeeper.engine.simulator import PreFlightSimulator
from gatekeeper.storage.database import DatabaseManager
from gatekeeper.storage.repository import AuditLedgerRepository

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("gatekeeper")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifecycle management for database schema provisioning and client initialization."""
    logger.info("Initializing Gatekeeper Storage Layer...")
    db_manager = DatabaseManager(config=settings)
    await db_manager.init_db()

    # Attach instances to application state
    app.state.db_manager = db_manager
    app.state.repository = AuditLedgerRepository(db_manager)
    app.state.simulator = PreFlightSimulator(config=settings)
    app.state.arbitrator = GatekeeperArbitrator(config=settings)

    journal_mode = await db_manager.check_journal_mode()
    logger.info(
        "Gatekeeper Middleware running. SQLite WAL mode: %s | RPC URL: %s",
        journal_mode,
        settings.RPC_URL,
    )

    yield

    logger.info("Shutting down Gatekeeper Middleware.")


app = FastAPI(
    title="Project Gatekeeper",
    description="Deterministic Pre-Flight Execution Layer & Middleware for Solana",
    version="0.1.0",
    lifespan=lifespan,
)

# Register API v1 routes
app.include_router(api_v1_router)


@app.get("/health", tags=["System"])
async def health_check():
    """Liveness probe for VPS monitoring."""
    return {
        "status": "healthy",
        "service": "gatekeeper",
        "version": "0.1.0",
    }


@app.exception_handler(Exception)
async def global_exception_handler(_request: Request, exc: Exception):
    """Graceful error response for unhandled server exceptions."""
    logger.error("Unhandled exception occurred: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "InternalServerError",
            "message": str(exc),
        },
    )

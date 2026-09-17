import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.responses import HTMLResponse, JSONResponse

from gatekeeper.api.middleware.rate_limit import RateLimitMiddleware
from gatekeeper.api.v1 import api_v1_router
from gatekeeper.config import settings
from gatekeeper.engine.arbitrator import GatekeeperArbitrator
from gatekeeper.engine.candidate_generator import RouteCandidateGenerator
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

    # Attach core instances to application state
    app.state.db_manager = db_manager
    app.state.repository = AuditLedgerRepository(db_manager)
    app.state.simulator = PreFlightSimulator(config=settings)
    app.state.arbitrator = GatekeeperArbitrator(config=settings)
    app.state.candidate_generator = RouteCandidateGenerator(config=settings)

    journal_mode = await db_manager.check_journal_mode()
    logger.info(
        "Gatekeeper Middleware running on %s:%s. SQLite WAL mode: %s | RPC URL: %s",
        settings.HOST,
        settings.PORT,
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

# Register Token-Bucket Rate Limiting (5 req/s peak, 10,000 req/month)
app.add_middleware(
    RateLimitMiddleware,
    capacity=5.0,
    refill_rate=5.0,
    monthly_quota=10_000,
)

# Register API v1 routes
app.include_router(api_v1_router)

TEMPLATES_DIR = Path(__file__).parent / "templates"


@app.get("/", response_class=HTMLResponse, tags=["Developer Portal"])
async def developer_portal():
    """Minimal developer portal showcasing live Gatekeeper metrics & SDKs."""
    html_file = TEMPLATES_DIR / "index.html"
    if html_file.exists():
        return HTMLResponse(content=html_file.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Project Gatekeeper Gateway</h1>")


@app.get("/api/v1/public/metrics", tags=["Metrics"])
async def public_savings_metrics(request: Request):
    """Public unauthenticated savings metrics endpoint for the landing page showcase."""
    if hasattr(request.app.state, "repository"):
        repo = request.app.state.repository
    else:
        from gatekeeper.storage.database import DatabaseManager
        from gatekeeper.storage.repository import AuditLedgerRepository
        repo = AuditLedgerRepository(DatabaseManager())
    return await repo.get_savings_metrics()


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

from contextlib import asynccontextmanager
import logging
from pathlib import Path
from typing import AsyncGenerator, Optional
import aiosqlite

from gatekeeper.config import Settings, settings as global_settings

logger = logging.getLogger(__name__)

INIT_SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;

-- 1. Intent Requests Table
CREATE TABLE IF NOT EXISTS intents (
    intent_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    input_mint TEXT NOT NULL,
    output_mint TEXT NOT NULL,
    amount_in INTEGER NOT NULL,
    min_amount_out INTEGER NOT NULL,
    max_slippage_bps INTEGER NOT NULL,
    max_priority_fee_lamports INTEGER NOT NULL,
    jito_tip_lamports INTEGER NOT NULL DEFAULT 0,
    user_wallet TEXT NOT NULL,
    created_at_slot INTEGER NOT NULL,
    valid_until_slot INTEGER NOT NULL,
    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'PENDING'
);

-- 2. Route Candidates Table
CREATE TABLE IF NOT EXISTS route_candidates (
    candidate_id TEXT PRIMARY KEY,
    intent_id TEXT NOT NULL,
    dex_type TEXT NOT NULL,
    route_plan_json TEXT NOT NULL,
    is_split BOOLEAN DEFAULT FALSE,
    estimated_hops INTEGER DEFAULT 1,
    serialized_tx TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(intent_id) REFERENCES intents(intent_id) ON DELETE CASCADE
);

-- 3. Simulation Results Table
CREATE TABLE IF NOT EXISTS simulations (
    simulation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id TEXT NOT NULL,
    success BOOLEAN NOT NULL,
    consumed_units INTEGER NOT NULL DEFAULT 0,
    simulated_delta_out INTEGER NOT NULL DEFAULT 0,
    error_code TEXT,
    error_log TEXT,
    simulation_duration_ms REAL NOT NULL DEFAULT 0.0,
    simulated_at_slot INTEGER NOT NULL DEFAULT 0,
    simulated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(candidate_id) REFERENCES route_candidates(candidate_id) ON DELETE CASCADE
);

-- 4. Fee Savings Ledger Table
CREATE TABLE IF NOT EXISTS fee_savings_ledger (
    ledger_id INTEGER PRIMARY KEY AUTOINCREMENT,
    intent_id TEXT NOT NULL,
    action_taken TEXT NOT NULL,
    selected_candidate_id TEXT,
    aborted_candidates_count INTEGER NOT NULL DEFAULT 0,
    base_fee_saved_lamports INTEGER NOT NULL DEFAULT 0,
    priority_fee_saved_lamports INTEGER NOT NULL DEFAULT 0,
    jito_tip_saved_lamports INTEGER NOT NULL DEFAULT 0,
    total_fees_saved_lamports INTEGER NOT NULL DEFAULT 0,
    capital_saved_lamports INTEGER NOT NULL DEFAULT 0,
    clamped_cu_saved_units INTEGER NOT NULL DEFAULT 0,
    decision_latency_ms REAL NOT NULL DEFAULT 0.0,
    abort_reason TEXT,
    abort_details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(intent_id) REFERENCES intents(intent_id)
);

CREATE INDEX IF NOT EXISTS idx_intents_agent ON intents(agent_id);
CREATE INDEX IF NOT EXISTS idx_simulations_candidate ON simulations(candidate_id);
CREATE INDEX IF NOT EXISTS idx_savings_action ON fee_savings_ledger(action_taken);
"""


class DatabaseManager:
    """Manages high-throughput SQLite storage with WAL mode for the Gatekeeper VPS."""

    def __init__(self, db_path: Optional[str] = None, config: Optional[Settings] = None):
        self.config = config or global_settings
        self.db_path = db_path or self.config.DATABASE_PATH

    @asynccontextmanager
    async def get_connection(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        """Provides an asynchronous connection context manager that releases resources cleanly."""
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            if self.config.ENABLE_WAL_MODE:
                await conn.execute("PRAGMA journal_mode=WAL;")
                await conn.execute("PRAGMA synchronous=NORMAL;")
            await conn.execute("PRAGMA foreign_keys=ON;")
            yield conn

    async def init_db(self) -> None:
        """Applies schema DDL if tables do not exist."""
        db_file = Path(self.db_path)
        if db_file.parent and not db_file.parent.exists():
            db_file.parent.mkdir(parents=True, exist_ok=True)

        async with self.get_connection() as conn:
            await conn.executescript(INIT_SCHEMA_SQL)
            await conn.commit()
            logger.info("Initialized Gatekeeper SQLite storage at %s", self.db_path)

    async def check_journal_mode(self) -> str:
        """Returns the active SQLite journal mode (should be 'wal')."""
        async with self.get_connection() as conn:
            cursor = await conn.execute("PRAGMA journal_mode;")
            row = await cursor.fetchone()
            return row[0] if row else "unknown"

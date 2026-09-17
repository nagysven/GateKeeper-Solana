from pathlib import Path
import pytest

from gatekeeper.config import Settings
from gatekeeper.core.models import (
    AbortReason,
    DexType,
    IntentRequest,
    RouteCandidate,
    SimulationResult,
    ValidationResult,
)
from gatekeeper.storage.database import DatabaseManager
from gatekeeper.storage.repository import AuditLedgerRepository


@pytest.fixture
async def temp_db_repo(tmp_path: Path):
    """Provides an isolated SQLite repository using pytest's tmp_path fixture."""
    db_path = str(tmp_path / "test_ledger.db")
    settings = Settings(DATABASE_PATH=db_path, ENABLE_WAL_MODE=True)
    db_mgr = DatabaseManager(db_path=db_path, config=settings)
    await db_mgr.init_db()
    repo = AuditLedgerRepository(db_mgr)
    yield repo, db_mgr


class TestSQLiteAuditLedger:
    async def test_wal_mode_enabled(self, temp_db_repo):
        _, db_mgr = temp_db_repo
        journal_mode = await db_mgr.check_journal_mode()
        assert journal_mode.lower() == "wal"

    async def test_atomic_logging_and_savings_metrics(
        self,
        temp_db_repo,
        valid_wsol_mint: str,
        valid_usdc_mint: str,
        valid_wallet_pubkey: str,
    ):
        repo, _ = temp_db_repo

        # Initial metrics should be clean zeros
        empty_metrics = await repo.get_savings_metrics()
        assert empty_metrics["total_evaluations"] == 0
        assert empty_metrics["total_fees_saved_lamports"] == 0

        # Create test intent 1 (Dispatched)
        intent1 = IntentRequest(
            agent_id="agent-alpha",
            input_mint=valid_wsol_mint,
            output_mint=valid_usdc_mint,
            amount_in=1_000_000_000,
            min_amount_out=150_000_000,
            max_slippage_bps=50,
            jito_tip_lamports=10_000,
            user_wallet=valid_wallet_pubkey,
            created_at_slot=100,
            valid_until_slot=150,
        )
        await repo.log_intent(intent1)

        cand1 = RouteCandidate(
            candidate_id="cand-1",
            intent_id=intent1.intent_id,
            dex_type=DexType.RAYDIUM,
            route_plan_json={"dex": "raydium"},
        )
        await repo.log_route_candidates([cand1])

        sim1 = SimulationResult(
            candidate_id="cand-1",
            success=True,
            consumed_units=45_000,
            simulated_delta_out=152_000_000,
            simulation_duration_ms=12.5,
            simulated_at_slot=105,
        )
        await repo.log_simulation_results([sim1])

        verdict1 = ValidationResult(
            intent_id=intent1.intent_id,
            is_valid=True,
            action="DISPATCH",
            selected_candidate=cand1,
            clamped_compute_units=50_400,
            clamped_cu_saved_units=149_600,
            candidate_simulations=[sim1],
            decision_latency_ms=14.2,
        )
        await repo.record_audit_verdict(verdict1)

        # Create test intent 2 (Hard Aborted due to Slippage)
        intent2 = IntentRequest(
            agent_id="agent-beta",
            input_mint=valid_wsol_mint,
            output_mint=valid_usdc_mint,
            amount_in=2_000_000_000,  # 2 SOL
            min_amount_out=300_000_000,
            max_slippage_bps=30,
            jito_tip_lamports=25_000,
            user_wallet=valid_wallet_pubkey,
            created_at_slot=100,
            valid_until_slot=150,
        )
        await repo.log_intent(intent2)

        verdict2 = ValidationResult(
            intent_id=intent2.intent_id,
            is_valid=False,
            action="HARD_ABORT",
            abort_reason=AbortReason.ERR_SLIPPAGE_EXCEEDED,
            abort_details="Simulated delta < min_amount_out",
            base_fee_saved_lamports=5_000,
            priority_fee_saved_lamports=10_000,
            jito_tip_saved_lamports=25_000,
            capital_saved_lamports=2_000_000_000,
            decision_latency_ms=18.0,
        )
        await repo.record_audit_verdict(verdict2, aborted_candidates_count=1)

        # Query aggregated savings
        metrics = await repo.get_savings_metrics()

        assert metrics["total_evaluations"] == 2
        assert metrics["total_dispatched"] == 1
        assert metrics["total_hard_aborts"] == 1

        # 5,000 base + 10,000 priority + 25,000 jito = 40,000 lamports saved
        assert metrics["base_fee_saved_lamports"] == 5_000
        assert metrics["priority_fee_saved_lamports"] == 10_000
        assert metrics["jito_tip_saved_lamports"] == 25_000
        assert metrics["total_fees_saved_lamports"] == 40_000
        assert metrics["total_fees_saved_sol"] == 0.000040

        # Capital saved: 2 SOL
        assert metrics["capital_saved_lamports"] == 2_000_000_000
        assert metrics["capital_saved_sol"] == 2.0

        # Breakdown by abort reason
        assert metrics["aborts_by_reason"]["ERR_SLIPPAGE_EXCEEDED"] == 1
        assert metrics["clamped_cu_saved_units"] == 149_600

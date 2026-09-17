import json
from typing import Any, Dict, List, Optional

from gatekeeper.core.models import (
    IntentRequest,
    RouteCandidate,
    SimulationResult,
    ValidationResult,
)
from gatekeeper.storage.database import DatabaseManager


class AuditLedgerRepository:
    """High-performance repository for atomic audit logging and fee savings tracking."""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    async def log_intent(self, intent: IntentRequest, status: str = "PENDING") -> None:
        """Persists an incoming IntentRequest."""
        query = """
            INSERT INTO intents (
                intent_id, agent_id, input_mint, output_mint, amount_in,
                min_amount_out, max_slippage_bps, max_priority_fee_lamports,
                jito_tip_lamports, user_wallet, created_at_slot, valid_until_slot, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(intent_id) DO UPDATE SET status=excluded.status;
        """
        async with self.db.get_connection() as conn:
            await conn.execute(
                query,
                (
                    intent.intent_id,
                    intent.agent_id,
                    intent.input_mint,
                    intent.output_mint,
                    intent.amount_in,
                    intent.min_amount_out,
                    intent.max_slippage_bps,
                    intent.max_priority_fee_lamports,
                    intent.jito_tip_lamports,
                    intent.user_wallet,
                    intent.created_at_slot,
                    intent.valid_until_slot,
                    status,
                ),
            )
            await conn.commit()

    async def log_route_candidates(self, candidates: List[RouteCandidate]) -> None:
        """Persists generated candidate paths for an intent."""
        if not candidates:
            return

        query = """
            INSERT OR REPLACE INTO route_candidates (
                candidate_id, intent_id, dex_type, route_plan_json,
                is_split, estimated_hops, serialized_tx
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
        """
        data = [
            (
                c.candidate_id,
                c.intent_id,
                c.dex_type.value if hasattr(c.dex_type, "value") else str(c.dex_type),
                json.dumps(c.route_plan_json) if isinstance(c.route_plan_json, (dict, list)) else str(c.route_plan_json),
                c.is_split,
                c.estimated_hops,
                c.serialized_tx,
            )
            for c in candidates
        ]
        async with self.db.get_connection() as conn:
            await conn.executemany(query, data)
            await conn.commit()

    async def log_simulation_results(self, simulations: List[SimulationResult]) -> None:
        """Records raw simulation telemetry for candidates."""
        if not simulations:
            return

        query = """
            INSERT INTO simulations (
                candidate_id, success, consumed_units, simulated_delta_out,
                error_code, error_log, simulation_duration_ms, simulated_at_slot
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """
        data = [
            (
                s.candidate_id,
                s.success,
                s.consumed_units,
                s.simulated_delta_out,
                s.error_code,
                s.error_log,
                s.simulation_duration_ms,
                s.simulated_at_slot,
            )
            for s in simulations
        ]
        async with self.db.get_connection() as conn:
            await conn.executemany(query, data)
            await conn.commit()

    async def record_audit_verdict(
        self,
        verdict: ValidationResult,
        aborted_candidates_count: Optional[int] = None,
    ) -> None:
        """Records the final arbitration verdict (DISPATCH or HARD_ABORT) and saved fees."""
        update_intent_sql = "UPDATE intents SET status = ? WHERE intent_id = ?;"
        insert_ledger_sql = """
            INSERT INTO fee_savings_ledger (
                intent_id, action_taken, selected_candidate_id, aborted_candidates_count,
                base_fee_saved_lamports, priority_fee_saved_lamports, jito_tip_saved_lamports,
                total_fees_saved_lamports, capital_saved_lamports, clamped_cu_saved_units,
                decision_latency_ms, abort_reason, abort_details
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """

        aborted_count = (
            aborted_candidates_count
            if aborted_candidates_count is not None
            else sum(1 for s in verdict.candidate_simulations if not s.success)
        )
        selected_id = (
            verdict.selected_candidate.candidate_id
            if verdict.selected_candidate
            else None
        )
        reason_str = (
            verdict.abort_reason.value
            if hasattr(verdict.abort_reason, "value")
            else str(verdict.abort_reason)
            if verdict.abort_reason
            else None
        )

        async with self.db.get_connection() as conn:
            await conn.execute(
                update_intent_sql,
                (verdict.action, verdict.intent_id),
            )
            await conn.execute(
                insert_ledger_sql,
                (
                    verdict.intent_id,
                    verdict.action,
                    selected_id,
                    aborted_count,
                    verdict.base_fee_saved_lamports,
                    verdict.priority_fee_saved_lamports,
                    verdict.jito_tip_saved_lamports,
                    verdict.total_fees_saved_lamports,
                    verdict.capital_saved_lamports,
                    verdict.clamped_cu_saved_units,
                    verdict.decision_latency_ms,
                    reason_str,
                    verdict.abort_details,
                ),
            )
            await conn.commit()

    async def get_savings_metrics(self) -> Dict[str, Any]:
        """Calculates aggregated metrics for fee savings, prevented reverts, and latencies."""
        summary_query = """
            SELECT
                COUNT(*) as total_evaluations,
                SUM(CASE WHEN action_taken = 'DISPATCH' THEN 1 ELSE 0 END) as total_dispatched,
                SUM(CASE WHEN action_taken = 'HARD_ABORT' THEN 1 ELSE 0 END) as total_hard_aborts,
                SUM(base_fee_saved_lamports) as sum_base_saved,
                SUM(priority_fee_saved_lamports) as sum_priority_saved,
                SUM(jito_tip_saved_lamports) as sum_jito_saved,
                SUM(total_fees_saved_lamports) as sum_total_fees_saved,
                SUM(capital_saved_lamports) as sum_capital_saved,
                SUM(clamped_cu_saved_units) as sum_cu_saved,
                AVG(decision_latency_ms) as avg_latency
            FROM fee_savings_ledger;
        """

        reasons_query = """
            SELECT abort_reason, COUNT(*) as count
            FROM fee_savings_ledger
            WHERE action_taken = 'HARD_ABORT' AND abort_reason IS NOT NULL
            GROUP BY abort_reason;
        """

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(summary_query)
            row = await cursor.fetchone()

            reasons_cursor = await conn.execute(reasons_query)
            reason_rows = await reasons_cursor.fetchall()

        aborts_by_reason = {r["abort_reason"]: r["count"] for r in reason_rows}

        if not row or row["total_evaluations"] == 0:
            return {
                "total_evaluations": 0,
                "total_dispatched": 0,
                "total_hard_aborts": 0,
                "total_fees_saved_lamports": 0,
                "total_fees_saved_sol": 0.0,
                "base_fee_saved_lamports": 0,
                "priority_fee_saved_lamports": 0,
                "jito_tip_saved_lamports": 0,
                "capital_saved_lamports": 0,
                "capital_saved_sol": 0.0,
                "clamped_cu_saved_units": 0,
                "avg_decision_latency_ms": 0.0,
                "aborts_by_reason": {},
            }

        total_saved = row["sum_total_fees_saved"] or 0
        capital_saved = row["sum_capital_saved"] or 0

        return {
            "total_evaluations": row["total_evaluations"] or 0,
            "total_dispatched": row["total_dispatched"] or 0,
            "total_hard_aborts": row["total_hard_aborts"] or 0,
            "total_fees_saved_lamports": total_saved,
            "total_fees_saved_sol": round(total_saved / 1_000_000_000, 6),
            "base_fee_saved_lamports": row["sum_base_saved"] or 0,
            "priority_fee_saved_lamports": row["sum_priority_saved"] or 0,
            "jito_tip_saved_lamports": row["sum_jito_saved"] or 0,
            "capital_saved_lamports": capital_saved,
            "capital_saved_sol": round(capital_saved / 1_000_000_000, 6),
            "clamped_cu_saved_units": row["sum_cu_saved"] or 0,
            "avg_decision_latency_ms": round(row["avg_latency"] or 0.0, 2),
            "aborts_by_reason": aborts_by_reason,
        }

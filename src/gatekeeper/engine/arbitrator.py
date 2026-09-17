import time
from typing import Dict, List, Optional, Tuple

from gatekeeper.config import Settings, settings as global_settings
from gatekeeper.core.models import (
    AbortReason,
    IntentRequest,
    RouteCandidate,
    SimulationResult,
    ValidationResult,
)
from gatekeeper.matrix.ttl_validator import TTLValidator


class GatekeeperArbitrator:
    """Deterministic Arbitration Engine: Evaluates simulated routes and dictates DISPATCH vs HARD_ABORT."""

    def __init__(self, config: Optional[Settings] = None):
        self.config = config or global_settings
        self.ttl_validator = TTLValidator(self.config)

    def arbitrate(
        self,
        intent: IntentRequest,
        candidates: List[RouteCandidate],
        simulations: List[SimulationResult],
        current_cluster_slot: int,
        blockhash_slot: Optional[int] = None,
        start_time_perf: Optional[float] = None,
    ) -> ValidationResult:
        """Determines the optimal execution path or enforces a hard abort with zero on-chain cost."""
        start_time = start_time_perf or time.perf_counter()

        # 1. Evaluate Blockhash and Intent Slot TTL
        is_ttl_valid, ttl_error = self.ttl_validator.validate_slot_ttl(
            intent=intent,
            current_cluster_slot=current_cluster_slot,
            blockhash_slot=blockhash_slot,
        )

        if not is_ttl_valid:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            return self._build_hard_abort_result(
                intent=intent,
                simulations=simulations,
                reason=AbortReason.ERR_BLOCKHASH_EXPIRED,
                details=ttl_error or "Blockhash TTL expired before flight.",
                duration_ms=duration_ms,
            )

        # Map candidate_id to RouteCandidate for quick lookup
        candidate_map: Dict[str, RouteCandidate] = {c.candidate_id: c for c in candidates}

        # 2. Filter viable candidates that simulated successfully
        viable_routes: List[Tuple[RouteCandidate, SimulationResult]] = []
        for sim in simulations:
            cand = candidate_map.get(sim.candidate_id)
            if cand and sim.success:
                viable_routes.append((cand, sim))

        # 3. Decision Branch: If at least one viable route exists -> DISPATCH
        if viable_routes:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            return self._build_dispatch_result(
                intent=intent,
                viable_routes=viable_routes,
                all_simulations=simulations,
                duration_ms=duration_ms,
            )

        # 4. Decision Branch: All routes failed -> HARD_ABORT
        duration_ms = (time.perf_counter() - start_time) * 1000.0
        primary_reason, abort_details = self._determine_primary_abort_reason(simulations)

        return self._build_hard_abort_result(
            intent=intent,
            simulations=simulations,
            reason=primary_reason,
            details=abort_details,
            duration_ms=duration_ms,
        )

    def _build_dispatch_result(
        self,
        intent: IntentRequest,
        viable_routes: List[Tuple[RouteCandidate, SimulationResult]],
        all_simulations: List[SimulationResult],
        duration_ms: float,
    ) -> ValidationResult:
        """Picks the best candidate and injects dynamically clamped compute budget."""
        # Rank by highest net output token amount, then lowest compute units
        ranked = sorted(
            viable_routes,
            key=lambda item: (item[1].simulated_delta_out, -item[1].consumed_units),
            reverse=True,
        )
        selected_candidate, best_sim = ranked[0]

        # Dynamic Compute-Budget Clamping:
        # Buffer = 1.12 for direct single-hop, 1.20 for multi-hop / split
        buffer = selected_candidate.get_clamping_buffer(self.config)
        raw_clamped = int(best_sim.consumed_units * buffer)
        clamped_cu = max(
            self.config.MIN_COMPUTE_UNITS,
            min(raw_clamped, self.config.MAX_COMPUTE_UNITS),
        )

        cu_saved = max(0, self.config.DEFAULT_CU_LIMIT - clamped_cu)

        return ValidationResult(
            intent_id=intent.intent_id,
            is_valid=True,
            action="DISPATCH",
            selected_candidate=selected_candidate,
            clamped_compute_units=clamped_cu,
            priority_fee_micro_lamports=self.config.DEFAULT_PRIORITY_FEE_MICRO_LAMPORTS,
            abort_reason=None,
            abort_details=None,
            candidate_simulations=all_simulations,
            base_fee_saved_lamports=0,
            priority_fee_saved_lamports=0,
            jito_tip_saved_lamports=0,
            capital_saved_lamports=0,
            clamped_cu_saved_units=cu_saved,
            decision_latency_ms=round(duration_ms, 2),
        )

    def _build_hard_abort_result(
        self,
        intent: IntentRequest,
        simulations: List[SimulationResult],
        reason: AbortReason,
        details: str,
        duration_ms: float,
    ) -> ValidationResult:
        """Constructs an abort decision and calculates preserved capital, priority fees and tips."""
        # Calculate fees saved by intercepting execution before on-chain dispatch:
        # 1. Base fee
        base_saved = self.config.BASE_FEE_LAMPORTS

        # 2. Priority fee saved: based on default CU limit and configured rate
        cu_basis = self.config.DEFAULT_CU_LIMIT
        if simulations:
            avg_cu = sum(s.consumed_units for s in simulations if s.consumed_units > 0)
            if avg_cu > 0:
                cu_basis = int(avg_cu / len(simulations))

        priority_saved = int(
            (cu_basis * self.config.DEFAULT_PRIORITY_FEE_MICRO_LAMPORTS) / 1_000_000
        )

        # 3. Jito tip saved: full tip is preserved if bundle is discarded
        jito_saved = intent.jito_tip_lamports

        # 4. Capital saved: input capital saved from failed/reverted transaction
        capital_saved = intent.amount_in

        return ValidationResult(
            intent_id=intent.intent_id,
            is_valid=False,
            action="HARD_ABORT",
            selected_candidate=None,
            clamped_compute_units=0,
            priority_fee_micro_lamports=0,
            abort_reason=reason,
            abort_details=details,
            candidate_simulations=simulations,
            base_fee_saved_lamports=base_saved,
            priority_fee_saved_lamports=priority_saved,
            jito_tip_saved_lamports=jito_saved,
            capital_saved_lamports=capital_saved,
            clamped_cu_saved_units=0,
            decision_latency_ms=round(duration_ms, 2),
        )

    def _determine_primary_abort_reason(
        self, simulations: List[SimulationResult]
    ) -> Tuple[AbortReason, str]:
        """Classifies the primary failure mode from failed simulation logs."""
        if not simulations:
            return AbortReason.ERR_NO_VIABLE_ROUTE, "No route candidates generated or simulated."

        for sim in simulations:
            err_str = f"{sim.error_code or ''} {sim.error_log or ''}".lower()
            if "accountinuse" in err_str or "locked" in err_str:
                return (
                    AbortReason.ERR_ACCOUNT_CONTENTION,
                    f"Candidate {sim.candidate_id} failed due to account contention: {sim.error_code}",
                )
            if "slippage" in err_str or "0x1771" in err_str or "6001" in err_str:
                return (
                    AbortReason.ERR_SLIPPAGE_EXCEEDED,
                    f"Candidate {sim.candidate_id} violated slippage tolerance: {sim.error_code}",
                )
            if "computebudget" in err_str or "consumed 200000 of 200000" in err_str:
                return (
                    AbortReason.ERR_CU_EXHAUSTION,
                    f"Candidate {sim.candidate_id} exceeded compute unit budget: {sim.error_code}",
                )
            if "instructionerror" in err_str or "custom program error" in err_str:
                return (
                    AbortReason.ERR_CUSTOM_PROGRAM_FAIL,
                    f"Candidate {sim.candidate_id} failed with program error: {sim.error_code}",
                )

        return AbortReason.ERR_NO_VIABLE_ROUTE, "All candidate execution paths failed pre-flight verification."

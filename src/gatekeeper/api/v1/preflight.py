import time
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from gatekeeper.core.models import IntentRequest
from gatekeeper.engine.arbitrator import GatekeeperArbitrator
from gatekeeper.engine.candidate_generator import RouteCandidateGenerator
from gatekeeper.engine.simulator import PreFlightSimulator
from gatekeeper.storage.repository import AuditLedgerRepository

router = APIRouter()


class PreflightRequest(BaseModel):
    intent_id: str = Field(default_factory=lambda: f"intent-{uuid.uuid4().hex[:8]}")
    token_in: str
    token_out: str
    amount_in: int = Field(gt=0)
    max_slippage_bps: int = Field(default=50, ge=1, le=10000)
    priority_fee_cap_lamports: int = Field(default=100_000, ge=0)
    user_wallet: Optional[str] = "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5"
    min_amount_out: Optional[int] = None
    created_at_slot: Optional[int] = None
    valid_until_slot: Optional[int] = None


class PreflightResponse(BaseModel):
    intent_id: str
    decision: str  # "APPROVED" or "REJECTED"
    action: str    # "DISPATCH" or "HARD_ABORT"
    simulated_compute_units: int
    clamped_compute_units: int
    execution_time_ms: float
    selected_route: Optional[str] = None
    estimated_hops: int = 1
    clamped_cu_saved: int = 0
    fees_saved_lamports: int = 0
    rejection_reason: Optional[str] = None
    rejection_details: Optional[str] = None
    candidates_evaluated: int = 0


def get_repository(request: Request) -> AuditLedgerRepository:
    if hasattr(request.app.state, "repository"):
        return request.app.state.repository
    from gatekeeper.storage.database import DatabaseManager
    return AuditLedgerRepository(DatabaseManager())


def get_simulator(request: Request) -> PreFlightSimulator:
    if hasattr(request.app.state, "simulator"):
        return request.app.state.simulator
    return PreFlightSimulator()


def get_arbitrator(request: Request) -> GatekeeperArbitrator:
    if hasattr(request.app.state, "arbitrator"):
        return request.app.state.arbitrator
    return GatekeeperArbitrator()


def get_candidate_generator(request: Request) -> RouteCandidateGenerator:
    if hasattr(request.app.state, "candidate_generator"):
        return request.app.state.candidate_generator
    return RouteCandidateGenerator()


@router.post("", response_model=PreflightResponse)
@router.post("/", response_model=PreflightResponse)
async def evaluate_preflight_gate(
    payload: PreflightRequest,
    repo: AuditLedgerRepository = Depends(get_repository),
    simulator: PreFlightSimulator = Depends(get_simulator),
    arbitrator: GatekeeperArbitrator = Depends(get_arbitrator),
    candidate_gen: RouteCandidateGenerator = Depends(get_candidate_generator),
) -> PreflightResponse:
    """Live Pre-Flight Gate endpoint: Evaluates trade intents against live state and arbitrates APPROVED/REJECTED."""
    start_time = time.perf_counter()

    created_slot = payload.created_at_slot or 280_000_000
    valid_until = payload.valid_until_slot or (created_slot + 100)
    user_wallet = payload.user_wallet or "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5"

    # Default min_amount_out to 1 if unspecified (slippage checked via AMM threshold)
    min_amount = payload.min_amount_out or 1

    # 1. Normalize into strict IntentRequest
    intent = IntentRequest(
        intent_id=payload.intent_id,
        agent_id="preflight-agent",
        input_mint=payload.token_in,
        output_mint=payload.token_out,
        amount_in=payload.amount_in,
        min_amount_out=min_amount,
        max_slippage_bps=payload.max_slippage_bps,
        max_priority_fee_lamports=payload.priority_fee_cap_lamports,
        user_wallet=user_wallet,
        created_at_slot=created_slot,
        valid_until_slot=valid_until,
    )

    # 2. Synthesize candidates
    candidates = await candidate_gen.generate_candidates(intent)

    # 3. Log to SQLite storage
    await repo.log_intent(intent=intent, status="SIMULATING")
    await repo.log_route_candidates(candidates=candidates)

    # 4. Simulate candidates in parallel via asyncio.gather
    simulations = await simulator.simulate_all_candidates(candidates, intent)
    await repo.log_simulation_results(simulations)

    # 5. Arbitrate verdict
    verdict = arbitrator.arbitrate(
        intent=intent,
        candidates=candidates,
        simulations=simulations,
        current_cluster_slot=created_slot,
        blockhash_slot=created_slot,
        start_time_perf=start_time,
    )

    # 6. Record audit ledger verdict
    await repo.record_audit_verdict(verdict)

    execution_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
    decision = "APPROVED" if verdict.is_valid else "REJECTED"

    simulated_cu = (
        verdict.candidate_simulations[0].consumed_units
        if verdict.candidate_simulations
        else 0
    )
    if verdict.selected_candidate and verdict.candidate_simulations:
        for sim in verdict.candidate_simulations:
            if sim.candidate_id == verdict.selected_candidate.candidate_id:
                simulated_cu = sim.consumed_units
                break

    selected_dex = None
    estimated_hops = 1
    if verdict.selected_candidate:
        cand = verdict.selected_candidate
        selected_dex = cand.dex_type.value if hasattr(cand.dex_type, "value") else str(cand.dex_type)
        estimated_hops = cand.estimated_hops

    reason_str = (
        verdict.abort_reason.value
        if hasattr(verdict.abort_reason, "value")
        else str(verdict.abort_reason)
        if verdict.abort_reason
        else None
    )

    return PreflightResponse(
        intent_id=verdict.intent_id,
        decision=decision,
        action=verdict.action,
        simulated_compute_units=simulated_cu,
        clamped_compute_units=verdict.clamped_compute_units,
        execution_time_ms=execution_ms,
        selected_route=selected_dex,
        estimated_hops=estimated_hops,
        clamped_cu_saved=verdict.clamped_cu_saved_units,
        fees_saved_lamports=verdict.total_fees_saved_lamports,
        rejection_reason=reason_str,
        rejection_details=verdict.abort_details,
        candidates_evaluated=len(verdict.candidate_simulations),
    )

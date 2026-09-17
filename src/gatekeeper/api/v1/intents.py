from typing import List, Optional, Union
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from gatekeeper.core.models import (
    IntentRequest,
    RouteCandidate,
    ValidationResult,
)
from gatekeeper.engine.arbitrator import GatekeeperArbitrator
from gatekeeper.engine.candidate_generator import RouteCandidateGenerator
from gatekeeper.engine.simulator import PreFlightSimulator
from gatekeeper.storage.repository import AuditLedgerRepository

router = APIRouter()


class IntentEvaluationRequest(BaseModel):
    """Payload for submitting an intent with optional pre-computed route candidates."""

    intent: IntentRequest
    candidates: Optional[List[RouteCandidate]] = Field(
        default=None,
        description="Optional pre-generated candidates. If omitted, Gatekeeper synthesizes alternatives via Jupiter v6.",
    )
    current_cluster_slot: Optional[int] = Field(
        default=None,
        description="Current slot on Solana cluster. Defaults to intent.created_at_slot.",
    )
    blockhash_slot: Optional[int] = Field(
        default=None,
        description="Slot at which recent blockhash was created. Defaults to intent.created_at_slot.",
    )


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


@router.post("/evaluate", response_model=ValidationResult)
async def evaluate_intent(
    payload: Union[IntentEvaluationRequest, IntentRequest],
    repo: AuditLedgerRepository = Depends(get_repository),
    simulator: PreFlightSimulator = Depends(get_simulator),
    arbitrator: GatekeeperArbitrator = Depends(get_arbitrator),
    candidate_gen: RouteCandidateGenerator = Depends(get_candidate_generator),
) -> ValidationResult:
    """Pre-flight endpoint: Simulates routes concurrently, arbitrates DISPATCH vs HARD_ABORT, and audits fees."""
    # 1. Unpack request parameters
    if isinstance(payload, IntentEvaluationRequest):
        intent = payload.intent
        raw_candidates = payload.candidates
        cluster_slot = payload.current_cluster_slot or intent.created_at_slot
        blockhash_slot = payload.blockhash_slot or intent.created_at_slot
    else:
        intent = payload
        raw_candidates = None
        cluster_slot = intent.created_at_slot
        blockhash_slot = intent.created_at_slot

    # 2. Synthesize candidates via Jupiter DEX Aggregator if not provided
    if raw_candidates:
        candidates = raw_candidates
    else:
        candidates = await candidate_gen.generate_candidates(intent)

    # 3. Log intent & candidate routes atomically
    await repo.log_intent(intent=intent, status="SIMULATING")
    await repo.log_route_candidates(candidates=candidates)

    # 4. Concurrently simulate all candidates via asyncio.gather
    simulations = await simulator.simulate_all_candidates(
        candidates=candidates,
        intent=intent,
    )

    # 5. Persist raw simulation telemetry
    await repo.log_simulation_results(simulations=simulations)

    # 6. Arbitrate deterministic verdict
    verdict = arbitrator.arbitrate(
        intent=intent,
        candidates=candidates,
        simulations=simulations,
        current_cluster_slot=cluster_slot,
        blockhash_slot=blockhash_slot,
    )

    # 7. Record verdict and update fee savings ledger
    await repo.record_audit_verdict(verdict=verdict)

    return verdict

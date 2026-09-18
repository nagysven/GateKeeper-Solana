from typing import Optional
from pydantic import BaseModel, Field


class PreflightEvaluation(BaseModel):
    """Result of a deterministic pre-flight evaluation."""

    intent_id: str
    decision: str  # "APPROVED" or "REJECTED"
    action: str  # "DISPATCH" or "HARD_ABORT"
    simulated_compute_units: int = 0
    clamped_compute_units: int = 0
    execution_time_ms: float = 0.0
    selected_route: Optional[str] = None
    estimated_hops: int = 1
    clamped_cu_saved: int = 0
    fees_saved_lamports: int = 0
    rejection_reason: Optional[str] = None
    rejection_details: Optional[str] = None
    candidates_evaluated: int = 0

    @property
    def is_approved(self) -> bool:
        """True if the transaction safely passed simulation and arbitration."""
        return self.decision == "APPROVED"

    @property
    def fees_saved_sol(self) -> float:
        """Total preserved fees converted to SOL."""
        return self.fees_saved_lamports / 1_000_000_000.0


class SavingsMetrics(BaseModel):
    """Cumulative firewall savings metrics."""

    total_evaluations: int = 0
    total_dispatched: int = 0
    total_hard_aborts: int = 0
    total_fees_saved_lamports: int = 0
    total_fees_saved_sol: float = 0.0
    clamped_cu_saved_units: int = 0
    avg_decision_latency_ms: float = 0.0

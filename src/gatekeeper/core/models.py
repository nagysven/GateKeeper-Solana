import uuid
from enum import Enum
from typing import Any, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator
from solders.pubkey import Pubkey

from gatekeeper.config import Settings, settings as global_settings


class DexType(str, Enum):
    RAYDIUM = "RAYDIUM"
    ORCA = "ORCA"
    METEORA = "METEORA"
    SPLIT = "SPLIT"
    CUSTOM = "CUSTOM"


class IntentStatus(str, Enum):
    PENDING = "PENDING"
    SIMULATING = "SIMULATING"
    DISPATCHED = "DISPATCHED"
    HARD_ABORT = "HARD_ABORT"
    EXPIRED = "EXPIRED"


class AbortReason(str, Enum):
    ERR_BLOCKHASH_EXPIRED = "ERR_BLOCKHASH_EXPIRED"
    ERR_SLIPPAGE_EXCEEDED = "ERR_SLIPPAGE_EXCEEDED"
    ERR_ACCOUNT_CONTENTION = "ERR_ACCOUNT_CONTENTION"
    ERR_CU_EXHAUSTION = "ERR_CU_EXHAUSTION"
    ERR_RENT_NON_EXEMPT = "ERR_RENT_NON_EXEMPT"
    ERR_INSUFFICIENT_FUNDS = "ERR_INSUFFICIENT_FUNDS"
    ERR_CUSTOM_PROGRAM_FAIL = "ERR_CUSTOM_PROGRAM_FAIL"
    ERR_NO_VIABLE_ROUTE = "ERR_NO_VIABLE_ROUTE"


class IntentRequest(BaseModel):
    """Normalized intent submitted by an autonomous AI agent or trading client."""

    intent_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for this intent.",
    )
    agent_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="ID of the originating AI agent or client.",
    )
    input_mint: str = Field(
        ...,
        description="Base58 public key of the input token mint.",
    )
    output_mint: str = Field(
        ...,
        description="Base58 public key of the desired output token mint.",
    )
    amount_in: int = Field(
        ...,
        gt=0,
        description="Input token amount in atomic units (e.g., Lamports for native SOL).",
    )
    min_amount_out: int = Field(
        ...,
        gt=0,
        description="Minimum acceptable output token amount in atomic units.",
    )
    max_slippage_bps: int = Field(
        ...,
        ge=1,
        le=10_000,
        description="Maximum allowed slippage in basis points (1 bp = 0.01%, 10000 bp = 100%).",
    )
    max_priority_fee_lamports: int = Field(
        default=100_000,
        ge=0,
        description="Maximum priority fee the agent is willing to pay in Lamports.",
    )
    jito_tip_lamports: int = Field(
        default=0,
        ge=0,
        description="Optional Jito validator bundle tip in Lamports.",
    )
    user_wallet: str = Field(
        ...,
        description="Base58 public key of the trader/agent wallet.",
    )
    created_at_slot: int = Field(
        ...,
        gt=0,
        description="Cluster slot at the moment of intent creation.",
    )
    valid_until_slot: int = Field(
        ...,
        gt=0,
        description="Cluster slot after which the intent must strictly not execute.",
    )

    @field_validator("input_mint", "output_mint", "user_wallet")
    @classmethod
    def validate_solana_pubkey(cls, v: str) -> str:
        try:
            Pubkey.from_string(v)
            return v
        except Exception as e:
            raise ValueError(f"Invalid Solana public key format: {v}") from e

    @model_validator(mode="after")
    def validate_intent_logic(self) -> "IntentRequest":
        if self.input_mint == self.output_mint:
            raise ValueError("input_mint and output_mint cannot be identical.")
        if self.valid_until_slot < self.created_at_slot:
            raise ValueError(
                f"valid_until_slot ({self.valid_until_slot}) must be >= created_at_slot ({self.created_at_slot})."
            )
        if (self.valid_until_slot - self.created_at_slot) > 300:
            raise ValueError(
                f"Intent TTL exceeds maximum allowed window of 300 slots "
                f"({self.valid_until_slot - self.created_at_slot} slots requested)."
            )
        return self

    def is_expired(self, current_slot: int) -> bool:
        """Determines if the intent has exceeded its valid slot range."""
        return current_slot > self.valid_until_slot

    def slots_remaining(self, current_slot: int) -> int:
        """Returns remaining slots before expiration, bounded at 0."""
        return max(0, self.valid_until_slot - current_slot)


class RouteCandidate(BaseModel):
    """An execution route candidate to be simulated in parallel against live state."""

    candidate_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for this route candidate.",
    )
    intent_id: str = Field(..., description="ID of the associated IntentRequest.")
    dex_type: DexType = Field(..., description="DEX or routing strategy employed.")
    route_plan_json: Any = Field(..., description="DEX-specific route data or swap instructions.")
    is_split: bool = Field(default=False, description="True if route splits volume across pools.")
    estimated_hops: int = Field(
        default=1,
        ge=1,
        description="Number of swap hops in this candidate path.",
    )
    serialized_tx: Optional[str] = Field(
        default=None,
        description="Base64-encoded unsigned or pre-signed transaction wire payload.",
    )

    def get_clamping_buffer(self, config: Optional[Settings] = None) -> float:
        """Dynamically determines the safety buffer for compute unit clamping.

        Direct single-hop swaps use DIRECT_SWAP_CLAMPING_BUFFER (default 1.12).
        Multi-hop or split routes use MULTI_HOP_CLAMPING_BUFFER (default 1.20).
        """
        cfg = config or global_settings
        if self.is_split or self.estimated_hops > 1:
            return cfg.MULTI_HOP_CLAMPING_BUFFER
        return cfg.DIRECT_SWAP_CLAMPING_BUFFER


class SimulationResult(BaseModel):
    """Raw output and execution statistics from simulateTransaction."""

    candidate_id: str = Field(..., description="ID of the simulated RouteCandidate.")
    success: bool = Field(..., description="Whether simulation executed without reverting.")
    consumed_units: int = Field(default=0, ge=0, description="Actual compute units consumed.")
    simulated_delta_out: int = Field(
        default=0,
        ge=0,
        description="Simulated net token amount received by destination wallet.",
    )
    error_code: Optional[str] = Field(
        default=None,
        description="Error code string (e.g. 0x1771, AccountInUse, ComputeBudgetExceeded).",
    )
    error_log: Optional[str] = Field(
        default=None,
        description="Program log excerpt detailing failure cause.",
    )
    simulation_duration_ms: float = Field(
        default=0.0,
        ge=0.0,
        description="RPC round-trip simulation latency in milliseconds.",
    )
    simulated_at_slot: int = Field(
        default=0,
        ge=0,
        description="Cluster slot at which simulation was evaluated.",
    )


class ValidationResult(BaseModel):
    """Deterministic verdict produced by the Gatekeeper arbitrator."""

    intent_id: str = Field(..., description="ID of the evaluated IntentRequest.")
    is_valid: bool = Field(..., description="True if a path is deemed safe to dispatch.")
    action: str = Field(
        ...,
        description="'DISPATCH' if route is cleared, 'HARD_ABORT' if dropped.",
    )
    selected_candidate: Optional[RouteCandidate] = Field(
        default=None,
        description="Optimal route selected for on-chain dispatch.",
    )
    clamped_compute_units: int = Field(
        default=0,
        ge=0,
        description="Dynamically injected compute unit limit (consumed_cu * buffer).",
    )
    priority_fee_micro_lamports: int = Field(
        default=0,
        ge=0,
        description="Applied priority fee rate in micro-lamports per CU.",
    )
    abort_reason: Optional[AbortReason] = Field(
        default=None,
        description="Root cause if action is HARD_ABORT.",
    )
    abort_details: Optional[str] = Field(
        default=None,
        description="Human-readable explanation of abort decision.",
    )
    candidate_simulations: List[SimulationResult] = Field(
        default_factory=list,
        description="Simulations evaluated during pre-flight.",
    )

    # Verifiable Audit Ledger & Fee Savings Metrics
    base_fee_saved_lamports: int = Field(
        default=0,
        ge=0,
        description="Base transaction fees saved by dropping invalid paths.",
    )
    priority_fee_saved_lamports: int = Field(
        default=0,
        ge=0,
        description="Priority fees saved by preventing failed on-chain execution.",
    )
    jito_tip_saved_lamports: int = Field(
        default=0,
        ge=0,
        description="Jito validator tip saved by dropping failing bundle.",
    )
    capital_saved_lamports: int = Field(
        default=0,
        ge=0,
        description="Principal capital preserved by intercepting bad slippage/revert.",
    )
    clamped_cu_saved_units: int = Field(
        default=0,
        ge=0,
        description="Compute units saved vs standard default limit through dynamic clamping.",
    )
    decision_latency_ms: float = Field(
        default=0.0,
        ge=0.0,
        description="Total time spent in Gatekeeper arbitration pipeline in milliseconds.",
    )

    @property
    def total_fees_saved_lamports(self) -> int:
        """Total on-chain fees preserved: base fee + priority fee + Jito validator tip."""
        return (
            self.base_fee_saved_lamports
            + self.priority_fee_saved_lamports
            + self.jito_tip_saved_lamports
        )

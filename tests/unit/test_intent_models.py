import pytest
from pydantic import ValidationError

from gatekeeper.config import Settings
from gatekeeper.core.models import (
    AbortReason,
    DexType,
    IntentRequest,
    RouteCandidate,
    ValidationResult,
)


class TestIntentRequestValidation:
    """Unit test suite verifying boundary and type enforcement on IntentRequest."""

    def test_valid_intent_instantiation(
        self, valid_wsol_mint: str, valid_usdc_mint: str, valid_wallet_pubkey: str
    ):
        """Verify standard valid intent creation with full parameter coverage."""
        intent = IntentRequest(
            agent_id="sentient-trader-01",
            input_mint=valid_wsol_mint,
            output_mint=valid_usdc_mint,
            amount_in=1_000_000_000,  # 1 SOL
            min_amount_out=150_000_000,  # 150 USDC (6 decimals)
            max_slippage_bps=50,  # 0.5%
            max_priority_fee_lamports=50_000,
            jito_tip_lamports=15_000,
            user_wallet=valid_wallet_pubkey,
            created_at_slot=280_000_000,
            valid_until_slot=280_000_050,
        )

        assert intent.agent_id == "sentient-trader-01"
        assert intent.amount_in == 1_000_000_000
        assert intent.jito_tip_lamports == 15_000
        assert intent.slots_remaining(280_000_020) == 30
        assert not intent.is_expired(280_000_020)
        assert intent.is_expired(280_000_051)

    def test_invalid_solana_pubkey_rejection(
        self, valid_usdc_mint: str, valid_wallet_pubkey: str
    ):
        """Verify non-base58 or malformed Solana public keys are rejected immediately."""
        with pytest.raises(ValidationError) as exc_info:
            IntentRequest(
                agent_id="test-agent",
                input_mint="NotAValidSolanaPublicKey123",
                output_mint=valid_usdc_mint,
                amount_in=1_000_000,
                min_amount_out=900_000,
                max_slippage_bps=50,
                user_wallet=valid_wallet_pubkey,
                created_at_slot=100,
                valid_until_slot=150,
            )
        assert "Invalid Solana public key format" in str(exc_info.value)

    def test_identical_input_and_output_mint_rejection(
        self, valid_wsol_mint: str, valid_wallet_pubkey: str
    ):
        """Verify trading the same asset for itself is blocked at the gateway."""
        with pytest.raises(ValidationError) as exc_info:
            IntentRequest(
                agent_id="test-agent",
                input_mint=valid_wsol_mint,
                output_mint=valid_wsol_mint,
                amount_in=1_000_000,
                min_amount_out=990_000,
                max_slippage_bps=50,
                user_wallet=valid_wallet_pubkey,
                created_at_slot=100,
                valid_until_slot=150,
            )
        assert "cannot be identical" in str(exc_info.value)

    def test_negative_or_zero_amount_in_rejection(
        self, valid_wsol_mint: str, valid_usdc_mint: str, valid_wallet_pubkey: str
    ):
        """Verify non-positive input amounts fail validation."""
        for invalid_amount in [0, -1, -1_000_000]:
            with pytest.raises(ValidationError):
                IntentRequest(
                    agent_id="test-agent",
                    input_mint=valid_wsol_mint,
                    output_mint=valid_usdc_mint,
                    amount_in=invalid_amount,
                    min_amount_out=100,
                    max_slippage_bps=50,
                    user_wallet=valid_wallet_pubkey,
                    created_at_slot=100,
                    valid_until_slot=150,
                )

    def test_slippage_bounds_enforcement(
        self, valid_wsol_mint: str, valid_usdc_mint: str, valid_wallet_pubkey: str
    ):
        """Verify slippage must be between 1 and 10000 bps."""
        # 0 bps is invalid
        with pytest.raises(ValidationError):
            IntentRequest(
                agent_id="test-agent",
                input_mint=valid_wsol_mint,
                output_mint=valid_usdc_mint,
                amount_in=1_000_000,
                min_amount_out=100,
                max_slippage_bps=0,
                user_wallet=valid_wallet_pubkey,
                created_at_slot=100,
                valid_until_slot=150,
            )

        # >10000 bps (100%) is invalid
        with pytest.raises(ValidationError):
            IntentRequest(
                agent_id="test-agent",
                input_mint=valid_wsol_mint,
                output_mint=valid_usdc_mint,
                amount_in=1_000_000,
                min_amount_out=100,
                max_slippage_bps=10_001,
                user_wallet=valid_wallet_pubkey,
                created_at_slot=100,
                valid_until_slot=150,
            )

    def test_slot_ttl_invariance_checks(
        self, valid_wsol_mint: str, valid_usdc_mint: str, valid_wallet_pubkey: str
    ):
        """Verify slot ordering and TTL window constraints."""
        # valid_until_slot before created_at_slot
        with pytest.raises(ValidationError) as exc_info:
            IntentRequest(
                agent_id="test-agent",
                input_mint=valid_wsol_mint,
                output_mint=valid_usdc_mint,
                amount_in=1_000_000,
                min_amount_out=100,
                max_slippage_bps=50,
                user_wallet=valid_wallet_pubkey,
                created_at_slot=200,
                valid_until_slot=199,
            )
        assert "must be >= created_at_slot" in str(exc_info.value)

        # TTL exceeding 300 slots
        with pytest.raises(ValidationError) as exc_info:
            IntentRequest(
                agent_id="test-agent",
                input_mint=valid_wsol_mint,
                output_mint=valid_usdc_mint,
                amount_in=1_000_000,
                min_amount_out=100,
                max_slippage_bps=50,
                user_wallet=valid_wallet_pubkey,
                created_at_slot=100,
                valid_until_slot=401,
            )
        assert "Intent TTL exceeds maximum allowed window" in str(exc_info.value)


class TestRouteCandidateClampingBuffer:
    """Verifies dynamic clamping buffer configuration for direct vs multi-hop."""

    def test_direct_single_hop_buffer(self, custom_settings: Settings):
        candidate = RouteCandidate(
            intent_id="intent-123",
            dex_type=DexType.RAYDIUM,
            route_plan_json={"pool": "raydium-sol-usdc"},
            is_split=False,
            estimated_hops=1,
        )
        assert candidate.get_clamping_buffer(custom_settings) == 1.12

    def test_multi_hop_buffer(self, custom_settings: Settings):
        candidate = RouteCandidate(
            intent_id="intent-123",
            dex_type=DexType.ORCA,
            route_plan_json={"pool1": "sol-usdc", "pool2": "usdc-bonk"},
            is_split=False,
            estimated_hops=2,
        )
        assert candidate.get_clamping_buffer(custom_settings) == 1.20

    def test_split_route_buffer(self, custom_settings: Settings):
        candidate = RouteCandidate(
            intent_id="intent-123",
            dex_type=DexType.SPLIT,
            route_plan_json={"split": [{"dex": "raydium"}, {"dex": "orca"}]},
            is_split=True,
            estimated_hops=1,
        )
        assert candidate.get_clamping_buffer(custom_settings) == 1.20


class TestValidationResultAndSavings:
    """Verifies fee accounting including priority fees and Jito tips."""

    def test_total_fees_saved_calculation(self):
        result = ValidationResult(
            intent_id="intent-456",
            is_valid=False,
            action="HARD_ABORT",
            abort_reason=AbortReason.ERR_SLIPPAGE_EXCEEDED,
            abort_details="Simulated delta 95000 < expected 100000",
            base_fee_saved_lamports=5_000,
            priority_fee_saved_lamports=25_000,
            jito_tip_saved_lamports=50_000,
            capital_saved_lamports=1_000_000,
            clamped_cu_saved_units=40_000,
            decision_latency_ms=18.4,
        )

        # 5,000 + 25,000 + 50,000 = 80,000 Lamports
        assert result.total_fees_saved_lamports == 80_000
        assert result.capital_saved_lamports == 1_000_000
        assert result.action == "HARD_ABORT"

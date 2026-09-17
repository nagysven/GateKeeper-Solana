import json
from pathlib import Path
from typing import Any, Dict

import pytest

from gatekeeper.config import Settings
from gatekeeper.core.models import (
    AbortReason,
    DexType,
    IntentRequest,
    RouteCandidate,
)
from gatekeeper.engine.arbitrator import GatekeeperArbitrator
from gatekeeper.engine.simulator import PreFlightSimulator


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent.parent / "fixtures" / "simulation_responses"


@pytest.fixture
def raydium_success_payload(fixtures_dir: Path) -> Dict[str, Any]:
    return json.loads((fixtures_dir / "raydium_success.json").read_text(encoding="utf-8"))


@pytest.fixture
def slippage_failure_payload(fixtures_dir: Path) -> Dict[str, Any]:
    return json.loads((fixtures_dir / "slippage_failure.json").read_text(encoding="utf-8"))


@pytest.fixture
def cu_exceeded_payload(fixtures_dir: Path) -> Dict[str, Any]:
    return json.loads((fixtures_dir / "cu_exceeded.json").read_text(encoding="utf-8"))


@pytest.fixture
def account_in_use_payload(fixtures_dir: Path) -> Dict[str, Any]:
    return json.loads((fixtures_dir / "account_in_use.json").read_text(encoding="utf-8"))


class TestSimulationEngineIntegration:
    """Integration test suite verifying concurrent simulation and deterministic arbitration."""

    async def test_parallel_simulation_selects_optimal_path(
        self,
        valid_wsol_mint: str,
        valid_usdc_mint: str,
        valid_wallet_pubkey: str,
        raydium_success_payload: Dict[str, Any],
        slippage_failure_payload: Dict[str, Any],
        cu_exceeded_payload: Dict[str, Any],
    ):
        """Simulates 3 candidates concurrently: Route 1 succeeds, Route 2 slippage fails, Route 3 CU exceeds.

        Verifies that Gatekeeper selects the winning Route 1 and clamps CU to 44,820 * 1.12 = 50,198.
        """
        intent = IntentRequest(
            agent_id="auton-trader-99",
            input_mint=valid_wsol_mint,
            output_mint=valid_usdc_mint,
            amount_in=1_000_000_000,
            min_amount_out=150_000_000,
            max_slippage_bps=50,
            max_priority_fee_lamports=100_000,
            jito_tip_lamports=20_000,
            user_wallet=valid_wallet_pubkey,
            created_at_slot=280_000_000,
            valid_until_slot=280_000_050,
        )

        cand_raydium = RouteCandidate(
            candidate_id="cand-raydium",
            intent_id=intent.intent_id,
            dex_type=DexType.RAYDIUM,
            route_plan_json={"pool": "raydium-direct"},
            is_split=False,
            estimated_hops=1,
        )
        cand_slippage = RouteCandidate(
            candidate_id="cand-slippage",
            intent_id=intent.intent_id,
            dex_type=DexType.ORCA,
            route_plan_json={"pool": "orca-direct"},
            is_split=False,
            estimated_hops=1,
        )
        cand_cu_exhaust = RouteCandidate(
            candidate_id="cand-cu-exhaust",
            intent_id=intent.intent_id,
            dex_type=DexType.SPLIT,
            route_plan_json={"pool": "split-multi-hop"},
            is_split=True,
            estimated_hops=2,
        )

        # Mock RPC dispatcher that returns corresponding fixture by candidate_id
        def mock_rpc_dispatcher(candidate: RouteCandidate, _intent: IntentRequest):
            if candidate.candidate_id == "cand-raydium":
                return raydium_success_payload
            elif candidate.candidate_id == "cand-slippage":
                return slippage_failure_payload
            elif candidate.candidate_id == "cand-cu-exhaust":
                return cu_exceeded_payload
            raise ValueError(f"Unknown candidate {candidate.candidate_id}")

        simulator = PreFlightSimulator(rpc_dispatcher=mock_rpc_dispatcher)
        arbitrator = GatekeeperArbitrator()

        # Step 1: Simulate all 3 candidates in parallel via asyncio.gather
        simulations = await simulator.simulate_all_candidates(
            candidates=[cand_raydium, cand_slippage, cand_cu_exhaust],
            intent=intent,
        )

        assert len(simulations) == 3

        # Verify parsed simulations
        sim_ray = next(s for s in simulations if s.candidate_id == "cand-raydium")
        sim_slip = next(s for s in simulations if s.candidate_id == "cand-slippage")
        sim_cu = next(s for s in simulations if s.candidate_id == "cand-cu-exhaust")

        assert sim_ray.success is True
        assert sim_ray.consumed_units == 44_820
        assert sim_ray.simulated_delta_out == 151_200_000

        assert sim_slip.success is False
        assert "0x1771" in (sim_slip.error_log or "")

        assert sim_cu.success is False
        assert sim_cu.consumed_units == 200_000

        # Step 2: Arbitrate at slot 280_000_010 (within TTL)
        verdict = arbitrator.arbitrate(
            intent=intent,
            candidates=[cand_raydium, cand_slippage, cand_cu_exhaust],
            simulations=simulations,
            current_cluster_slot=280_000_010,
            blockhash_slot=280_000_000,
        )

        # Step 3: Assert verdict and dynamic clamping
        assert verdict.is_valid is True
        assert verdict.action == "DISPATCH"
        assert verdict.selected_candidate is not None
        assert verdict.selected_candidate.candidate_id == "cand-raydium"

        # 44,820 * 1.12 = 50,198 CU
        expected_clamped_cu = int(44_820 * 1.12)
        assert verdict.clamped_compute_units == expected_clamped_cu
        assert verdict.clamped_cu_saved_units == (200_000 - expected_clamped_cu)

    async def test_all_candidates_failing_triggers_hard_abort_with_savings(
        self,
        valid_wsol_mint: str,
        valid_usdc_mint: str,
        valid_wallet_pubkey: str,
        slippage_failure_payload: Dict[str, Any],
        account_in_use_payload: Dict[str, Any],
    ):
        """Simulates scenario where all routes fail: Gatekeeper must enforce HARD_ABORT and calculate fee savings."""
        intent = IntentRequest(
            agent_id="auton-trader-88",
            input_mint=valid_wsol_mint,
            output_mint=valid_usdc_mint,
            amount_in=2_000_000_000,  # 2 SOL
            min_amount_out=300_000_000,
            max_slippage_bps=30,
            max_priority_fee_lamports=50_000,
            jito_tip_lamports=25_000,
            user_wallet=valid_wallet_pubkey,
            created_at_slot=280_000_000,
            valid_until_slot=280_000_050,
        )

        cand_lock = RouteCandidate(
            candidate_id="cand-locked",
            intent_id=intent.intent_id,
            dex_type=DexType.RAYDIUM,
            route_plan_json={"pool": "locked-vault"},
        )
        cand_slip = RouteCandidate(
            candidate_id="cand-revert",
            intent_id=intent.intent_id,
            dex_type=DexType.ORCA,
            route_plan_json={"pool": "slippage-pool"},
        )

        def mock_rpc_dispatcher(candidate: RouteCandidate, _intent: IntentRequest):
            if candidate.candidate_id == "cand-locked":
                return account_in_use_payload
            return slippage_failure_payload

        simulator = PreFlightSimulator(rpc_dispatcher=mock_rpc_dispatcher)
        arbitrator = GatekeeperArbitrator()

        simulations = await simulator.simulate_all_candidates(
            candidates=[cand_lock, cand_slip],
            intent=intent,
        )

        verdict = arbitrator.arbitrate(
            intent=intent,
            candidates=[cand_lock, cand_slip],
            simulations=simulations,
            current_cluster_slot=280_000_015,
            blockhash_slot=280_000_000,
        )

        # Assert zero on-chain transaction dispatch
        assert verdict.is_valid is False
        assert verdict.action == "HARD_ABORT"
        assert verdict.selected_candidate is None
        assert verdict.abort_reason == AbortReason.ERR_ACCOUNT_CONTENTION

        # Assert full fee & tip preservation accounting
        assert verdict.base_fee_saved_lamports == 5_000
        assert verdict.jito_tip_saved_lamports == 25_000
        assert verdict.priority_fee_saved_lamports > 0
        assert verdict.capital_saved_lamports == 2_000_000_000
        assert verdict.total_fees_saved_lamports == (
            verdict.base_fee_saved_lamports
            + verdict.priority_fee_saved_lamports
            + verdict.jito_tip_saved_lamports
        )

    async def test_expired_ttl_triggers_immediate_hard_abort(
        self,
        valid_wsol_mint: str,
        valid_usdc_mint: str,
        valid_wallet_pubkey: str,
        raydium_success_payload: Dict[str, Any],
    ):
        """Even if simulation succeeded, if blockhash/intent slot expired before arbitration -> HARD_ABORT."""
        intent = IntentRequest(
            agent_id="auton-trader-77",
            input_mint=valid_wsol_mint,
            output_mint=valid_usdc_mint,
            amount_in=1_000_000_000,
            min_amount_out=150_000_000,
            max_slippage_bps=50,
            jito_tip_lamports=10_000,
            user_wallet=valid_wallet_pubkey,
            created_at_slot=280_000_000,
            valid_until_slot=280_000_030,
        )

        cand = RouteCandidate(
            candidate_id="cand-delayed",
            intent_id=intent.intent_id,
            dex_type=DexType.RAYDIUM,
            route_plan_json={},
        )

        simulator = PreFlightSimulator(rpc_dispatcher=lambda _c, _i: raydium_success_payload)
        arbitrator = GatekeeperArbitrator()

        simulations = await simulator.simulate_all_candidates([cand], intent)

        # Slot 280_000_035 > valid_until_slot 280_000_030
        verdict = arbitrator.arbitrate(
            intent=intent,
            candidates=[cand],
            simulations=simulations,
            current_cluster_slot=280_000_035,
            blockhash_slot=280_000_000,
        )

        assert verdict.is_valid is False
        assert verdict.action == "HARD_ABORT"
        assert verdict.abort_reason == AbortReason.ERR_BLOCKHASH_EXPIRED
        assert verdict.jito_tip_saved_lamports == 10_000

    async def test_multi_hop_candidate_applies_20_percent_buffer(
        self,
        valid_wsol_mint: str,
        valid_usdc_mint: str,
        valid_wallet_pubkey: str,
        raydium_success_payload: Dict[str, Any],
    ):
        """Verifies that a multi-hop candidate receives a 20% clamping buffer instead of 12%."""
        intent = IntentRequest(
            agent_id="auton-trader-55",
            input_mint=valid_wsol_mint,
            output_mint=valid_usdc_mint,
            amount_in=1_000_000_000,
            min_amount_out=150_000_000,
            max_slippage_bps=50,
            user_wallet=valid_wallet_pubkey,
            created_at_slot=280_000_000,
            valid_until_slot=280_000_050,
        )

        cand_multihop = RouteCandidate(
            candidate_id="cand-2hop",
            intent_id=intent.intent_id,
            dex_type=DexType.ORCA,
            route_plan_json={"hops": 2},
            is_split=False,
            estimated_hops=2,  # Multi-hop route!
        )

        simulator = PreFlightSimulator(rpc_dispatcher=lambda _c, _i: raydium_success_payload)
        arbitrator = GatekeeperArbitrator()

        simulations = await simulator.simulate_all_candidates([cand_multihop], intent)

        verdict = arbitrator.arbitrate(
            intent=intent,
            candidates=[cand_multihop],
            simulations=simulations,
            current_cluster_slot=280_000_010,
            blockhash_slot=280_000_000,
        )

        assert verdict.is_valid is True
        # Consumed is 44,820. With 2 hops -> 1.20 buffer: 44,820 * 1.20 = 53,784 CU
        expected_clamped = int(44_820 * 1.20)
        assert verdict.clamped_compute_units == expected_clamped

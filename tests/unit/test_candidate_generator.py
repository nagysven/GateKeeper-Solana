import json
from pathlib import Path
from typing import Any, Dict
import httpx
import pytest

from gatekeeper.core.models import DexType, IntentRequest
from gatekeeper.engine.candidate_generator import RouteCandidateGenerator
from gatekeeper.engine.jupiter_client import JupiterApiError, JupiterClient


@pytest.fixture
def jupiter_fixtures_dir() -> Path:
    return Path(__file__).parent.parent / "fixtures" / "jupiter_quotes"


@pytest.fixture
def direct_quote_payload(jupiter_fixtures_dir: Path) -> Dict[str, Any]:
    return json.loads((jupiter_fixtures_dir / "direct_quote.json").read_text(encoding="utf-8"))


@pytest.fixture
def multihop_quote_payload(jupiter_fixtures_dir: Path) -> Dict[str, Any]:
    return json.loads((jupiter_fixtures_dir / "multihop_quote.json").read_text(encoding="utf-8"))


@pytest.fixture
def swap_tx_payload(jupiter_fixtures_dir: Path) -> Dict[str, Any]:
    return json.loads((jupiter_fixtures_dir / "swap_transaction.json").read_text(encoding="utf-8"))


class TestJupiterClient:
    async def test_get_quote_success(self, direct_quote_payload: dict):
        def handler(request: httpx.Request):
            assert request.url.path.endswith("/quote")
            assert "onlyDirectRoutes=true" in str(request.url)
            return httpx.Response(200, json=direct_quote_payload)

        mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        jup = JupiterClient(http_client=mock_client)

        quote = await jup.get_quote(
            input_mint="So11111111111111111111111111111111111111112",
            output_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            amount_in=1_000_000_000,
            slippage_bps=50,
            only_direct_routes=True,
        )
        assert quote["outAmount"] == "151200000"
        assert len(quote["routePlan"]) == 1

    async def test_get_quote_error_raises_jupiter_api_error(self):
        def handler(_request: httpx.Request):
            return httpx.Response(500, text="Internal Jupiter Service Error")

        mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        jup = JupiterClient(http_client=mock_client)

        with pytest.raises(JupiterApiError) as exc_info:
            await jup.get_quote(
                input_mint="So11111111111111111111111111111111111111112",
                output_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                amount_in=1_000_000_000,
                slippage_bps=50,
            )
        assert "status 500" in str(exc_info.value)

    async def test_get_swap_transaction_success(self, direct_quote_payload: dict, swap_tx_payload: dict):
        def handler(request: httpx.Request):
            assert request.url.path.endswith("/swap")
            return httpx.Response(200, json=swap_tx_payload)

        mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        jup = JupiterClient(http_client=mock_client)

        tx_b64 = await jup.get_swap_transaction(
            quote_response=direct_quote_payload,
            user_public_key="96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5",
        )
        assert tx_b64.startswith("AQAA")


class TestRouteCandidateGenerator:
    async def test_generate_candidates_produces_direct_and_multihop(
        self,
        direct_quote_payload: dict,
        multihop_quote_payload: dict,
        swap_tx_payload: dict,
        valid_wsol_mint: str,
        valid_usdc_mint: str,
        valid_wallet_pubkey: str,
    ):
        """Verify that RouteCandidateGenerator parses quotes into 2 candidates with proper hops and buffers."""
        def handler(request: httpx.Request):
            path = request.url.path
            query = str(request.url.query)

            if path.endswith("/quote"):
                if "onlyDirectRoutes=true" in query:
                    return httpx.Response(200, json=direct_quote_payload)
                else:
                    return httpx.Response(200, json=multihop_quote_payload)
            elif path.endswith("/swap"):
                return httpx.Response(200, json=swap_tx_payload)
            return httpx.Response(404)

        mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        jup_client = JupiterClient(http_client=mock_client)
        generator = RouteCandidateGenerator(jupiter_client=jup_client)

        intent = IntentRequest(
            agent_id="test-synth",
            input_mint=valid_wsol_mint,
            output_mint=valid_usdc_mint,
            amount_in=1_000_000_000,
            min_amount_out=150_000_000,
            max_slippage_bps=50,
            user_wallet=valid_wallet_pubkey,
            created_at_slot=100,
            valid_until_slot=150,
        )

        candidates = await generator.generate_candidates(intent)
        assert len(candidates) == 2

        cand_direct, cand_multihop = candidates[0], candidates[1]

        # Assert Direct Candidate
        assert cand_direct.dex_type == DexType.RAYDIUM
        assert cand_direct.estimated_hops == 1
        assert cand_direct.is_split is False
        assert cand_direct.serialized_tx is not None
        assert cand_direct.get_clamping_buffer() == 1.12

        # Assert Multi-hop Candidate
        assert cand_multihop.estimated_hops == 2
        assert cand_multihop.is_split is True
        assert cand_multihop.serialized_tx is not None
        assert cand_multihop.get_clamping_buffer() == 1.20

    async def test_graceful_fallback_to_synthetic_on_aggregator_failure(
        self,
        valid_wsol_mint: str,
        valid_usdc_mint: str,
        valid_wallet_pubkey: str,
    ):
        """Verify that when Jupiter fails, Gatekeeper falls back gracefully to synthetic paths."""
        def failing_handler(_request: httpx.Request):
            return httpx.Response(503, text="Service Unavailable")

        mock_client = httpx.AsyncClient(transport=httpx.MockTransport(failing_handler))
        jup_client = JupiterClient(http_client=mock_client)
        generator = RouteCandidateGenerator(
            jupiter_client=jup_client, fallback_to_synthetic=True
        )

        intent = IntentRequest(
            agent_id="test-fallback",
            input_mint=valid_wsol_mint,
            output_mint=valid_usdc_mint,
            amount_in=1_000_000_000,
            min_amount_out=150_000_000,
            max_slippage_bps=50,
            user_wallet=valid_wallet_pubkey,
            created_at_slot=100,
            valid_until_slot=150,
        )

        candidates = await generator.generate_candidates(intent)
        assert len(candidates) == 2
        assert "fallback" in candidates[0].candidate_id
        assert "fallback" in candidates[1].candidate_id

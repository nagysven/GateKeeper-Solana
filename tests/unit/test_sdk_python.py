import pytest
from unittest.mock import MagicMock, patch

from gatekeeper_py import (
    GatekeeperClient,
    GatekeeperAsyncClient,
    PreflightEvaluation,
    SavingsMetrics,
    GatekeeperAuthError,
    GatekeeperRateLimitError,
)


def test_client_init():
    client = GatekeeperClient(api_key="gk_test_123", base_url="https://gk.ai-futures-bot.pro/")
    assert client.base_url == "https://gk.ai-futures-bot.pro"
    assert client._get_headers()["X-Gatekeeper-Key"] == "gk_test_123"


def test_client_evaluate_approved():
    client = GatekeeperClient(api_key="gk_test_123")
    mock_payload = {
        "intent_id": "intent-123",
        "decision": "APPROVED",
        "action": "DISPATCH",
        "simulated_compute_units": 42000,
        "clamped_compute_units": 47040,
        "execution_time_ms": 78.5,
        "selected_route": "JUPITER_DIRECT",
        "estimated_hops": 1,
        "clamped_cu_saved": 152960,
        "fees_saved_lamports": 0,
        "rejection_reason": None,
        "rejection_details": None,
        "candidates_evaluated": 2,
    }

    with patch("httpx.Client.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_payload
        mock_post.return_value = mock_response

        eval_res = client.evaluate_intent(
            token_in="So11111111111111111111111111111111111111112",
            token_out="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            amount_in=100_000_000,
        )

        assert isinstance(eval_res, PreflightEvaluation)
        assert eval_res.is_approved is True
        assert eval_res.clamped_compute_units == 47040
        assert eval_res.selected_route == "JUPITER_DIRECT"


def test_client_evaluate_rejected():
    client = GatekeeperClient(api_key="gk_test_123")
    mock_payload = {
        "intent_id": "intent-999",
        "decision": "REJECTED",
        "action": "HARD_ABORT",
        "simulated_compute_units": 0,
        "clamped_compute_units": 0,
        "execution_time_ms": 65.2,
        "selected_route": None,
        "estimated_hops": 0,
        "clamped_cu_saved": 0,
        "fees_saved_lamports": 55000,
        "rejection_reason": "ERR_SLIPPAGE_EXCEEDED",
        "rejection_details": "Swap exceeded tolerance (0x1771)",
        "candidates_evaluated": 2,
    }

    with patch("httpx.Client.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_payload
        mock_post.return_value = mock_response

        eval_res = client.evaluate_intent(
            token_in="So11111111111111111111111111111111111111112",
            token_out="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            amount_in=100_000_000,
        )

        assert eval_res.is_approved is False
        assert eval_res.rejection_reason == "ERR_SLIPPAGE_EXCEEDED"
        assert eval_res.fees_saved_lamports == 55000
        assert eval_res.fees_saved_sol == 0.000055


def test_client_auth_error():
    client = GatekeeperClient(api_key="gk_invalid")
    with patch("httpx.Client.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_post.return_value = mock_response

        with pytest.raises(GatekeeperAuthError):
            client.evaluate_intent(
                token_in="So11111111111111111111111111111111111111112",
                token_out="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                amount_in=100_000_000,
            )


@pytest.mark.asyncio
async def test_async_client_evaluate():
    client = GatekeeperAsyncClient(api_key="gk_test_123")
    mock_payload = {
        "intent_id": "intent-async",
        "decision": "APPROVED",
        "action": "DISPATCH",
        "simulated_compute_units": 38000,
        "clamped_compute_units": 42560,
        "execution_time_ms": 72.1,
        "selected_route": "JUPITER_SPLIT",
        "estimated_hops": 2,
        "clamped_cu_saved": 157440,
        "fees_saved_lamports": 0,
        "rejection_reason": None,
        "rejection_details": None,
        "candidates_evaluated": 2,
    }

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_payload
        mock_post.return_value = mock_response

        eval_res = await client.evaluate_intent(
            token_in="So11111111111111111111111111111111111111112",
            token_out="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            amount_in=100_000_000,
        )

        assert eval_res.is_approved is True
        assert eval_res.clamped_compute_units == 42560

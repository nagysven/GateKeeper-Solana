import json
from pathlib import Path
import httpx
import pytest

from gatekeeper.config import Settings
from gatekeeper.engine.arbitrator import GatekeeperArbitrator
from gatekeeper.engine.simulator import PreFlightSimulator
from gatekeeper.main import app
from gatekeeper.storage.database import DatabaseManager
from gatekeeper.storage.repository import AuditLedgerRepository

TEST_API_KEY = "gk-test-secret-key-12345"


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent.parent / "fixtures" / "simulation_responses"


@pytest.fixture
def raydium_success_payload(fixtures_dir: Path):
    return json.loads((fixtures_dir / "raydium_success.json").read_text(encoding="utf-8"))


@pytest.fixture
def slippage_failure_payload(fixtures_dir: Path):
    return json.loads((fixtures_dir / "slippage_failure.json").read_text(encoding="utf-8"))


@pytest.fixture
async def test_client(tmp_path: Path):
    """Sets up FastAPI app with an isolated test SQLite database and configured API Key."""
    db_path = str(tmp_path / "test_api.db")
    cfg = Settings(DATABASE_PATH=db_path, ENABLE_WAL_MODE=True, API_KEY=TEST_API_KEY)
    db_mgr = DatabaseManager(db_path=db_path, config=cfg)
    await db_mgr.init_db()

    app.state.api_key = TEST_API_KEY
    app.state.db_manager = db_mgr
    app.state.repository = AuditLedgerRepository(db_mgr)
    app.state.simulator = PreFlightSimulator(config=cfg)
    app.state.arbitrator = GatekeeperArbitrator(config=cfg)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


class TestApiEndpoints:
    async def test_health_check_open_without_auth(self, test_client: httpx.AsyncClient):
        """Verify /health is publicly accessible without API-Key header."""
        response = await test_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "gatekeeper"

    async def test_auth_missing_header_rejected_with_401(
        self, test_client: httpx.AsyncClient
    ):
        """Requests without X-Gatekeeper-Key to protected /api/v1 routes return 401."""
        response = await test_client.get("/api/v1/metrics/savings")
        assert response.status_code == 401
        assert "Missing required authentication header" in response.json()["detail"]

    async def test_auth_invalid_header_rejected_with_401(
        self, test_client: httpx.AsyncClient
    ):
        """Requests with invalid X-Gatekeeper-Key return 401."""
        headers = {"X-Gatekeeper-Key": "wrong-key-value"}
        response = await test_client.get("/api/v1/metrics/savings", headers=headers)
        assert response.status_code == 401
        assert "Invalid X-Gatekeeper-Key" in response.json()["detail"]

    async def test_evaluate_intent_successful_dispatch_flow(
        self,
        test_client: httpx.AsyncClient,
        valid_wsol_mint: str,
        valid_usdc_mint: str,
        valid_wallet_pubkey: str,
        raydium_success_payload: dict,
    ):
        # Configure app simulator to return winning simulation
        app.state.simulator = PreFlightSimulator(
            rpc_dispatcher=lambda _c, _i: raydium_success_payload
        )

        headers = {"X-Gatekeeper-Key": TEST_API_KEY}
        payload = {
            "intent": {
                "agent_id": "fastapi-agent-1",
                "input_mint": valid_wsol_mint,
                "output_mint": valid_usdc_mint,
                "amount_in": 1_000_000_000,
                "min_amount_out": 150_000_000,
                "max_slippage_bps": 50,
                "jito_tip_lamports": 15_000,
                "user_wallet": valid_wallet_pubkey,
                "created_at_slot": 280_000_000,
                "valid_until_slot": 280_000_050,
            }
        }

        response = await test_client.post(
            "/api/v1/intent/evaluate", json=payload, headers=headers
        )
        assert response.status_code == 200
        data = response.json()

        assert data["is_valid"] is True
        assert data["action"] == "DISPATCH"
        assert data["selected_candidate"] is not None
        assert data["clamped_compute_units"] == int(44_820 * 1.12)
        assert data["decision_latency_ms"] >= 0.0

    async def test_evaluate_intent_hard_abort_flow(
        self,
        test_client: httpx.AsyncClient,
        valid_wsol_mint: str,
        valid_usdc_mint: str,
        valid_wallet_pubkey: str,
        slippage_failure_payload: dict,
    ):
        app.state.simulator = PreFlightSimulator(
            rpc_dispatcher=lambda _c, _i: slippage_failure_payload
        )

        headers = {"X-Gatekeeper-Key": TEST_API_KEY}
        payload = {
            "intent": {
                "agent_id": "fastapi-agent-2",
                "input_mint": valid_wsol_mint,
                "output_mint": valid_usdc_mint,
                "amount_in": 2_000_000_000,
                "min_amount_out": 300_000_000,
                "max_slippage_bps": 20,
                "jito_tip_lamports": 30_000,
                "user_wallet": valid_wallet_pubkey,
                "created_at_slot": 280_000_000,
                "valid_until_slot": 280_000_050,
            }
        }

        response = await test_client.post(
            "/api/v1/intent/evaluate", json=payload, headers=headers
        )
        assert response.status_code == 200
        data = response.json()

        assert data["is_valid"] is False
        assert data["action"] == "HARD_ABORT"
        assert data["abort_reason"] == "ERR_SLIPPAGE_EXCEEDED"
        assert data["base_fee_saved_lamports"] == 5_000
        assert data["jito_tip_saved_lamports"] == 30_000
        assert data["capital_saved_lamports"] == 2_000_000_000

    async def test_metrics_savings_endpoint(
        self,
        test_client: httpx.AsyncClient,
        valid_wsol_mint: str,
        valid_usdc_mint: str,
        valid_wallet_pubkey: str,
        slippage_failure_payload: dict,
    ):
        headers = {"X-Gatekeeper-Key": TEST_API_KEY}
        app.state.simulator = PreFlightSimulator(
            rpc_dispatcher=lambda _c, _i: slippage_failure_payload
        )
        payload = {
            "intent": {
                "agent_id": "fastapi-agent-3",
                "input_mint": valid_wsol_mint,
                "output_mint": valid_usdc_mint,
                "amount_in": 1_000_000_000,
                "min_amount_out": 150_000_000,
                "max_slippage_bps": 25,
                "jito_tip_lamports": 20_000,
                "user_wallet": valid_wallet_pubkey,
                "created_at_slot": 280_000_000,
                "valid_until_slot": 280_000_050,
            }
        }
        await test_client.post(
            "/api/v1/intent/evaluate", json=payload, headers=headers
        )

        response = await test_client.get("/api/v1/metrics/savings", headers=headers)
        assert response.status_code == 200
        metrics = response.json()

        assert metrics["total_evaluations"] >= 1
        assert metrics["total_hard_aborts"] >= 1
        assert metrics["total_fees_saved_lamports"] >= 25_000
        assert metrics["jito_tip_saved_lamports"] >= 20_000
        assert "ERR_SLIPPAGE_EXCEEDED" in metrics["aborts_by_reason"]

    async def test_invalid_pubkey_returns_422(self, test_client: httpx.AsyncClient):
        headers = {"X-Gatekeeper-Key": TEST_API_KEY}
        invalid_payload = {
            "intent": {
                "agent_id": "malformed-agent",
                "input_mint": "NotAValidPublicKey",
                "output_mint": "AlsoInvalid",
                "amount_in": 100,
                "min_amount_out": 90,
                "max_slippage_bps": 50,
                "user_wallet": "FakeWallet",
                "created_at_slot": 10,
                "valid_until_slot": 20,
            }
        }
        response = await test_client.post(
            "/api/v1/intent/evaluate", json=invalid_payload, headers=headers
        )
        assert response.status_code == 422

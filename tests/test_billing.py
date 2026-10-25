import pytest
from httpx import ASGITransport, AsyncClient

from gatekeeper.config import settings
from gatekeeper.main import app
from gatekeeper.storage.billing_repository import BillingRepository
from gatekeeper.storage.database import DatabaseManager


@pytest.fixture(autouse=True)
async def init_test_db(tmp_path):
    test_db = str(tmp_path / "test_billing.db")
    settings.DATABASE_PATH = test_db
    settings.ENABLE_WAL_MODE = False
    db_manager = DatabaseManager(test_db, settings)
    await db_manager.init_db()
    app.state.db_manager = db_manager
    app.state.repository = None
    from gatekeeper.billing.solana_pay import SolanaPayService
    app.state.billing_repo = BillingRepository(db_manager, settings)
    app.state.solana_pay_service = SolanaPayService(app.state.billing_repo, settings)
    yield
    settings.DATABASE_PATH = "gatekeeper_audit.db"


@pytest.mark.asyncio
async def test_register_api_key_and_check_status():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Register new developer API key
        res = await client.post(
            "/api/v1/billing/keys/register",
            json={"client_name": "TestBot-01", "owner_wallet": "9XdA2scpuFoxtbv74wPhcgghftV56vdY9SsdrFKgxjgw"},
        )
        assert res.status_code == 201
        data = res.json()
        assert data["key_id"].startswith("gk_live_")
        assert data["client_name"] == "TestBot-01"
        assert data["monthly_quota"] == 10000
        assert data["bonus_credits"] == 0

        key_id = data["key_id"]

        # 2. Check key balance & quota status
        status_res = await client.get(f"/api/v1/billing/keys/{key_id}/status")
        assert status_res.status_code == 200
        status_data = status_res.json()
        assert status_data["key_id"] == key_id
        assert status_data["remaining_checks"] == 10000
        assert status_data["total_allowance"] == 10000


@pytest.mark.asyncio
async def test_create_solana_pay_checkout():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Register key
        reg_res = await client.post("/api/v1/billing/keys/register", json={"client_name": "CheckoutBot"})
        key_id = reg_res.json()["key_id"]

        # Create SOL checkout
        sol_res = await client.post(
            "/api/v1/billing/checkout",
            json={"key_id": key_id, "currency": "SOL"},
        )
        assert sol_res.status_code == 200
        sol_data = sol_res.json()
        assert sol_data["amount"] == 0.05
        assert sol_data["currency"] == "SOL"
        assert sol_data["credits_granted"] == 50000
        assert sol_data["recipient"] == "9XdA2scpuFoxtbv74wPhcgghftV56vdY9SsdrFKgxjgw"
        assert sol_data["solana_pay_url"].startswith("solana:9XdA2scpuFoxtbv74wPhcgghftV56vdY9SsdrFKgxjgw?")
        assert "reference=" in sol_data["solana_pay_url"]
        assert "amount=0.05" in sol_data["solana_pay_url"]

        # Create USDC checkout
        usdc_res = await client.post(
            "/api/v1/billing/checkout",
            json={"key_id": key_id, "currency": "USDC"},
        )
        assert usdc_res.status_code == 200
        usdc_data = usdc_res.json()
        assert usdc_data["amount"] == 10.0
        assert usdc_data["currency"] == "USDC"
        assert "spl-token=" in usdc_data["solana_pay_url"]


@pytest.mark.asyncio
async def test_payment_confirmation_and_credit_addition():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        reg_res = await client.post("/api/v1/billing/keys/register", json={"client_name": "CreditBot"})
        key_id = reg_res.json()["key_id"]

        checkout_res = await client.post("/api/v1/billing/checkout", json={"key_id": key_id, "currency": "SOL"})
        reference = checkout_res.json()["reference"]

        # Manually confirm payment in DB to simulate on-chain settlement
        db = app.state.db_manager
        billing_repo = BillingRepository(db, settings)
        await billing_repo.confirm_payment(reference, "mock_solana_signature_5k7...")

        # Poll verification endpoint
        verify_res = await client.get(f"/api/v1/billing/checkout/{reference}/verify")
        assert verify_res.status_code == 200
        verify_data = verify_res.json()
        assert verify_data["confirmed"] is True
        assert verify_data["status"] == "CONFIRMED"
        assert verify_data["credits_granted"] == 50000
        assert verify_data["total_remaining_checks"] == 60000  # 10k free + 50k bonus!

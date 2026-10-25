import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from gatekeeper.billing.solana_pay import SolanaPayService
from gatekeeper.config import settings
from gatekeeper.storage.billing_repository import BillingRepository
from gatekeeper.storage.database import DatabaseManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["Billing & Solana Pay"])


def get_billing_repo(request: Request) -> BillingRepository:
    """Dependency provider for BillingRepository backed by the active DatabaseManager."""
    if hasattr(request.app.state, "billing_repo") and request.app.state.billing_repo:
        return request.app.state.billing_repo
    db = getattr(request.app.state, "db_manager", None) or DatabaseManager(config=settings)
    return BillingRepository(db, settings)


def get_solana_pay_service(
    request: Request,
    repo: BillingRepository = Depends(get_billing_repo),
) -> SolanaPayService:
    """Dependency provider for SolanaPayService."""
    if hasattr(request.app.state, "solana_pay_service") and request.app.state.solana_pay_service:
        return request.app.state.solana_pay_service
    return SolanaPayService(repo, settings)


class RegisterKeyRequest(BaseModel):
    client_name: Optional[str] = Field(default="Autonomous Agent", description="Optional label for the bot/agent.")
    owner_wallet: Optional[str] = Field(default=None, description="Optional Solana wallet of the developer.")


class RegisterKeyResponse(BaseModel):
    key_id: str
    client_name: str
    monthly_quota: int
    bonus_credits: int
    used_this_month: int
    message: str


class CreateCheckoutRequest(BaseModel):
    key_id: str = Field(..., description="API key to receive credited checks.")
    currency: str = Field(default="SOL", description="Payment currency: 'SOL' (0.05 SOL) or 'USDC' (10 USDC).")


class CreateCheckoutResponse(BaseModel):
    payment_id: str
    key_id: str
    reference: str
    recipient: str
    amount: float
    currency: str
    credits_granted: int
    solana_pay_url: str
    status: str
    instructions: str


class KeyStatusResponse(BaseModel):
    key_id: str
    client_name: str
    is_active: bool
    monthly_quota: int
    bonus_credits: int
    used_this_month: int
    total_allowance: int
    remaining_checks: int
    current_month: str


class VerifyPaymentResponse(BaseModel):
    confirmed: bool
    status: str
    message: str
    reference: str
    signature: Optional[str] = None
    credits_granted: Optional[int] = None
    total_remaining_checks: Optional[int] = None


@router.post("/keys/register", response_model=RegisterKeyResponse, status_code=status.HTTP_201_CREATED)
async def register_api_key(
    req: RegisterKeyRequest,
    repo: BillingRepository = Depends(get_billing_repo),
):
    """Instantly registers a new developer API key with Free Tier quota (10,000 checks/month)."""
    try:
        key_data = await repo.create_api_key(
            client_name=req.client_name or "Autonomous Agent",
            owner_wallet=req.owner_wallet,
        )
        return RegisterKeyResponse(
            key_id=key_data["key_id"],
            client_name=key_data["client_name"],
            monthly_quota=key_data["monthly_quota"],
            bonus_credits=key_data["bonus_credits"],
            used_this_month=key_data["used_this_month"],
            message="Developer API key generated successfully. Add to X-Gatekeeper-Key header.",
        )
    except Exception as e:
        logger.error("Failed to create API key: %s", e)
        raise HTTPException(status_code=500, detail="Failed to generate API key")


@router.get("/keys/{key_id}/status", response_model=KeyStatusResponse)
async def get_key_status(
    key_id: str,
    repo: BillingRepository = Depends(get_billing_repo),
):
    """Fetches remaining checks and quota for an API key."""
    key_data = await repo.get_api_key(key_id)
    if not key_data:
        raise HTTPException(status_code=404, detail="API key not found")

    total_allowance = key_data["monthly_quota"] + key_data["bonus_credits"]
    remaining = max(0, total_allowance - key_data["used_this_month"])

    return KeyStatusResponse(
        key_id=key_data["key_id"],
        client_name=key_data["client_name"],
        is_active=bool(key_data["is_active"]),
        monthly_quota=key_data["monthly_quota"],
        bonus_credits=key_data["bonus_credits"],
        used_this_month=key_data["used_this_month"],
        total_allowance=total_allowance,
        remaining_checks=remaining,
        current_month=key_data["current_month"],
    )


@router.post("/checkout", response_model=CreateCheckoutResponse)
async def create_checkout(
    req: CreateCheckoutRequest,
    repo: BillingRepository = Depends(get_billing_repo),
    pay_service: SolanaPayService = Depends(get_solana_pay_service),
):
    """Creates a Solana Pay payment request for purchasing +50,000 extra pre-flight checks."""
    key_data = await repo.get_api_key(req.key_id)
    if not key_data:
        raise HTTPException(status_code=404, detail="API key not found")

    try:
        checkout = await pay_service.create_checkout(
            key_id=req.key_id,
            currency=req.currency,
        )
        return CreateCheckoutResponse(**checkout)
    except Exception as e:
        logger.error("Failed to create Solana Pay checkout: %s", e)
        raise HTTPException(status_code=500, detail=f"Checkout creation failed: {str(e)}")


@router.get("/checkout/{reference}/verify", response_model=VerifyPaymentResponse)
async def verify_checkout(
    reference: str,
    pay_service: SolanaPayService = Depends(get_solana_pay_service),
):
    """Verifies on-chain payment for a reference address and credits the user's API key."""
    confirmed, result = await pay_service.verify_payment(reference)

    payment = result.get("payment", {})
    key_data = result.get("api_key")

    remaining = None
    if key_data:
        total = key_data.get("monthly_quota", 0) + key_data.get("bonus_credits", 0)
        remaining = max(0, total - key_data.get("used_this_month", 0))

    return VerifyPaymentResponse(
        confirmed=confirmed,
        status=result.get("status", "PENDING"),
        message=result.get("message") or result.get("error", "Payment pending verification"),
        reference=reference,
        signature=result.get("signature"),
        credits_granted=payment.get("credits_granted") if confirmed else None,
        total_remaining_checks=remaining,
    )

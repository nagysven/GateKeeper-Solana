import logging
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode

import httpx
from solders.keypair import Keypair
from solders.pubkey import Pubkey

from gatekeeper.config import Settings, settings as global_settings
from gatekeeper.storage.billing_repository import BillingRepository

logger = logging.getLogger(__name__)


class SolanaPayService:
    """Implements the official Solana Pay specification for on-chain Top-Up billing."""

    def __init__(
        self,
        billing_repo: BillingRepository,
        config: Optional[Settings] = None,
    ):
        self.repo = billing_repo
        self.config = config or global_settings

    def generate_reference(self) -> str:
        """Generates an ephemeral, unique Base58 public key used as the Solana Pay reference."""
        ephemeral = Keypair()
        return str(ephemeral.pubkey())

    async def create_checkout(
        self,
        key_id: str,
        currency: str = "SOL",
    ) -> Dict[str, Any]:
        """Creates a Solana Pay payment request and registers it in the ledger."""
        currency_clean = currency.upper().strip()
        recipient = self.config.TREASURY_WALLET_ADDRESS

        if currency_clean == "USDC":
            amount = self.config.TOPUP_USDC_PRICE
            token_mint = self.config.USDC_MINT_ADDRESS
        else:
            currency_clean = "SOL"
            amount = self.config.TOPUP_SOL_PRICE
            token_mint = None

        credits = self.config.TOPUP_CREDITS
        reference = self.generate_reference()

        # Build Solana Pay standard URL query params
        params: Dict[str, str] = {
            "amount": str(amount),
            "reference": reference,
            "label": "Project Gatekeeper",
            "message": f"{credits:,} Pre-Flight Checks Top-Up",
        }
        if token_mint:
            params["spl-token"] = token_mint

        solana_pay_url = f"solana:{recipient}?{urlencode(params)}"

        # Save to database
        payment_record = await self.repo.create_payment_intent(
            key_id=key_id,
            reference=reference,
            recipient=recipient,
            amount=amount,
            currency=currency_clean,
            credits_granted=credits,
        )

        return {
            "payment_id": payment_record["payment_id"],
            "key_id": key_id,
            "reference": reference,
            "recipient": recipient,
            "amount": amount,
            "currency": currency_clean,
            "credits_granted": credits,
            "solana_pay_url": solana_pay_url,
            "status": "PENDING",
            "instructions": f"Send {amount} {currency_clean} to {recipient} using the provided Solana Pay link or QR code.",
        }

    async def verify_payment(self, reference: str) -> Tuple[bool, Dict[str, Any]]:
        """Verifies on-chain payment against the Solana RPC cluster using reference address."""
        payment = await self.repo.get_payment_by_reference(reference)
        if not payment:
            return False, {"error": "Payment request not found"}

        if payment["status"] == "CONFIRMED":
            key_data = await self.repo.get_api_key(payment["key_id"])
            return True, {
                "status": "CONFIRMED",
                "payment": payment,
                "api_key": key_data,
                "message": "Payment already confirmed and credited.",
            }

        # Query Solana RPC for transactions including this reference address
        rpc_url = self.config.RPC_URL
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getSignaturesForAddress",
            "params": [
                reference,
                {"limit": 5, "commitment": self.config.COMMITMENT},
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(rpc_url, json=payload)
                res.raise_for_status()
                data = res.json()

            signatures = data.get("result", [])
            if not signatures:
                return False, {
                    "status": "PENDING",
                    "payment": payment,
                    "message": "No confirmed transaction detected on-chain yet.",
                }

            # Check latest signature
            tx_info = signatures[0]
            signature = tx_info.get("signature")
            if tx_info.get("err"):
                return False, {
                    "status": "FAILED",
                    "payment": payment,
                    "signature": signature,
                    "error": f"On-chain transaction failed: {tx_info.get('err')}",
                }

            # Transaction landed successfully and has 0 error!
            # Confirm and credit user
            confirmed_payment = await self.repo.confirm_payment(reference, signature)
            key_data = await self.repo.get_api_key(payment["key_id"])

            return True, {
                "status": "CONFIRMED",
                "payment": confirmed_payment,
                "api_key": key_data,
                "signature": signature,
                "message": f"Successfully confirmed! Credited {payment['credits_granted']:,} checks to {payment['key_id']}.",
            }

        except Exception as e:
            logger.error("Error verifying payment for reference %s: %s", reference, e)
            return False, {
                "status": "PENDING",
                "payment": payment,
                "error": f"RPC verification check failed: {str(e)}",
            }

import logging
import time
import uuid
from typing import Any, Dict, Optional

from gatekeeper.config import Settings, settings as global_settings
from gatekeeper.storage.database import DatabaseManager

logger = logging.getLogger(__name__)


class BillingRepository:
    """Repository for API Key management and Solana Pay transaction reconciliation."""

    def __init__(self, db_manager: DatabaseManager, config: Optional[Settings] = None):
        self.db = db_manager
        self.config = config or global_settings

    async def create_api_key(
        self,
        client_name: str = "Developer",
        owner_wallet: Optional[str] = None,
        monthly_quota: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Creates a new API key with Free-Tier quota."""
        key_id = f"gk_live_{uuid.uuid4().hex}"
        quota = monthly_quota or self.config.FREE_TIER_MONTHLY_QUOTA
        current_month = time.strftime("%Y-%m")

        query = """
            INSERT INTO api_keys (
                key_id, client_name, owner_wallet, monthly_quota,
                bonus_credits, used_this_month, current_month, is_active
            ) VALUES (?, ?, ?, ?, 0, 0, ?, 1)
        """
        async with self.db.get_connection() as conn:
            await conn.execute(query, (key_id, client_name, owner_wallet, quota, current_month))
            await conn.commit()

        logger.info("Created new API key %s for %s (quota: %d)", key_id, client_name, quota)
        return {
            "key_id": key_id,
            "client_name": client_name,
            "owner_wallet": owner_wallet,
            "monthly_quota": quota,
            "bonus_credits": 0,
            "used_this_month": 0,
            "current_month": current_month,
            "is_active": True,
        }

    async def get_api_key(self, key_id: str) -> Optional[Dict[str, Any]]:
        """Fetches API key metadata and automatically reconciles monthly reset if needed."""
        current_month = time.strftime("%Y-%m")
        query = "SELECT * FROM api_keys WHERE key_id = ?"

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(query, (key_id,))
            row = await cursor.fetchone()
            if not row:
                return None

            data = dict(row)
            # Automatic monthly counter reset if month rolled over
            if data["current_month"] != current_month:
                reset_query = """
                    UPDATE api_keys 
                    SET used_this_month = 0, current_month = ?
                    WHERE key_id = ?
                """
                await conn.execute(reset_query, (current_month, key_id))
                await conn.commit()
                data["used_this_month"] = 0
                data["current_month"] = current_month

            return data

    async def check_and_increment_usage(self, key_id: str) -> tuple[bool, Dict[str, Any]]:
        """Checks if key has quota remaining and increments usage counter atomically.

        Total capacity = monthly_quota + bonus_credits.
        Returns: (allowed: bool, key_info: dict)
        """
        key_data = await self.get_api_key(key_id)
        if not key_data or not key_data["is_active"]:
            return False, {"error": "Invalid or deactivated API key"}

        total_allowance = key_data["monthly_quota"] + key_data["bonus_credits"]
        current_used = key_data["used_this_month"]

        if current_used >= total_allowance:
            return False, {
                "allowed": False,
                "used": current_used,
                "allowance": total_allowance,
                "monthly_quota": key_data["monthly_quota"],
                "bonus_credits": key_data["bonus_credits"],
                "reason": "Request quota exhausted. Top up credits with Solana Pay.",
            }

        # Increment usage
        async with self.db.get_connection() as conn:
            await conn.execute(
                "UPDATE api_keys SET used_this_month = used_this_month + 1 WHERE key_id = ?",
                (key_id,),
            )
            await conn.commit()

        key_data["used_this_month"] = current_used + 1
        key_data["remaining"] = total_allowance - (current_used + 1)
        return True, key_data

    async def add_bonus_credits(self, key_id: str, credits: int) -> bool:
        """Adds purchased bonus credits to an API key."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "UPDATE api_keys SET bonus_credits = bonus_credits + ? WHERE key_id = ?",
                (credits, key_id),
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def create_payment_intent(
        self,
        key_id: str,
        reference: str,
        recipient: str,
        amount: float,
        currency: str,
        credits_granted: int,
    ) -> Dict[str, Any]:
        """Records a new pending Solana Pay payment intent."""
        payment_id = f"pay_{uuid.uuid4().hex}"
        query = """
            INSERT INTO payment_transactions (
                payment_id, key_id, reference, recipient, amount, currency,
                credits_granted, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING')
        """
        async with self.db.get_connection() as conn:
            await conn.execute(
                query,
                (payment_id, key_id, reference, recipient, amount, currency, credits_granted),
            )
            await conn.commit()

        return {
            "payment_id": payment_id,
            "key_id": key_id,
            "reference": reference,
            "recipient": recipient,
            "amount": amount,
            "currency": currency,
            "credits_granted": credits_granted,
            "status": "PENDING",
        }

    async def get_payment_by_reference(self, reference: str) -> Optional[Dict[str, Any]]:
        """Retrieves payment details by its unique Solana Pay reference address."""
        query = "SELECT * FROM payment_transactions WHERE reference = ?"
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(query, (reference,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def confirm_payment(self, reference: str, signature: str) -> Optional[Dict[str, Any]]:
        """Marks a payment as CONFIRMED and credits the associated API key."""
        payment = await self.get_payment_by_reference(reference)
        if not payment:
            return None

        if payment["status"] == "CONFIRMED":
            return payment  # Already confirmed

        async with self.db.get_connection() as conn:
            # Update payment transaction
            update_query = """
                UPDATE payment_transactions
                SET status = 'CONFIRMED', signature = ?, confirmed_at = CURRENT_TIMESTAMP
                WHERE reference = ?
            """
            await conn.execute(update_query, (signature, reference))

            # Credit API key
            credit_query = """
                UPDATE api_keys
                SET bonus_credits = bonus_credits + ?
                WHERE key_id = ?
            """
            await conn.execute(credit_query, (payment["credits_granted"], payment["key_id"]))
            await conn.commit()

        payment["status"] = "CONFIRMED"
        payment["signature"] = signature
        logger.info(
            "Payment %s CONFIRMED. Credited %d units to key %s (tx: %s)",
            payment["payment_id"],
            payment["credits_granted"],
            payment["key_id"],
            signature,
        )
        return payment

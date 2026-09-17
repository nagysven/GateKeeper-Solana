import uuid
from typing import Any, Dict, Optional
import httpx

from gatekeeper_py.exceptions import (
    GatekeeperAuthError,
    GatekeeperConnectionError,
    GatekeeperError,
    GatekeeperRateLimitError,
)
from gatekeeper_py.models import PreflightEvaluation, SavingsMetrics


class GatekeeperClient:
    """Synchronous Gatekeeper Client for AI Agent transaction protection."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://gk.ai-futures-bot.pro",
        timeout_seconds: float = 10.0,
    ):
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout_seconds

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-Gatekeeper-Key": self.api_key,
            "User-Agent": "gatekeeper-py/0.1.0",
        }

    def check_health(self) -> Dict[str, Any]:
        """Check gateway liveness."""
        url = f"{self.base_url}/health"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url)
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            raise GatekeeperConnectionError(f"Health check failed: {e}") from e

    def evaluate_intent(
        self,
        token_in: str,
        token_out: str,
        amount_in: int,
        max_slippage_bps: int = 50,
        priority_fee_cap_lamports: int = 100_000,
        min_amount_out: Optional[int] = None,
        user_wallet: Optional[str] = None,
        created_at_slot: Optional[int] = None,
        valid_until_slot: Optional[int] = None,
        intent_id: Optional[str] = None,
    ) -> PreflightEvaluation:
        """Evaluate a swap intent deterministically before broadcasting to Solana."""
        url = f"{self.base_url}/api/v1/preflight"
        payload: Dict[str, Any] = {
            "intent_id": intent_id or f"intent-{uuid.uuid4().hex[:8]}",
            "token_in": token_in,
            "token_out": token_out,
            "amount_in": amount_in,
            "max_slippage_bps": max_slippage_bps,
            "priority_fee_cap_lamports": priority_fee_cap_lamports,
        }
        if min_amount_out is not None:
            payload["min_amount_out"] = min_amount_out
        if user_wallet:
            payload["user_wallet"] = user_wallet
        if created_at_slot is not None:
            payload["created_at_slot"] = created_at_slot
        if valid_until_slot is not None:
            payload["valid_until_slot"] = valid_until_slot

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(url, json=payload, headers=self._get_headers())
                if resp.status_code == 401:
                    raise GatekeeperAuthError("Invalid or missing X-Gatekeeper-Key.")
                if resp.status_code == 429:
                    raise GatekeeperRateLimitError("Monthly quota or rate limit exceeded.")
                resp.raise_for_status()
                return PreflightEvaluation(**resp.json())
        except (GatekeeperAuthError, GatekeeperRateLimitError):
            raise
        except httpx.HTTPStatusError as e:
            raise GatekeeperError(f"Gatekeeper API HTTP {e.response.status_code}: {e.response.text}") from e
        except Exception as e:
            raise GatekeeperConnectionError(f"Connection to Gatekeeper failed: {e}") from e

    def get_metrics(self) -> SavingsMetrics:
        """Fetch cumulative savings and firewall metrics."""
        url = f"{self.base_url}/api/v1/metrics/savings"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, headers=self._get_headers())
                if resp.status_code == 401:
                    raise GatekeeperAuthError("Invalid or missing X-Gatekeeper-Key.")
                resp.raise_for_status()
                return SavingsMetrics(**resp.json())
        except GatekeeperAuthError:
            raise
        except Exception as e:
            raise GatekeeperConnectionError(f"Failed to fetch metrics: {e}") from e


class GatekeeperAsyncClient:
    """Asynchronous Gatekeeper Client for high-throughput AI agents."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://gk.ai-futures-bot.pro",
        timeout_seconds: float = 10.0,
    ):
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout_seconds

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-Gatekeeper-Key": self.api_key,
            "User-Agent": "gatekeeper-py/0.1.0",
        }

    async def check_health(self) -> Dict[str, Any]:
        url = f"{self.base_url}/health"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            raise GatekeeperConnectionError(f"Health check failed: {e}") from e

    async def evaluate_intent(
        self,
        token_in: str,
        token_out: str,
        amount_in: int,
        max_slippage_bps: int = 50,
        priority_fee_cap_lamports: int = 100_000,
        min_amount_out: Optional[int] = None,
        user_wallet: Optional[str] = None,
        created_at_slot: Optional[int] = None,
        valid_until_slot: Optional[int] = None,
        intent_id: Optional[str] = None,
    ) -> PreflightEvaluation:
        url = f"{self.base_url}/api/v1/preflight"
        payload: Dict[str, Any] = {
            "intent_id": intent_id or f"intent-{uuid.uuid4().hex[:8]}",
            "token_in": token_in,
            "token_out": token_out,
            "amount_in": amount_in,
            "max_slippage_bps": max_slippage_bps,
            "priority_fee_cap_lamports": priority_fee_cap_lamports,
        }
        if min_amount_out is not None:
            payload["min_amount_out"] = min_amount_out
        if user_wallet:
            payload["user_wallet"] = user_wallet
        if created_at_slot is not None:
            payload["created_at_slot"] = created_at_slot
        if valid_until_slot is not None:
            payload["valid_until_slot"] = valid_until_slot

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, json=payload, headers=self._get_headers())
                if resp.status_code == 401:
                    raise GatekeeperAuthError("Invalid or missing X-Gatekeeper-Key.")
                if resp.status_code == 429:
                    raise GatekeeperRateLimitError("Monthly quota or rate limit exceeded.")
                resp.raise_for_status()
                return PreflightEvaluation(**resp.json())
        except (GatekeeperAuthError, GatekeeperRateLimitError):
            raise
        except httpx.HTTPStatusError as e:
            raise GatekeeperError(f"Gatekeeper API HTTP {e.response.status_code}: {e.response.text}") from e
        except Exception as e:
            raise GatekeeperConnectionError(f"Connection to Gatekeeper failed: {e}") from e

    async def get_metrics(self) -> SavingsMetrics:
        url = f"{self.base_url}/api/v1/metrics/savings"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, headers=self._get_headers())
                if resp.status_code == 401:
                    raise GatekeeperAuthError("Invalid or missing X-Gatekeeper-Key.")
                resp.raise_for_status()
                return SavingsMetrics(**resp.json())
        except GatekeeperAuthError:
            raise
        except Exception as e:
            raise GatekeeperConnectionError(f"Failed to fetch metrics: {e}") from e

import logging
from typing import Any, Dict, Optional
import httpx

from gatekeeper.config import Settings, settings as global_settings

logger = logging.getLogger(__name__)


class JupiterApiError(Exception):
    """Raised when Jupiter DEX Aggregator returns an error or invalid response."""
    pass


class JupiterClient:
    """Async Client for Jupiter v6 Quote and Swap API."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        config: Optional[Settings] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        self.config = config or global_settings
        self.base_url = (base_url or self.config.JUPITER_API_URL).rstrip("/")
        self._custom_client = http_client

    async def get_quote(
        self,
        input_mint: str,
        output_mint: str,
        amount_in: int,
        slippage_bps: int,
        only_direct_routes: bool = False,
    ) -> Dict[str, Any]:
        """Fetches an optimal swap quote from Jupiter."""
        url = f"{self.base_url}/quote"
        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": str(amount_in),
            "slippageBps": str(slippage_bps),
            "onlyDirectRoutes": "true" if only_direct_routes else "false",
            "asLegacyTransaction": "false",
        }

        client = self._custom_client or httpx.AsyncClient(timeout=5.0)
        try:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                raise JupiterApiError(
                    f"Jupiter Quote API returned status {resp.status_code}: {resp.text}"
                )
            data = resp.json()
            if not data or "routePlan" not in data:
                raise JupiterApiError(f"Malformed quote received from Jupiter: {data}")
            return data
        except Exception as exc:
            if isinstance(exc, JupiterApiError):
                raise
            raise JupiterApiError(f"Network error querying Jupiter Quote API: {exc}") from exc
        finally:
            if self._custom_client is None:
                await client.aclose()

    async def get_swap_transaction(
        self,
        quote_response: Dict[str, Any],
        user_public_key: str,
    ) -> str:
        """Requests an unsigned Base64-encoded VersionedTransaction wire payload."""
        url = f"{self.base_url}/swap"
        payload = {
            "userPublicKey": user_public_key,
            "quoteResponse": quote_response,
            "wrapAndUnwrapSol": True,
            "dynamicComputeUnitLimit": False,
            "prioritizationFeeLamports": 0,
        }

        client = self._custom_client or httpx.AsyncClient(timeout=5.0)
        try:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                raise JupiterApiError(
                    f"Jupiter Swap API returned status {resp.status_code}: {resp.text}"
                )
            data = resp.json()
            swap_tx = data.get("swapTransaction")
            if not swap_tx:
                raise JupiterApiError(f"No swapTransaction in Jupiter response: {data}")
            return swap_tx
        except Exception as exc:
            if isinstance(exc, JupiterApiError):
                raise
            raise JupiterApiError(f"Network error requesting Jupiter Swap transaction: {exc}") from exc
        finally:
            if self._custom_client is None:
                await client.aclose()

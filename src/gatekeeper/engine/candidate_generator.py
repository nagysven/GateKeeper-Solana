import asyncio
import logging
import uuid
from typing import List, Optional

from gatekeeper.config import Settings, settings as global_settings
from gatekeeper.core.models import (
    DexType,
    IntentRequest,
    RouteCandidate,
)
from gatekeeper.engine.jupiter_client import JupiterApiError, JupiterClient

logger = logging.getLogger(__name__)


class RouteCandidateGenerator:
    """Generates alternative execution route candidates using DEX Aggregator (Jupiter v6)."""

    def __init__(
        self,
        config: Optional[Settings] = None,
        jupiter_client: Optional[JupiterClient] = None,
        fallback_to_synthetic: bool = True,
    ):
        self.config = config or global_settings
        self.jupiter = jupiter_client or JupiterClient(config=self.config)
        self.fallback_to_synthetic = fallback_to_synthetic

    async def generate_candidates(self, intent: IntentRequest) -> List[RouteCandidate]:
        """Synthesizes Route A (Direct single-hop) and Route B (Multi-hop/Optimal Yield) in parallel."""
        try:
            # 1. Concurrently fetch quotes for Direct and Multi-hop routes
            direct_task = self.jupiter.get_quote(
                input_mint=intent.input_mint,
                output_mint=intent.output_mint,
                amount_in=intent.amount_in,
                slippage_bps=intent.max_slippage_bps,
                only_direct_routes=True,
            )
            multihop_task = self.jupiter.get_quote(
                input_mint=intent.input_mint,
                output_mint=intent.output_mint,
                amount_in=intent.amount_in,
                slippage_bps=intent.max_slippage_bps,
                only_direct_routes=False,
            )

            direct_quote, multihop_quote = await asyncio.gather(
                direct_task, multihop_task, return_exceptions=False
            )

            # 2. Concurrently request unsigned swap wire transactions
            direct_tx_task = self.jupiter.get_swap_transaction(
                quote_response=direct_quote,
                user_public_key=intent.user_wallet,
            )
            multihop_tx_task = self.jupiter.get_swap_transaction(
                quote_response=multihop_quote,
                user_public_key=intent.user_wallet,
            )

            direct_tx, multihop_tx = await asyncio.gather(
                direct_tx_task, multihop_tx_task, return_exceptions=False
            )

            # 3. Assemble Route Candidates
            cand_direct = self._build_candidate(
                intent=intent,
                quote=direct_quote,
                serialized_tx=direct_tx,
                forced_direct=True,
            )
            cand_multihop = self._build_candidate(
                intent=intent,
                quote=multihop_quote,
                serialized_tx=multihop_tx,
                forced_direct=False,
            )

            return [cand_direct, cand_multihop]

        except (JupiterApiError, Exception) as exc:
            logger.warning(
                "Jupiter Route Synthesis failed for intent %s: %s",
                intent.intent_id,
                exc,
            )
            if self.fallback_to_synthetic:
                logger.info(
                    "Falling back to synthetic route candidates for intent %s",
                    intent.intent_id,
                )
                return self._generate_synthetic_fallback(intent)
            raise

    def _build_candidate(
        self,
        intent: IntentRequest,
        quote: dict,
        serialized_tx: str,
        forced_direct: bool = False,
    ) -> RouteCandidate:
        """Translates a Jupiter quote into a typed RouteCandidate."""
        route_plan = quote.get("routePlan", [])
        hops = len(route_plan)

        # Detect primary DEX label
        primary_label = "CUSTOM"
        if route_plan:
            first_swap = route_plan[0].get("swapInfo", {})
            label = first_swap.get("label", "").upper()
            if "RAYDIUM" in label:
                primary_label = DexType.RAYDIUM
            elif "ORCA" in label or "WHIRLPOOL" in label:
                primary_label = DexType.ORCA
            elif "METEORA" in label:
                primary_label = DexType.METEORA
            else:
                primary_label = DexType.CUSTOM

        is_split = (hops > 1 or any(p.get("percent", 100) < 100 for p in route_plan))
        dex_type = DexType.SPLIT if (is_split and not forced_direct) else primary_label

        candidate_suffix = "direct" if forced_direct else "optimal"
        candidate_id = f"cand-{candidate_suffix}-{uuid.uuid4().hex[:8]}"

        return RouteCandidate(
            candidate_id=candidate_id,
            intent_id=intent.intent_id,
            dex_type=dex_type,
            route_plan_json=quote,
            is_split=is_split if not forced_direct else False,
            estimated_hops=1 if forced_direct else max(1, hops),
            serialized_tx=serialized_tx,
        )

    def _generate_synthetic_fallback(self, intent: IntentRequest) -> List[RouteCandidate]:
        """Synthetic candidate generator used when aggregator APIs are unreachable."""
        cand1 = RouteCandidate(
            candidate_id=f"cand-fallback-direct-{uuid.uuid4().hex[:8]}",
            intent_id=intent.intent_id,
            dex_type=DexType.RAYDIUM,
            route_plan_json={"strategy": "fallback-direct", "dex": "raydium"},
            is_split=False,
            estimated_hops=1,
            serialized_tx=None,
        )
        cand2 = RouteCandidate(
            candidate_id=f"cand-fallback-multihop-{uuid.uuid4().hex[:8]}",
            intent_id=intent.intent_id,
            dex_type=DexType.ORCA,
            route_plan_json={"strategy": "fallback-multihop", "dex": "orca-whirlpool"},
            is_split=False,
            estimated_hops=2,
            serialized_tx=None,
        )
        return [cand1, cand2]

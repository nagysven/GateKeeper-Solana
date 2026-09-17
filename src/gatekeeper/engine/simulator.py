import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional

from gatekeeper.config import Settings, settings as global_settings
from gatekeeper.core.models import (
    IntentRequest,
    RouteCandidate,
    SimulationResult,
)
from gatekeeper.matrix.contention_checker import ContentionChecker
from gatekeeper.matrix.slippage_validator import SlippageValidator

logger = logging.getLogger(__name__)


class PreFlightSimulator:
    """Asynchronous Pre-Flight Simulation Engine for Solana Route Candidates."""

    def __init__(
        self,
        config: Optional[Settings] = None,
        rpc_dispatcher: Optional[Callable[[RouteCandidate, IntentRequest], Any]] = None,
    ):
        self.config = config or global_settings
        self.rpc_dispatcher = rpc_dispatcher
        self.slippage_validator = SlippageValidator()
        self.contention_checker = ContentionChecker()

    async def simulate_candidate(
        self, candidate: RouteCandidate, intent: IntentRequest
    ) -> SimulationResult:
        """Simulates a single route candidate against cluster state and extracts execution metrics."""
        start_time = time.perf_counter()

        try:
            if self.rpc_dispatcher:
                # Use custom dispatcher / mock if injected
                raw_response = await self._invoke_dispatcher(candidate, intent)
            else:
                # Default mock-safe fallback or live RPC execution
                raw_response = self._create_empty_fallback_response()

            duration_ms = (time.perf_counter() - start_time) * 1000.0
            return self._parse_simulation_response(
                candidate=candidate,
                intent=intent,
                raw_response=raw_response,
                duration_ms=duration_ms,
            )

        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            logger.error(
                "Error during candidate %s simulation: %s",
                candidate.candidate_id,
                exc,
                exc_info=True,
            )
            return SimulationResult(
                candidate_id=candidate.candidate_id,
                success=False,
                consumed_units=0,
                simulated_delta_out=0,
                error_code="SIMULATION_TRANSPORT_ERROR",
                error_log=str(exc),
                simulation_duration_ms=duration_ms,
                simulated_at_slot=intent.created_at_slot,
            )

    async def simulate_all_candidates(
        self, candidates: List[RouteCandidate], intent: IntentRequest
    ) -> List[SimulationResult]:
        """Concurrently simulates 2-3 route candidates using asyncio.gather."""
        if not candidates:
            return []

        tasks = [self.simulate_candidate(candidate, intent) for candidate in candidates]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        return list(results)

    async def _invoke_dispatcher(
        self, candidate: RouteCandidate, intent: IntentRequest
    ) -> Dict[str, Any]:
        """Invokes the async dispatcher (or wraps synchronous mock)."""
        res = self.rpc_dispatcher(candidate, intent)
        if asyncio.iscoroutine(res):
            return await res
        return res

    def _parse_simulation_response(
        self,
        candidate: RouteCandidate,
        intent: IntentRequest,
        raw_response: Dict[str, Any],
        duration_ms: float,
    ) -> SimulationResult:
        """Extracts CUs, logs, balances and errors from Solana JSON-RPC simulation payload."""
        # Normalize result structure (handles {value: ...} or {result: {value: ...}})
        value_data = raw_response.get("value", raw_response.get("result", {}).get("value", raw_response))
        context_data = raw_response.get("context", raw_response.get("result", {}).get("context", {}))
        slot = context_data.get("slot", intent.created_at_slot)

        raw_err = value_data.get("err")
        logs: List[str] = value_data.get("logs") or []
        units_consumed = value_data.get("unitsConsumed", 0)

        pre_balances = value_data.get("preTokenBalances") or []
        post_balances = value_data.get("postTokenBalances") or []

        # 1. Fallback CU extraction from program logs if unitsConsumed is 0
        if units_consumed == 0 and logs:
            units_consumed = self._extract_cu_from_logs(logs)

        # 2. Parse error representations
        error_code = None
        error_log = None
        is_success = (raw_err is None)

        if raw_err:
            error_code = self._extract_error_code(raw_err)
            error_log = "\n".join(logs) if logs else str(raw_err)

        # 3. Check Account Contention
        is_contended, contention_msg = self.contention_checker.check_contention(raw_err, logs)
        if is_contended:
            is_success = False
            error_code = error_code or "AccountInUse"
            error_log = error_log or contention_msg

        # 4. Check Slippage and Balance Deltas
        is_slippage_ok, delta_out, slippage_msg = self.slippage_validator.validate_simulation_slippage(
            intent=intent,
            pre_token_balances=pre_balances,
            post_token_balances=post_balances,
            logs=logs,
            error_code=error_code,
        )

        if not is_slippage_ok:
            is_success = False
            error_code = error_code or "ERR_SLIPPAGE_EXCEEDED"
            error_log = error_log or slippage_msg

        return SimulationResult(
            candidate_id=candidate.candidate_id,
            success=is_success,
            consumed_units=units_consumed,
            simulated_delta_out=delta_out,
            error_code=error_code,
            error_log=error_log,
            simulation_duration_ms=round(duration_ms, 2),
            simulated_at_slot=slot,
        )

    def _extract_cu_from_logs(self, logs: List[str]) -> int:
        """Parses 'Program ... consumed X of Y compute units' from execution logs."""
        max_cu = 0
        for log in logs:
            if "consumed" in log and "compute units" in log:
                parts = log.split()
                try:
                    idx = parts.index("consumed")
                    cu_val = int(parts[idx + 1])
                    if cu_val > max_cu:
                        max_cu = cu_val
                except (ValueError, IndexError):
                    continue
        return max_cu

    def _extract_error_code(self, raw_err: Any) -> str:
        """Translates Solana RPC error structures into identifiable string tokens."""
        if isinstance(raw_err, str):
            return raw_err
        if isinstance(raw_err, dict):
            if "InstructionError" in raw_err:
                ie = raw_err["InstructionError"]
                return f"InstructionError_{ie}"
            return str(raw_err)
        return str(raw_err)

    def _create_empty_fallback_response(self) -> Dict[str, Any]:
        return {
            "context": {"slot": 0},
            "value": {
                "err": "NO_DISPATCHER_CONFIGURED",
                "unitsConsumed": 0,
                "logs": ["Gatekeeper simulator: No RPC client configured."],
                "preTokenBalances": [],
                "postTokenBalances": [],
            },
        }

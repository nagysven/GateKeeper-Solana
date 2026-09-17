from typing import Any, Dict, List, Optional, Tuple

from gatekeeper.core.models import IntentRequest

SLIPPAGE_ERROR_PATTERNS = [
    "0x1771",  # Raydium SlippageExceeded hex
    "6001",  # Anchor / Raydium SlippageExceeded decimal
    "SlippageExceeded",
    "Slippage tolerance exceeded",
    "0x1770",  # Whirlpool / Orca Slippage breach
]


class SlippageValidator:
    """Validates post-simulation token output amounts and AMM slippage tolerances."""

    def validate_simulation_slippage(
        self,
        intent: IntentRequest,
        pre_token_balances: Optional[List[Dict[str, Any]]] = None,
        post_token_balances: Optional[List[Dict[str, Any]]] = None,
        logs: Optional[List[str]] = None,
        error_code: Optional[str] = None,
    ) -> Tuple[bool, int, Optional[str]]:
        """Verifies if the simulated execution meets minimum output threshold.

        Returns:
            (is_valid, simulated_delta_out, error_message)
        """
        # 1. Check for explicit slippage errors in logs or error_code
        if error_code:
            for pattern in SLIPPAGE_ERROR_PATTERNS:
                if pattern.lower() in error_code.lower():
                    return (
                        False,
                        0,
                        f"Simulation rejected by DEX with slippage error: {error_code}",
                    )

        if logs:
            for line in logs:
                for pattern in SLIPPAGE_ERROR_PATTERNS:
                    if pattern.lower() in line.lower():
                        return (
                            False,
                            0,
                            f"Simulation logs reveal slippage failure: '{line.strip()}'",
                        )

        # 2. Extract and compute pre/post token balance deltas for destination wallet
        delta_out = self._calculate_balance_delta(
            output_mint=intent.output_mint,
            wallet_owner=intent.user_wallet,
            pre_balances=pre_token_balances or [],
            post_balances=post_token_balances or [],
        )

        # 3. If balance info is available, verify against intent minimum
        if post_token_balances is not None and len(post_token_balances) > 0:
            if delta_out < intent.min_amount_out:
                return (
                    False,
                    delta_out,
                    f"Slippage exceeded: received delta ({delta_out}) < "
                    f"minimum required ({intent.min_amount_out}).",
                )

        return True, delta_out, None

    def _calculate_balance_delta(
        self,
        output_mint: str,
        wallet_owner: str,
        pre_balances: List[Dict[str, Any]],
        post_balances: List[Dict[str, Any]],
    ) -> int:
        """Finds the output mint balance difference for the wallet."""
        pre_amount = 0
        post_amount = 0

        for bal in pre_balances:
            if bal.get("mint") == output_mint and bal.get("owner") == wallet_owner:
                ui_token = bal.get("uiTokenAmount", {})
                pre_amount = int(ui_token.get("amount", "0"))
                break

        for bal in post_balances:
            if bal.get("mint") == output_mint and bal.get("owner") == wallet_owner:
                ui_token = bal.get("uiTokenAmount", {})
                post_amount = int(ui_token.get("amount", "0"))
                break

        return max(0, post_amount - pre_amount)

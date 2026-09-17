from typing import Any, List, Optional, Tuple

CONTENTION_PATTERNS = [
    "accountinuse",
    "account in use",
    "is locked by another transaction",
    "account is locked",
    "write lock",
]


class ContentionChecker:
    """Detects account write-lock conflicts and Solana cluster account contention."""

    def check_contention(
        self,
        rpc_error: Any,
        logs: Optional[List[str]] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Analyzes RPC error structures and logs for account lock contention.

        Returns:
            (is_contended: bool, error_message: Optional[str])
        """
        # 1. Analyze RPC error object or string
        if rpc_error:
            error_str = str(rpc_error).lower()
            for pattern in CONTENTION_PATTERNS:
                if pattern in error_str:
                    return (
                        True,
                        f"Account contention detected: {rpc_error}",
                    )

        # 2. Check program and simulation logs
        if logs:
            for log_line in logs:
                lower_log = log_line.lower()
                for pattern in CONTENTION_PATTERNS:
                    if pattern in lower_log:
                        return (
                            True,
                            f"Account contention detected in simulation logs: '{log_line.strip()}'",
                        )

        return False, None

from typing import Optional, Tuple

from gatekeeper.config import Settings, settings as global_settings
from gatekeeper.core.models import IntentRequest


class TTLValidator:
    """Deterministic validator for Blockhash and Intent Slot Time-To-Live (TTL)."""

    def __init__(self, config: Optional[Settings] = None):
        self.config = config or global_settings

    def validate_slot_ttl(
        self,
        intent: IntentRequest,
        current_cluster_slot: int,
        blockhash_slot: Optional[int] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Evaluates whether the intent and blockhash are within safe flight parameters.

        Returns:
            (is_valid, error_message)
        """
        # 1. Check if intent has already expired past valid_until_slot
        if current_cluster_slot > intent.valid_until_slot:
            return (
                False,
                f"Intent expired: current slot ({current_cluster_slot}) > "
                f"valid_until_slot ({intent.valid_until_slot}).",
            )

        # 2. Check if remaining slots are below safety flight buffer
        remaining_slots = intent.valid_until_slot - current_cluster_slot
        if remaining_slots < self.config.MIN_SLOT_BUFFER:
            return (
                False,
                f"Insufficient execution window: remaining slots ({remaining_slots}) < "
                f"min buffer ({self.config.MIN_SLOT_BUFFER}).",
            )

        # 3. Check blockhash slot age if blockhash_slot is provided
        if blockhash_slot is not None:
            if current_cluster_slot < blockhash_slot:
                return (
                    False,
                    f"Invalid blockhash slot ({blockhash_slot}) in future relative to "
                    f"current cluster slot ({current_cluster_slot}).",
                )

            age_slots = current_cluster_slot - blockhash_slot
            if age_slots >= self.config.MAX_BLOCKHASH_AGE_SLOTS:
                return (
                    False,
                    f"Blockhash expired: age ({age_slots} slots) >= "
                    f"max allowed ({self.config.MAX_BLOCKHASH_AGE_SLOTS} slots).",
                )

        return True, None

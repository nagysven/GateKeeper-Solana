from gatekeeper.config import Settings
from gatekeeper.core.models import IntentRequest
from gatekeeper.matrix.contention_checker import ContentionChecker
from gatekeeper.matrix.slippage_validator import SlippageValidator
from gatekeeper.matrix.ttl_validator import TTLValidator


class TestTTLValidator:
    def test_valid_slot_range(
        self, valid_wsol_mint: str, valid_usdc_mint: str, valid_wallet_pubkey: str
    ):
        settings = Settings(MIN_SLOT_BUFFER=10, MAX_BLOCKHASH_AGE_SLOTS=120)
        validator = TTLValidator(settings)

        intent = IntentRequest(
            agent_id="test",
            input_mint=valid_wsol_mint,
            output_mint=valid_usdc_mint,
            amount_in=1_000,
            min_amount_out=100,
            max_slippage_bps=50,
            user_wallet=valid_wallet_pubkey,
            created_at_slot=100,
            valid_until_slot=150,
        )

        # Current slot 120 (30 slots remaining, blockhash age 20) -> Valid
        is_valid, err = validator.validate_slot_ttl(
            intent=intent, current_cluster_slot=120, blockhash_slot=100
        )
        assert is_valid is True
        assert err is None

    def test_intent_expired(
        self, valid_wsol_mint: str, valid_usdc_mint: str, valid_wallet_pubkey: str
    ):
        validator = TTLValidator()
        intent = IntentRequest(
            agent_id="test",
            input_mint=valid_wsol_mint,
            output_mint=valid_usdc_mint,
            amount_in=1_000,
            min_amount_out=100,
            max_slippage_bps=50,
            user_wallet=valid_wallet_pubkey,
            created_at_slot=100,
            valid_until_slot=150,
        )

        is_valid, err = validator.validate_slot_ttl(intent=intent, current_cluster_slot=151)
        assert is_valid is False
        assert "Intent expired" in err

    def test_insufficient_slot_buffer(
        self, valid_wsol_mint: str, valid_usdc_mint: str, valid_wallet_pubkey: str
    ):
        settings = Settings(MIN_SLOT_BUFFER=10)
        validator = TTLValidator(settings)
        intent = IntentRequest(
            agent_id="test",
            input_mint=valid_wsol_mint,
            output_mint=valid_usdc_mint,
            amount_in=1_000,
            min_amount_out=100,
            max_slippage_bps=50,
            user_wallet=valid_wallet_pubkey,
            created_at_slot=100,
            valid_until_slot=150,
        )

        # 150 - 145 = 5 slots remaining < 10
        is_valid, err = validator.validate_slot_ttl(intent=intent, current_cluster_slot=145)
        assert is_valid is False
        assert "Insufficient execution window" in err

    def test_blockhash_expired(
        self, valid_wsol_mint: str, valid_usdc_mint: str, valid_wallet_pubkey: str
    ):
        settings = Settings(MAX_BLOCKHASH_AGE_SLOTS=120)
        validator = TTLValidator(settings)
        intent = IntentRequest(
            agent_id="test",
            input_mint=valid_wsol_mint,
            output_mint=valid_usdc_mint,
            amount_in=1_000,
            min_amount_out=100,
            max_slippage_bps=50,
            user_wallet=valid_wallet_pubkey,
            created_at_slot=100,
            valid_until_slot=350,
        )

        # Current 230 - blockhash 100 = 130 slots >= 120
        is_valid, err = validator.validate_slot_ttl(
            intent=intent, current_cluster_slot=230, blockhash_slot=100
        )
        assert is_valid is False
        assert "Blockhash expired" in err


class TestSlippageValidator:
    def test_slippage_ok_with_positive_delta(
        self, valid_wsol_mint: str, valid_usdc_mint: str, valid_wallet_pubkey: str
    ):
        validator = SlippageValidator()
        intent = IntentRequest(
            agent_id="test",
            input_mint=valid_wsol_mint,
            output_mint=valid_usdc_mint,
            amount_in=1_000,
            min_amount_out=100,
            max_slippage_bps=50,
            user_wallet=valid_wallet_pubkey,
            created_at_slot=100,
            valid_until_slot=150,
        )

        pre_balances = [
            {
                "mint": valid_usdc_mint,
                "owner": valid_wallet_pubkey,
                "uiTokenAmount": {"amount": "1000"},
            }
        ]
        post_balances = [
            {
                "mint": valid_usdc_mint,
                "owner": valid_wallet_pubkey,
                "uiTokenAmount": {"amount": "1150"},
            }
        ]

        is_valid, delta, err = validator.validate_simulation_slippage(
            intent=intent,
            pre_token_balances=pre_balances,
            post_token_balances=post_balances,
        )

        assert is_valid is True
        assert delta == 150
        assert err is None

    def test_slippage_breach_detected(
        self, valid_wsol_mint: str, valid_usdc_mint: str, valid_wallet_pubkey: str
    ):
        validator = SlippageValidator()
        intent = IntentRequest(
            agent_id="test",
            input_mint=valid_wsol_mint,
            output_mint=valid_usdc_mint,
            amount_in=1_000,
            min_amount_out=100,
            max_slippage_bps=50,
            user_wallet=valid_wallet_pubkey,
            created_at_slot=100,
            valid_until_slot=150,
        )

        pre_balances = [
            {
                "mint": valid_usdc_mint,
                "owner": valid_wallet_pubkey,
                "uiTokenAmount": {"amount": "1000"},
            }
        ]
        post_balances = [
            {
                "mint": valid_usdc_mint,
                "owner": valid_wallet_pubkey,
                "uiTokenAmount": {"amount": "1080"},  # only +80 vs 100 required
            }
        ]

        is_valid, delta, err = validator.validate_simulation_slippage(
            intent=intent,
            pre_token_balances=pre_balances,
            post_token_balances=post_balances,
        )

        assert is_valid is False
        assert delta == 80
        assert "Slippage exceeded" in err

    def test_slippage_log_error_detection(
        self, valid_wsol_mint: str, valid_usdc_mint: str, valid_wallet_pubkey: str
    ):
        validator = SlippageValidator()
        intent = IntentRequest(
            agent_id="test",
            input_mint=valid_wsol_mint,
            output_mint=valid_usdc_mint,
            amount_in=1_000,
            min_amount_out=100,
            max_slippage_bps=50,
            user_wallet=valid_wallet_pubkey,
            created_at_slot=100,
            valid_until_slot=150,
        )

        logs = [
            "Program 675k... invoke [1]",
            "Program log: Error Code: SlippageExceeded (0x1771). Error Number: 6001.",
            "Program 675k... failed: custom program error: 0x1771",
        ]

        is_valid, delta, err = validator.validate_simulation_slippage(
            intent=intent, logs=logs
        )
        assert is_valid is False
        assert "slippage failure" in err


class TestContentionChecker:
    def test_no_contention(self):
        checker = ContentionChecker()
        is_contended, err = checker.check_contention(rpc_error=None, logs=["Program success"])
        assert is_contended is False
        assert err is None

    def test_account_in_use_error_object(self):
        checker = ContentionChecker()
        is_contended, err = checker.check_contention(rpc_error="AccountInUse")
        assert is_contended is True
        assert "Account contention detected" in err

    def test_account_locked_in_logs(self):
        checker = ContentionChecker()
        logs = ["Account CAMM... is locked by another transaction"]
        is_contended, err = checker.check_contention(rpc_error=None, logs=logs)
        assert is_contended is True
        assert "Account contention detected in simulation logs" in err

import pytest
from gatekeeper.config import Settings


@pytest.fixture
def custom_settings() -> Settings:
    """Fixture providing customizable Gatekeeper settings for testing."""
    return Settings(
        DIRECT_SWAP_CLAMPING_BUFFER=1.12,
        MULTI_HOP_CLAMPING_BUFFER=1.20,
        BASE_FEE_LAMPORTS=5_000,
        DEFAULT_PRIORITY_FEE_MICRO_LAMPORTS=50_000,
        DEFAULT_JITO_TIP_LAMPORTS=10_000,
    )


@pytest.fixture
def valid_wsol_mint() -> str:
    return "So11111111111111111111111111111111111111112"


@pytest.fixture
def valid_usdc_mint() -> str:
    return "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


@pytest.fixture
def valid_wallet_pubkey() -> str:
    return "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5"

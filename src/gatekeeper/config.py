from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GATEKEEPER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Security & Authentication
    API_KEY: str = Field(
        default="gk-sec-master-key-change-in-prod",
        description="Master API key required for X-Gatekeeper-Key header authentication.",
    )

    # Solana Network & RPC Configuration
    RPC_URL: str = Field(
        default="https://api.mainnet-beta.solana.com",
        description="Solana RPC endpoint URL for pre-flight simulations.",
    )
    WSS_URL: str = Field(
        default="wss://api.mainnet-beta.solana.com",
        description="Solana WebSocket endpoint URL for slot/blockhash subscriptions.",
    )
    COMMITMENT: str = Field(
        default="confirmed",
        description="Cluster commitment level used for simulations and checks.",
    )

    # Dynamic Compute-Budget Clamping Buffers
    DIRECT_SWAP_CLAMPING_BUFFER: float = Field(
        default=1.12,
        ge=1.0,
        le=2.0,
        description="Safety multiplier for direct single-hop swaps (default +12%).",
    )
    MULTI_HOP_CLAMPING_BUFFER: float = Field(
        default=1.20,
        ge=1.0,
        le=2.0,
        description="Safety multiplier for multi-hop or split routes (default +20%).",
    )
    MIN_COMPUTE_UNITS: int = Field(
        default=1_000,
        ge=500,
        description="Minimum compute units clamp floor.",
    )
    MAX_COMPUTE_UNITS: int = Field(
        default=1_400_000,
        le=1_400_000,
        description="Solana protocol maximum compute unit limit per transaction.",
    )
    DEFAULT_CU_LIMIT: int = Field(
        default=200_000,
        description="Standard fallback compute unit limit.",
    )

    # Fee & Jito Tip Economics
    BASE_FEE_LAMPORTS: int = Field(
        default=5_000,
        description="Solana protocol base signature fee in Lamports.",
    )
    DEFAULT_PRIORITY_FEE_MICRO_LAMPORTS: int = Field(
        default=50_000,
        description="Default priority fee rate in micro-lamports per compute unit.",
    )
    DEFAULT_JITO_TIP_LAMPORTS: int = Field(
        default=10_000,
        ge=0,
        description="Default Jito validator tip in Lamports.",
    )
    JITO_TIP_ACCOUNTS: List[str] = Field(
        default=[
            "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5",
            "HFqU5x63VTxvQssQn138i2NN7MQSueBxWN4HEpcW8KA",
            "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY",
            "ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49",
            "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh",
            "ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt",
            "DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL",
            "3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT",
        ],
        description="Recognized Jito validator tip receiver accounts.",
    )

    # Deterministic Abort Thresholds
    MAX_BLOCKHASH_AGE_SLOTS: int = Field(
        default=120,
        description="Maximum slot age after which a blockhash is considered expired.",
    )
    MIN_SLOT_BUFFER: int = Field(
        default=10,
        description="Minimum slots remaining before intent expiration to allow dispatch.",
    )
    MIN_SOL_RESERVE_LAMPORTS: int = Field(
        default=2_000_000,
        description="Minimum SOL balance (0.002 SOL) required for rent-exemption and fees.",
    )

    # VPS Storage & Telemetry
    DATABASE_PATH: str = Field(
        default="gatekeeper_audit.db",
        description="Local SQLite database file path for audit ledger.",
    )
    ENABLE_WAL_MODE: bool = Field(
        default=True,
        description="Enforce SQLite Write-Ahead Logging for high-throughput concurrency.",
    )
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Standard logging verbosity (DEBUG, INFO, WARNING, ERROR).",
    )


# Singleton settings instance
settings = Settings()

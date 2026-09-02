from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

FORBIDDEN_HL_VARS = ("HL_AGENT_KEY", "HL_MASTER_KEY", "WALLET_HOT_SEED_MAINNET")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    database_url: str = "postgresql+psycopg://otc:otc_local@postgres:5432/otc"
    jwt_secret: str = "local-dev-jwt-not-for-production"
    jwt_alg: str = "HS256"
    hl_network: str = "stub"
    quote_ttl_ms: int = 20_000
    spread_bps: str = "10"
    fee_bps: str = "5"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def assert_local_stub() -> None:
    present = [name for name in FORBIDDEN_HL_VARS if os.environ.get(name)]
    if present:
        names = ", ".join(present)
        raise SystemExit(
            f"Refuse to start: {names} is set. Local stub only; do not provide Hyperliquid keys."
        )
    network = os.environ.get("HL_NETWORK", get_settings().hl_network)
    if network != "stub":
        raise SystemExit("Refuse to start: HL_NETWORK must be stub for this local desk.")

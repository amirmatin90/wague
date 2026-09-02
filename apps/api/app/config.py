from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

TESTNET_API = "https://api.hyperliquid-testnet.xyz"
TESTNET_WS = "wss://api.hyperliquid-testnet.xyz/ws"

FORBIDDEN_KEYS = (
    "HL_MASTER_KEY",
    "HL_WITHDRAW_KEY",
    "HL_AGENT_KEY_MAINNET",
    "WALLET_HOT_SEED_MAINNET",
)

MAINNET_HOST_MARKERS = (
    "https://api.hyperliquid.xyz",
    "wss://api.hyperliquid.xyz",
    "api.hyperliquid.xyz/info",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    database_url: str = "postgresql+psycopg://otc:otc_local@postgres:5432/otc"
    jwt_secret: str = "local-dev-jwt-not-for-production"
    jwt_alg: str = "HS256"
    hl_network: str = "testnet"
    hl_api_url: str = TESTNET_API
    hl_ws_url: str = TESTNET_WS
    quote_ttl_ms: int = 20_000
    spread_bps: str = "10"
    fee_bps: str = "5"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def agent_key() -> str | None:
    key = os.environ.get("HL_AGENT_KEY_TESTNET", "").strip()
    return key or None


def assert_testnet() -> None:
    present = [name for name in FORBIDDEN_KEYS if os.environ.get(name)]
    if present:
        names = ", ".join(present)
        raise SystemExit(f"Refuse to start: {names} is set. Testnet only; no master/withdraw/mainnet keys.")

    for name, value in os.environ.items():
        if not value:
            continue
        lowered = value.strip().lower()
        for marker in MAINNET_HOST_MARKERS:
            if marker in lowered and "testnet" not in lowered:
                raise SystemExit(f"Refuse to start: {name} points at a mainnet Hyperliquid host.")

    network = os.environ.get("HL_NETWORK", get_settings().hl_network).strip().lower()
    if network != "testnet":
        raise SystemExit("Refuse to start: HL_NETWORK must be testnet.")

    api_url = os.environ.get("HL_API_URL", get_settings().hl_api_url).strip()
    if "testnet" not in api_url.lower():
        raise SystemExit("Refuse to start: HL_API_URL must be the Hyperliquid testnet host.")

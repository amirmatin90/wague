from __future__ import annotations

import os
from decimal import Decimal

os.environ.setdefault("HL_NETWORK", "testnet")
os.environ.setdefault("HL_API_URL", "https://api.hyperliquid-testnet.xyz")
os.environ.setdefault("JWT_SECRET", "local-dev-jwt-not-for-production")

import pytest
from fastapi.testclient import TestClient

from app.hyperliquid.client import set_test_book

set_test_book(
    {
        "coin": "@0",
        "asset": 10000,
        "bids": [(Decimal("3490"), Decimal("100"))],
        "asks": [(Decimal("3510"), Decimal("100"))],
        "mid": Decimal("3500"),
    }
)

from app.main import app


@pytest.fixture(autouse=True)
def test_book() -> None:
    set_test_book(
        {
            "coin": "@0",
            "asset": 10000,
            "bids": [(Decimal("3490"), Decimal("100"))],
            "asks": [(Decimal("3510"), Decimal("100"))],
            "mid": Decimal("3500"),
        }
    )
    yield
    set_test_book(None)


@pytest.fixture(scope="session")
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def login(client: TestClient, email: str, password: str) -> str:
    response = client.post("/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth_headers(token: str, key: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if key is not None:
        headers["Idempotency-Key"] = key
    return headers

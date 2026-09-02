from __future__ import annotations

import os
from decimal import Decimal

os.environ.setdefault("HL_NETWORK", "testnet")
os.environ.setdefault("HL_API_URL", "https://api.hyperliquid-testnet.xyz")
os.environ.setdefault("JWT_SECRET", "local-dev-jwt-not-for-production")

import pytest
from fastapi.testclient import TestClient

from sqlalchemy import select

from app.db import SessionLocal
from app.hyperliquid.client import set_test_book
from app.ledger.service import ASSETS, CHAIN_PARTY_ID, get_account, post_entries
from app.models import User

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


def reset_client_books(email: str = "client@desk.local") -> None:
    session = SessionLocal()
    try:
        user = session.scalar(select(User).where(User.email == email))
        if user is None:
            return
        for asset in ASSETS:
            for kind in ("available", "reserved"):
                account = get_account(session, "client", user.id, asset, kind, for_update=True)
                if account is None or account.balance == 0:
                    continue
                chain = get_account(session, "chain", CHAIN_PARTY_ID, asset, "available", for_update=True)
                if chain is None:
                    continue
                post_entries(
                    session,
                    kind="test_reset",
                    trade_id=None,
                    legs=[(account, -account.balance), (chain, account.balance)],
                )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


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
    reset_client_books()
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

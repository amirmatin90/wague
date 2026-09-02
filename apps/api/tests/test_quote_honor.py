from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Quote, Rfq, User
from tests.conftest import auth_headers, login


def test_expired_quote_not_honored(client: TestClient) -> None:
    token = login(client, "client@desk.local", "client-local")
    session = SessionLocal()
    try:
        user = session.scalar(select(User).where(User.email == "client@desk.local"))
        assert user is not None
        from sqlalchemy import func

        db_now = session.scalar(select(func.now()))
        rfq = Rfq(
            user_id=user.id,
            side="buy",
            base="BTC",
            quote_asset="USDC",
            base_qty=Decimal("0.10000000"),
            status="quoted",
        )
        session.add(rfq)
        session.flush()
        quote = Quote(
            rfq_id=rfq.id,
            user_id=user.id,
            side="buy",
            base="BTC",
            quote_asset="USDC",
            base_qty=Decimal("0.10000000"),
            quote_qty=Decimal("9759.75"),
            price=Decimal("97597.50"),
            fee_amount=Decimal("4.88"),
            fee_bps=Decimal("5.00"),
            ttl_ms=1,
            expires_at=db_now - timedelta(seconds=5),
            status="quoted",
        )
        session.add(quote)
        session.commit()
        quote_id = str(quote.id)
    finally:
        session.close()

    response = client.post(
        f"/v1/quotes/{quote_id}/accept",
        headers=auth_headers(token, f"expired-{uuid4()}"),
    )
    assert response.status_code == 422
    assert response.json()["code"] == "QUOTE_EXPIRED"


def test_kill_switch_blocks_new_quotes(client: TestClient) -> None:
    ops = login(client, "ops@desk.local", "ops-local")
    client_token = login(client, "client@desk.local", "client-local")
    engage = client.post(
        "/v1/admin/kill-switch",
        json={"engaged": True},
        headers=auth_headers(ops, f"ks-on-{uuid4()}"),
    )
    assert engage.status_code == 200
    assert engage.json()["engaged"] is True
    try:
        response = client.post(
            "/v1/rfqs",
            json={"side": "buy", "base": "BTC", "quote": "USDC", "base_qty": "0.10"},
            headers=auth_headers(client_token, f"rfq-halted-{uuid4()}"),
        )
        assert response.status_code == 423
        assert response.json()["code"] == "KILL_SWITCH"
    finally:
        off = client.post(
            "/v1/admin/kill-switch",
            json={"engaged": False},
            headers=auth_headers(ops, f"ks-off-{uuid4()}"),
        )
        assert off.status_code == 200


def test_idempotent_accept(client: TestClient) -> None:
    token = login(client, "client@desk.local", "client-local")
    rfq = client.post(
        "/v1/rfqs",
        json={"side": "buy", "base": "BTC", "quote": "USDC", "base_qty": "0.25"},
        headers=auth_headers(token, f"rfq-idemp-{uuid4()}"),
    )
    assert rfq.status_code == 200, rfq.text
    quote_id = rfq.json()["quote_id"]
    key = f"accept-{uuid4()}"
    first = client.post(f"/v1/quotes/{quote_id}/accept", headers=auth_headers(token, key))
    assert first.status_code == 200, first.text
    second = client.post(f"/v1/quotes/{quote_id}/accept", headers=auth_headers(token, key))
    assert second.status_code == 200, second.text
    assert first.json()["trade_id"] == second.json()["trade_id"]
    assert "cloid" not in first.json()
    assert "oid" not in first.json()

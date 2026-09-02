from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.deposit.service import deposit_address
from app.hyperliquid.client import _parse_ioc, assert_executable_spot, resolve_spot_market, SpotMarket
from app.hyperliquid.cloid import hedge_cloid
from app.errors import ApiError
from app.workers import ACTIVE
from app.identity.service import hash_password
from app.ledger.service import credit_deposit, ensure_account
from app.models import User
from tests.conftest import auth_headers, login


def test_deposit_address_shared_for_eth_and_usdc(client: TestClient) -> None:
    token = login(client, "client@desk.local", "client-local")
    first = client.get("/v1/deposits/address", headers=auth_headers(token))
    second = client.get("/v1/deposits/address", headers=auth_headers(token))
    assert first.status_code == 200, first.text
    assert first.json()["address"] == second.json()["address"]
    assert first.json()["address"].startswith("0x")
    assert first.json()["assets"] == ["ETH", "USDC"]
    session = SessionLocal()
    try:
        user = session.scalar(select(User).where(User.email == "client@desk.local"))
        assert user is not None
        assert deposit_address(user.id, "ETH") == deposit_address(user.id, "USDC")
        assert deposit_address(user.id) == first.json()["address"]
    finally:
        session.close()


def test_simulate_deposit_requires_sim_chain_tx(client: TestClient) -> None:
    token = login(client, "client@desk.local", "client-local")
    quoted = client.post(
        "/v1/quotes",
        json={"pay_asset": "USDC", "receive_asset": "ETH", "pay_qty": "25.00"},
        headers=auth_headers(token, f"quote-sim-{uuid4()}"),
    )
    assert quoted.status_code == 200, quoted.text
    accepted = client.post(
        f"/v1/quotes/{quoted.json()['quote_id']}/accept",
        headers=auth_headers(token, f"accept-sim-{uuid4()}"),
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "awaiting_deposit"
    trade_id = accepted.json()["trade_id"]
    bad = client.post(
        "/v1/deposits/simulate",
        json={"trade_id": trade_id, "chain_tx_id": "0xreal"},
        headers=auth_headers(token, f"sim-bad-{uuid4()}"),
    )
    assert bad.status_code == 422
    chain_tx = f"sim-{uuid4()}"
    ok = client.post(
        "/v1/deposits/simulate",
        json={"trade_id": trade_id, "chain_tx_id": chain_tx},
        headers=auth_headers(token, f"sim-ok-{uuid4()}"),
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["deposit"]["chain_tx_id"] == chain_tx
    assert ok.json()["deposit"]["status"] == "credited"
    assert ok.json()["trade"]["status"] == "reserved"
    assert "cloid" not in ok.json()["trade"]


def test_funded_accept_skips_deposit(client: TestClient) -> None:
    email = f"funded-{uuid4()}@desk.local"
    session = SessionLocal()
    try:
        user = User(email=email, password_hash=hash_password("funded-local"), role="client")
        session.add(user)
        session.flush()
        for asset in ("ETH", "USDC"):
            ensure_account(session, "client", user.id, asset, "available", Decimal("0"))
            ensure_account(session, "client", user.id, asset, "reserved", Decimal("0"))
        credit_deposit(
            session,
            user_id=user.id,
            asset="USDC",
            amount=Decimal("100.00"),
            trade_id=uuid4(),
        )
        session.commit()
    finally:
        session.close()
    token = login(client, email, "funded-local")

    quoted = client.post(
        "/v1/quotes",
        json={"pay_asset": "USDC", "receive_asset": "ETH", "pay_qty": "25.00"},
        headers=auth_headers(token, f"quote-funded-{uuid4()}"),
    )
    assert quoted.status_code == 200, quoted.text
    accepted = client.post(
        f"/v1/quotes/{quoted.json()['quote_id']}/accept",
        headers=auth_headers(token, f"accept-funded-{uuid4()}"),
    )
    assert accepted.status_code == 200, accepted.text
    body = accepted.json()
    assert body["status"] == "reserved"
    assert "deposit" not in body
    assert "cloid" not in body
    assert "oid" not in body


def test_tokens_mark_btc_unavailable(client: TestClient) -> None:
    response = client.get("/v1/tokens")
    assert response.status_code == 200
    btc = next(row for row in response.json()["tokens"] if row["asset"] == "BTC")
    assert btc["available"] is False
    assert btc["reason"] == "unavailable on testnet"


def test_spot_meta_resolves_ueth_index() -> None:
    meta = {
        "tokens": [
            {"name": "USDC", "index": 0},
            {"name": "UETH", "index": 4},
            {"name": "JUNK", "index": 50},
        ],
        "universe": [
            {"name": "@50", "index": 50, "tokens": [50, 0]},
            {"name": "@7", "index": 7, "tokens": [4, 0]},
        ],
    }
    market = resolve_spot_market(meta)
    assert market.coin == "@7"
    assert market.asset == 10007
    assert market.universe_index == 7
    assert market.base_token == "UETH"


def test_never_order_junk_btc_at_50() -> None:
    try:
        assert_executable_spot(SpotMarket(coin="@50", asset=10050, universe_index=50, base_token="UBTC"))
    except ApiError as exc:
        assert exc.code == "HL_PAIR"
    else:
        raise AssertionError("junk BTC @50 must be refused")


def test_cloid_formula() -> None:
    from uuid import UUID

    trade_id = UUID("123e4567-e89b-12d3-a456-426614174000")
    import hashlib

    expected = "0x" + hashlib.sha256(b"otc-hedge-v1|" + str(trade_id).encode("utf-8")).digest()[:16].hex()
    assert hedge_cloid(trade_id) == expected
    assert hedge_cloid(trade_id).startswith("0x")
    assert len(hedge_cloid(trade_id)) == 34


def test_http_200_parses_statuses_zero() -> None:
    fill = _parse_ioc(
        {
            "status": "ok",
            "response": {"data": {"statuses": [{"filled": {"totalSz": "0.1", "avgPx": "3501.25"}}]}},
        }
    )
    assert fill.filled_qty == Decimal("0.1")
    assert fill.avg_price == Decimal("3501.25")
    assert fill.status == "filled"


def test_worker_does_not_execute_unreserved() -> None:
    assert "awaiting_deposit" not in ACTIVE
    assert "accepted" not in ACTIVE


def test_ioc_resting_is_failure() -> None:
    try:
        _parse_ioc(
            {
                "status": "ok",
                "response": {"data": {"statuses": [{"resting": {"oid": 1}}]}},
            }
        )
    except Exception as exc:
        assert getattr(exc, "code", "") == "HL_UNFILLED"
    else:
        raise AssertionError("resting IOC must fail")

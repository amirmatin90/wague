from __future__ import annotations

from decimal import Decimal
from uuid import uuid4
from unittest.mock import MagicMock, patch

import pytest
from eth_account import Account

from app.errors import ApiError
from app.hyperliquid.client import place_spot_ioc


def _ok_fill() -> dict:
    return {
        "status": "ok",
        "response": {"data": {"statuses": [{"filled": {"totalSz": "0.1", "avgPx": "3517.50"}}]}},
    }


def test_place_spot_ioc_passes_account_address(monkeypatch: pytest.MonkeyPatch) -> None:
    agent = Account.create()
    master = Account.create()
    monkeypatch.setenv("HL_AGENT_KEY_TESTNET", agent.key.hex())
    monkeypatch.setenv("HL_MASTER_ADDRESS", master.address)

    fake_exchange = MagicMock()
    fake_exchange.order.return_value = _ok_fill()

    with patch("hyperliquid.exchange.Exchange", return_value=fake_exchange) as exchange_cls:
        fill = place_spot_ioc(trade_id=uuid4(), is_buy=True, qty=Decimal("0.1"))

    assert fill.filled_qty == Decimal("0.1")
    assert fill.avg_price == Decimal("3517.50")
    exchange_cls.assert_called_once()
    _wallet, _url = exchange_cls.call_args.args[:2]
    assert exchange_cls.call_args.kwargs["account_address"] == master.address
    assert exchange_cls.call_args.kwargs["timeout"] == 8.0
    assert _wallet.address == agent.address


def test_place_spot_ioc_requires_master_address(monkeypatch: pytest.MonkeyPatch) -> None:
    agent = Account.create()
    monkeypatch.setenv("HL_AGENT_KEY_TESTNET", agent.key.hex())
    monkeypatch.delenv("HL_MASTER_ADDRESS", raising=False)

    with patch("hyperliquid.exchange.Exchange") as exchange_cls:
        with pytest.raises(ApiError) as exc:
            place_spot_ioc(trade_id=uuid4(), is_buy=True, qty=Decimal("0.1"))

    assert exc.value.status_code == 503
    assert exc.value.code == "HL_MASTER_MISSING"
    assert exc.value.message == "set HL_MASTER_ADDRESS to the testnet master that approved the agent"
    exchange_cls.assert_not_called()


def test_place_spot_ioc_missing_key_does_not_require_master(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HL_AGENT_KEY_TESTNET", raising=False)
    monkeypatch.delenv("HL_MASTER_ADDRESS", raising=False)

    with pytest.raises(ApiError) as exc:
        place_spot_ioc(trade_id=uuid4(), is_buy=True, qty=Decimal("0.1"))

    assert exc.value.status_code == 503
    assert exc.value.code == "HL_KEY_MISSING"
    assert "HL_AGENT_KEY_TESTNET" in exc.value.message

from __future__ import annotations

import pytest
from eth_account import Account

from app.config import assert_testnet


def test_refuse_agent_equals_master(monkeypatch: pytest.MonkeyPatch) -> None:
    wallet = Account.create()
    monkeypatch.setenv("HL_NETWORK", "testnet")
    monkeypatch.setenv("HL_API_URL", "https://api.hyperliquid-testnet.xyz")
    monkeypatch.setenv("HL_AGENT_KEY_TESTNET", wallet.key.hex())
    monkeypatch.setenv("HL_MASTER_ADDRESS", wallet.address)
    with pytest.raises(SystemExit, match="HL_MASTER_ADDRESS"):
        assert_testnet()


def test_refuse_mainnet_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HL_NETWORK", "mainnet")
    monkeypatch.setenv("HL_API_URL", "https://api.hyperliquid-testnet.xyz")
    monkeypatch.delenv("HL_MASTER_KEY", raising=False)
    monkeypatch.delenv("HL_WITHDRAW_KEY", raising=False)
    monkeypatch.delenv("HL_AGENT_KEY_MAINNET", raising=False)
    with pytest.raises(SystemExit, match="mainnet"):
        assert_testnet()


def test_refuse_master_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HL_NETWORK", "testnet")
    monkeypatch.setenv("HL_API_URL", "https://api.hyperliquid-testnet.xyz")
    monkeypatch.setenv("HL_MASTER_KEY", "0xabc")
    with pytest.raises(SystemExit, match="HL_MASTER_KEY"):
        assert_testnet()

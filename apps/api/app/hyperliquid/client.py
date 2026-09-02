from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from typing import Any

from app.config import TESTNET_API, TESTNET_WS, agent_key, get_settings
from app.errors import ApiError
from app.hyperliquid.cloid import hedge_cloid

SPOT_PAIR = "ETH/USDC"
HL_BASE = "UETH"
HL_QUOTE = "USDC"

_test_book: dict | None = None


@dataclass(frozen=True)
class Book:
    coin: str
    bids: list[tuple[Decimal, Decimal]]
    asks: list[tuple[Decimal, Decimal]]
    mid: Decimal


@dataclass(frozen=True)
class IocFill:
    filled_qty: Decimal
    avg_price: Decimal
    status: str


def set_test_book(book: dict | None) -> None:
    global _test_book
    _test_book = book


def _require_testnet_url(url: str) -> str:
    if "hyperliquid-testnet.xyz" not in url:
        raise ApiError(500, "HL_NETWORK", "Hyperliquid host must be testnet")
    return url


def api_url() -> str:
    return _require_testnet_url(get_settings().hl_api_url or TESTNET_API)


def ws_url() -> str:
    url = get_settings().hl_ws_url or TESTNET_WS
    if "hyperliquid-testnet.xyz" not in url:
        raise ApiError(500, "HL_NETWORK", "Hyperliquid websocket must be testnet")
    return url


@lru_cache
def _info():
    from hyperliquid.info import Info

    return Info(api_url(), skip_ws=True, timeout=8.0)


def _hl_call(fn, *args):
    try:
        return fn(*args)
    except ApiError:
        raise
    except Exception as exc:
        raise ApiError(503, "BOOK_UNAVAILABLE", "Live Hyperliquid testnet book is unavailable") from exc


def spot_coin() -> str:
    if _test_book is not None:
        return str(_test_book.get("coin") or "UETH/USDC")
    info = _hl_call(_info)
    meta = _hl_call(info.spot_meta)
    tokens = {token["name"]: token["index"] for token in meta["tokens"]}
    if HL_BASE not in tokens or HL_QUOTE not in tokens:
        raise ApiError(503, "BOOK_UNAVAILABLE", "Testnet spot meta does not list UETH/USDC")
    wanted = {tokens[HL_BASE], tokens[HL_QUOTE]}
    for row in meta["universe"]:
        if set(row["tokens"]) == wanted:
            return row["name"]
    raise ApiError(503, "BOOK_UNAVAILABLE", "UETH/USDC spot market not found on testnet")


def l2_book(coin: str | None = None) -> Book:
    if _test_book is not None:
        return Book(
            coin=str(_test_book.get("coin") or "UETH/USDC"),
            bids=list(_test_book["bids"]),
            asks=list(_test_book["asks"]),
            mid=Decimal(_test_book["mid"]),
        )
    name = coin or spot_coin()
    try:
        raw = _info().l2_snapshot(name)
    except ApiError:
        raise
    except Exception as exc:
        raise ApiError(503, "BOOK_UNAVAILABLE", "Live Hyperliquid testnet book is unavailable") from exc
    levels = raw.get("levels") or []
    if len(levels) < 2:
        raise ApiError(503, "BOOK_UNAVAILABLE", "Live Hyperliquid testnet book is empty")
    bids = [(Decimal(level["px"]), Decimal(level["sz"])) for level in levels[0]]
    asks = [(Decimal(level["px"]), Decimal(level["sz"])) for level in levels[1]]
    if not bids or not asks:
        raise ApiError(503, "BOOK_UNAVAILABLE", "Live Hyperliquid testnet book has no depth")
    mid = (bids[0][0] + asks[0][0]) / Decimal("2")
    return Book(coin=name, bids=bids, asks=asks, mid=mid)


def place_spot_ioc(
    *,
    trade_id,
    is_buy: bool,
    qty: Decimal,
    limit_px: Decimal,
) -> IocFill:
    key = agent_key()
    if not key:
        raise ApiError(
            503,
            "HL_KEY_MISSING",
            "set HL_AGENT_KEY_TESTNET to execute on Hyperliquid testnet",
        )
    from eth_account import Account
    from hyperliquid.exchange import Exchange
    from hyperliquid.utils.types import Cloid

    wallet = Account.from_key(key)
    exchange = Exchange(wallet, api_url())
    cloid = Cloid.from_str(hedge_cloid(trade_id))
    try:
        raw: dict[str, Any] = exchange.order(
            spot_coin(),
            is_buy,
            float(qty),
            float(limit_px),
            {"limit": {"tif": "Ioc"}},
            cloid=cloid,
        )
    except Exception as exc:
        raise ApiError(502, "HL_ORDER_FAILED", "Hyperliquid testnet order failed") from exc
    return _parse_ioc(raw)


def _parse_ioc(raw: dict[str, Any]) -> IocFill:
    if raw.get("status") != "ok":
        raise ApiError(502, "HL_ORDER_FAILED", str(raw.get("response") or "Hyperliquid rejected the order"))
    response = raw.get("response") or {}
    data = response.get("data") or {}
    statuses = data.get("statuses") or []
    if not statuses:
        raise ApiError(502, "HL_ORDER_FAILED", "Hyperliquid returned no fill status")
    first = statuses[0]
    if "filled" in first:
        filled = first["filled"]
        return IocFill(
            filled_qty=Decimal(str(filled["totalSz"])),
            avg_price=Decimal(str(filled["avgPx"])),
            status="filled",
        )
    if "error" in first:
        raise ApiError(502, "HL_ORDER_FAILED", str(first["error"]))
    raise ApiError(502, "HL_UNFILLED", "IOC did not fill; no stub fill is applied")

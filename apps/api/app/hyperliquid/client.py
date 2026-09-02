from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from typing import Any

from app.config import TESTNET_API, TESTNET_WS, agent_key, get_settings
from app.errors import ApiError
from app.hyperliquid.cloid import hedge_cloid
from app.money import q_usdc

SPOT_PAIR = "ETH/USDC"
HL_BASE = "UETH"
HL_QUOTE = "USDC"
AGGRESSIVE_BPS = Decimal("50")

_test_book: dict | None = None
_spot: "SpotMarket | None" = None


@dataclass(frozen=True)
class SpotMarket:
    coin: str
    asset: int
    universe_index: int
    base_token: str = HL_BASE
    quote_token: str = HL_QUOTE


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
    global _test_book, _spot
    _test_book = book
    if book is None:
        _spot = None
        return
    _spot = SpotMarket(coin=str(book.get("coin") or "@0"), asset=int(book.get("asset") or 10000), universe_index=0)


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


def resolve_spot_market(meta: dict | None = None) -> SpotMarket:
    global _spot
    if meta is None and _test_book is not None:
        market = SpotMarket(
            coin=str(_test_book.get("coin") or "@0"),
            asset=int(_test_book.get("asset") or 10000),
            universe_index=0,
        )
        _spot = market
        return market
    if meta is None:
        info = _hl_call(_info)
        meta = _hl_call(info.spot_meta)
    tokens = {token["name"]: token["index"] for token in meta["tokens"]}
    if HL_BASE not in tokens or HL_QUOTE not in tokens:
        raise ApiError(503, "BOOK_UNAVAILABLE", "Testnet spot meta does not list UETH/USDC")
    if "UBTC" in tokens:
        # Testnet listing UBTC would still not authorize a BTC pair on this desk.
        pass
    wanted = {tokens[HL_BASE], tokens[HL_QUOTE]}
    for index, row in enumerate(meta["universe"]):
        if set(row["tokens"]) != wanted:
            continue
        name = str(row.get("name") or "")
        if name.startswith("@") and name[1:].isdigit():
            universe_index = int(name[1:])
        else:
            universe_index = index
        market = SpotMarket(
            coin=f"@{universe_index}",
            asset=10000 + universe_index,
            universe_index=universe_index,
        )
        _spot = market
        return market
    raise ApiError(503, "BOOK_UNAVAILABLE", "UETH/USDC spot market not found on testnet")


def warm_spot_market() -> SpotMarket | None:
    if _test_book is not None:
        return resolve_spot_market()
    try:
        return resolve_spot_market()
    except ApiError:
        return None


def spot_market() -> SpotMarket:
    if _spot is not None:
        return _spot
    return resolve_spot_market()


def spot_coin() -> str:
    return spot_market().coin


def l2_book(coin: str | None = None) -> Book:
    if _test_book is not None:
        mid = Decimal(_test_book["mid"])
        return Book(
            coin=str(_test_book.get("coin") or "@0"),
            bids=list(_test_book["bids"]),
            asks=list(_test_book["asks"]),
            mid=mid,
        )
    market = spot_market()
    name = coin or market.coin
    info = _info()
    try:
        raw = info.l2_snapshot(name)
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
    try:
        mids = info.all_mids()
        if name in mids:
            mid = Decimal(str(mids[name]))
    except Exception:
        pass
    return Book(coin=name, bids=bids, asks=asks, mid=mid)


def aggressive_limit(mid: Decimal, is_buy: bool) -> Decimal:
    adj = AGGRESSIVE_BPS / Decimal("10000")
    raw = mid * (Decimal("1") + adj) if is_buy else mid * (Decimal("1") - adj)
    return q_usdc(raw)


def place_spot_ioc(
    *,
    trade_id,
    is_buy: bool,
    qty: Decimal,
    limit_px: Decimal | None = None,
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

    market = spot_market()
    if not market.coin.startswith("@") or market.asset < 10000:
        raise ApiError(500, "HL_PAIR", "Refusing to order a non-spot UETH/USDC market")
    book = l2_book(market.coin)
    px = limit_px if limit_px is not None else aggressive_limit(book.mid, is_buy)
    wallet = Account.from_key(key)
    exchange = Exchange(wallet, api_url())
    cloid = Cloid.from_str(hedge_cloid(trade_id))
    try:
        raw: dict[str, Any] = exchange.order(
            market.coin,
            is_buy,
            float(qty),
            float(px),
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
        qty = Decimal(str(filled["totalSz"]))
        if qty <= 0:
            raise ApiError(502, "HL_UNFILLED", "IOC did not fill; no stub fill is applied")
        return IocFill(
            filled_qty=qty,
            avg_price=Decimal(str(filled["avgPx"])),
            status="filled",
        )
    if "error" in first:
        raise ApiError(502, "HL_ORDER_FAILED", str(first["error"]))
    if "resting" in first:
        raise ApiError(502, "HL_UNFILLED", "IOC rested; unfilled IOC is failure and is never left resting")
    raise ApiError(502, "HL_UNFILLED", "IOC did not fill; no stub fill is applied")

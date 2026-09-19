from __future__ import annotations

from decimal import Decimal

from app.config import get_settings
from app.errors import ApiError
from app.hyperliquid.client import l2_book
from app.money import q_base, q_bps, q_usdc

LIVE_PAIR = ("ETH", "USDC")
MIN_PAY = {
    "ETH": Decimal("0.00100000"),
    "USDC": Decimal("10.00"),
}
MAX_PAY = {
    "ETH": Decimal("50.00000000"),
    "USDC": Decimal("250000.00"),
}


def assert_live_pair(pay_asset: str, receive_asset: str) -> None:
    if pay_asset == receive_asset:
        raise ApiError(422, "INVALID_PAIR", "Pay and receive assets must differ")
    if "BTC" in {pay_asset, receive_asset}:
        raise ApiError(422, "PAIR_UNAVAILABLE", "BTC is unavailable; testnet has no UBTC")
    if {pay_asset, receive_asset} != {"ETH", "USDC"}:
        raise ApiError(422, "INVALID_PAIR", "Live execute is ETH/USDC only")


def validate_pay(pay_asset: str, pay_qty: Decimal) -> Decimal:
    qty = q_usdc(pay_qty) if pay_asset == "USDC" else q_base(pay_qty)
    if qty <= 0:
        raise ApiError(422, "INVALID_QTY", "Amount must be greater than zero")
    minimum = MIN_PAY[pay_asset]
    maximum = MAX_PAY[pay_asset]
    if qty < minimum:
        raise ApiError(422, "BELOW_MINIMUM", f"Below minimum ({minimum} {pay_asset})")
    if qty > maximum:
        raise ApiError(422, "INVALID_QTY", f"Amount for {pay_asset} must be at most {maximum}")
    return qty


def _walk(levels: list[tuple[Decimal, Decimal]], pay_qty: Decimal, *, pay_is_quote: bool) -> tuple[Decimal, Decimal]:
    remaining = pay_qty
    other = Decimal("0")
    notional = Decimal("0")
    filled_pay = Decimal("0")
    for price, size in levels:
        if pay_is_quote:
            level_quote = price * size
            take_quote = min(remaining, level_quote)
            take_base = take_quote / price
        else:
            take_base = min(remaining, size)
            take_quote = take_base * price
        if take_base <= 0:
            continue
        other += take_base if pay_is_quote else take_quote
        filled_pay += take_quote if pay_is_quote else take_base
        notional += take_quote
        remaining -= take_quote if pay_is_quote else take_base
        if remaining <= Decimal("0.00000001"):
            remaining = Decimal("0")
            break
    if remaining > 0:
        raise ApiError(422, "INSUFFICIENT_LIQUIDITY", "Not enough testnet book depth for this size")
    avg = notional / (other if pay_is_quote else filled_pay)
    return other, avg


def price_swap(pay_asset: str, receive_asset: str, pay_qty: Decimal) -> dict:
    assert_live_pair(pay_asset, receive_asset)
    qty = validate_pay(pay_asset, pay_qty)
    settings = get_settings()
    book = l2_book()
    spread = q_bps(Decimal(settings.spread_bps))
    fee_bps = q_bps(Decimal(settings.fee_bps))
    adj = spread / Decimal("10000")
    if pay_asset == "USDC" and receive_asset == "ETH":
        raw_out, avg = _walk(book.asks, qty, pay_is_quote=True)
        price = q_usdc(avg * (Decimal("1") + adj))
        receive = q_base(qty / price)
        fee = q_usdc(qty * fee_bps / Decimal("10000"))
        side = "buy"
        base_qty = receive
        quote_qty = qty
    else:
        raw_out, avg = _walk(book.bids, qty, pay_is_quote=False)
        price = q_usdc(avg * (Decimal("1") - adj))
        gross = q_usdc(qty * price)
        fee = q_usdc(gross * fee_bps / Decimal("10000"))
        receive = q_usdc(gross - fee)
        side = "sell"
        base_qty = qty
        quote_qty = receive + fee
        _ = raw_out
    pay_usd = qty if pay_asset == "USDC" else q_usdc(qty * book.mid)
    receive_usd = receive if receive_asset == "USDC" else q_usdc(receive * book.mid)
    return {
        "side": side,
        "base": "ETH",
        "quote": "USDC",
        "base_qty": base_qty,
        "quote_qty": quote_qty,
        "price": price,
        "fee_amount": fee,
        "fee_bps": fee_bps,
        "pay_asset": pay_asset,
        "receive_asset": receive_asset,
        "pay_qty": qty,
        "receive_qty": receive,
        "pay_usd": pay_usd,
        "receive_usd": receive_usd,
        "mid": q_usdc(book.mid),
    }

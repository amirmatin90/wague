from __future__ import annotations

from decimal import Decimal

from app.config import get_settings
from app.errors import ApiError
from app.money import q_bps, q_usdc

PAIRS = {("BTC", "USDC"), ("ETH", "USDC")}
STUB_MIDS = {
    "BTC": Decimal("97500"),
    "ETH": Decimal("3520"),
}


def mid_for(base: str, quote: str) -> Decimal:
    if (base, quote) not in PAIRS:
        raise ApiError(422, "INVALID_PAIR", "Only BTC/USDC and ETH/USDC are quoted")
    return STUB_MIDS[base]


def price_rfq(side: str, base: str, quote: str, base_qty: Decimal) -> dict[str, Decimal | int]:
    settings = get_settings()
    mid = mid_for(base, quote)
    spread_bps = q_bps(Decimal(settings.spread_bps))
    fee_bps = q_bps(Decimal(settings.fee_bps))
    adj = spread_bps / Decimal("10000")
    if side == "buy":
        price = q_usdc(mid * (Decimal("1") + adj))
    elif side == "sell":
        price = q_usdc(mid * (Decimal("1") - adj))
    else:
        raise ApiError(422, "INVALID_SIDE", "side must be buy or sell")
    quote_qty = q_usdc(base_qty * price)
    fee_amount = q_usdc(quote_qty * fee_bps / Decimal("10000"))
    return {
        "price": price,
        "quote_qty": quote_qty,
        "fee_amount": fee_amount,
        "fee_bps": fee_bps,
        "mid": mid,
        "spread_bps": spread_bps,
    }

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.errors import ApiError
from app.ledger.service import DESK_PARTY_ID, get_account
from app.money import q_base
from app.pricing.engine import PAIRS

MIN_QTY = {"BTC": Decimal("0.00010000"), "ETH": Decimal("0.00100000")}
MAX_QTY = {"BTC": Decimal("5.00000000"), "ETH": Decimal("50.00000000")}


def validate_rfq(side: str, base: str, quote: str, base_qty: Decimal) -> Decimal:
    if side not in {"buy", "sell"}:
        raise ApiError(422, "INVALID_SIDE", "side must be buy or sell")
    if (base, quote) not in PAIRS:
        raise ApiError(422, "INVALID_PAIR", "Only BTC/USDC and ETH/USDC are quoted")
    qty = q_base(base_qty)
    if qty <= 0:
        raise ApiError(422, "INVALID_QTY", "base_qty must be greater than zero")
    if qty < MIN_QTY[base] or qty > MAX_QTY[base]:
        raise ApiError(
            422,
            "INVALID_QTY",
            f"base_qty for {base} must be between {MIN_QTY[base]} and {MAX_QTY[base]}",
        )
    return qty


def check_balances(
    session: Session,
    *,
    user_id: UUID,
    side: str,
    base: str,
    quote: str,
    base_qty: Decimal,
    quote_qty: Decimal,
    fee_amount: Decimal,
) -> None:
    if side == "buy":
        need = quote_qty + fee_amount
        client_usdc = get_account(session, "client", user_id, quote, "available", for_update=False)
        if client_usdc is None or client_usdc.balance < need:
            raise ApiError(422, "INSUFFICIENT_BALANCE", f"Insufficient {quote} to lift this quote")
        desk_base = get_account(session, "desk", DESK_PARTY_ID, base, "available", for_update=False)
        if desk_base is None or desk_base.balance < base_qty:
            raise ApiError(422, "INSUFFICIENT_INVENTORY", f"Desk inventory of {base} is insufficient")
    else:
        client_base = get_account(session, "client", user_id, base, "available", for_update=False)
        if client_base is None or client_base.balance < base_qty:
            raise ApiError(422, "INSUFFICIENT_BALANCE", f"Insufficient {base} to lift this quote")
        desk_need = quote_qty - fee_amount
        desk_usdc = get_account(session, "desk", DESK_PARTY_ID, quote, "available", for_update=False)
        if desk_usdc is None or desk_usdc.balance < desk_need:
            raise ApiError(422, "INSUFFICIENT_INVENTORY", f"Desk inventory of {quote} is insufficient")

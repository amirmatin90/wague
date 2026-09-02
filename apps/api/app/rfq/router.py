from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.service import write_audit
from app.config import get_settings
from app.deps import CurrentUser, DbSession, Idempotency, require_idempotency, require_roles
from app.errors import ApiError
from app.models import Quote, Rfq, User
from app.money import parse_decimal
from app.pricing.engine import price_swap
from app.schemas import quote_public
from app.trade.service import assert_desk_open

router = APIRouter(tags=["swap"])


class SwapQuoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pay_asset: Literal["ETH", "USDC", "BTC"]
    receive_asset: Literal["ETH", "USDC", "BTC"]
    pay_qty: Decimal

    @field_validator("pay_qty", mode="before")
    @classmethod
    def qty_as_decimal_string(cls, value: object) -> Decimal:
        return parse_decimal(value, field="pay_qty")


def _create_quote(session: Session, user: User, payload: SwapQuoteRequest) -> dict:
    assert_desk_open(session)
    priced = price_swap(payload.pay_asset, payload.receive_asset, payload.pay_qty)
    now = session.scalar(select(func.now()))
    ttl_ms = get_settings().quote_ttl_ms
    rfq = Rfq(
        user_id=user.id,
        side=priced["side"],
        base=priced["base"],
        quote_asset=priced["quote"],
        base_qty=priced["base_qty"],
        status="quoted",
    )
    session.add(rfq)
    session.flush()
    quote = Quote(
        rfq_id=rfq.id,
        user_id=user.id,
        side=priced["side"],
        base=priced["base"],
        quote_asset=priced["quote"],
        base_qty=priced["base_qty"],
        quote_qty=priced["quote_qty"],
        price=priced["price"],
        fee_amount=priced["fee_amount"],
        fee_bps=priced["fee_bps"],
        ttl_ms=ttl_ms,
        expires_at=now + timedelta(milliseconds=ttl_ms),
        status="quoted",
    )
    session.add(quote)
    session.flush()
    write_audit(
        session,
        user.id,
        "quote.create",
        "quote",
        str(quote.id),
        {"pay_asset": payload.pay_asset, "receive_asset": payload.receive_asset},
    )
    return quote_public(quote, priced)


@router.post("/v1/quotes")
def create_quote(
    payload: SwapQuoteRequest,
    session: DbSession,
    user: Annotated[User, Depends(require_roles("client"))],
    idem: Annotated[Idempotency, Depends(require_idempotency)],
):
    if idem.cached is not None:
        return JSONResponse(idem.cached, status_code=idem.cached_status or 200)
    body = _create_quote(session, user, payload)
    idem.store(200, body)
    return body


@router.get("/v1/quotes/{quote_id}")
def read_quote(quote_id: UUID, session: DbSession, user: CurrentUser) -> dict:
    quote = session.get(Quote, quote_id)
    if quote is None:
        raise ApiError(404, "QUOTE_NOT_FOUND", "Quote not found")
    if user.role == "client" and quote.user_id != user.id:
        raise ApiError(404, "QUOTE_NOT_FOUND", "Quote not found")
    now = session.scalar(select(func.now()))
    if quote.status == "quoted" and quote.expires_at <= now:
        quote.status = "expired"
    return quote_public(quote)


@router.get("/v1/rfqs/{rfq_id}")
def read_rfq(rfq_id: UUID, session: DbSession, user: CurrentUser) -> dict:
    rfq = session.get(Rfq, rfq_id)
    if rfq is None:
        raise ApiError(404, "RFQ_NOT_FOUND", "RFQ not found")
    if user.role == "client" and rfq.user_id != user.id:
        raise ApiError(404, "RFQ_NOT_FOUND", "RFQ not found")
    quote = session.scalar(select(Quote).where(Quote.rfq_id == rfq.id))
    if quote is None:
        raise ApiError(404, "QUOTE_NOT_FOUND", "No quote for this request")
    return quote_public(quote)


@router.get("/v1/tokens")
def list_tokens() -> dict:
    return {
        "tokens": [
            {"asset": "ETH", "name": "Ethereum", "available": True, "hl": "UETH"},
            {"asset": "USDC", "name": "USD Coin", "available": True, "hl": "USDC"},
            {
                "asset": "BTC",
                "name": "Bitcoin",
                "available": False,
                "reason": "Unavailable on Hyperliquid testnet (no UBTC)",
            },
        ]
    }

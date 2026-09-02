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
from app.deps import DbSession, Idempotency, require_idempotency, require_roles
from app.errors import ApiError
from app.models import Quote, Rfq, User
from app.money import parse_decimal
from app.pricing.engine import price_rfq
from app.realtime.hub import hub
from app.risk.engine import check_balances, validate_rfq
from app.schemas import quote_public
from app.trade.service import assert_desk_open

router = APIRouter(tags=["rfq"])


class RfqRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    side: Literal["buy", "sell"]
    base: Literal["BTC", "ETH"]
    quote: Literal["USDC"]
    base_qty: Decimal

    @field_validator("base_qty", mode="before")
    @classmethod
    def qty_as_decimal_string(cls, value: object) -> Decimal:
        return parse_decimal(value, field="base_qty")


def _create_rfq(session: Session, user: User, payload: RfqRequest) -> dict:
    assert_desk_open(session)
    qty = validate_rfq(payload.side, payload.base, payload.quote, payload.base_qty)
    priced = price_rfq(payload.side, payload.base, payload.quote, qty)
    check_balances(
        session,
        user_id=user.id,
        side=payload.side,
        base=payload.base,
        quote=payload.quote,
        base_qty=qty,
        quote_qty=priced["quote_qty"],
        fee_amount=priced["fee_amount"],
    )
    now = session.scalar(select(func.now()))
    ttl_ms = get_settings().quote_ttl_ms
    rfq = Rfq(
        user_id=user.id,
        side=payload.side,
        base=payload.base,
        quote_asset=payload.quote,
        base_qty=qty,
        status="quoted",
    )
    session.add(rfq)
    session.flush()
    quote = Quote(
        rfq_id=rfq.id,
        user_id=user.id,
        side=payload.side,
        base=payload.base,
        quote_asset=payload.quote,
        base_qty=qty,
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
        "rfq.create",
        "quote",
        str(quote.id),
        {"side": payload.side, "base": payload.base, "quote": payload.quote},
    )
    body = quote_public(quote)
    hub.publish({"type": "quote.created", **body}, user_id=user.id, admin=True)
    return body


@router.post("/v1/rfqs")
def create_rfq(
    payload: RfqRequest,
    session: DbSession,
    user: Annotated[User, Depends(require_roles("client"))],
    idem: Annotated[Idempotency, Depends(require_idempotency)],
):
    if idem.cached is not None:
        return JSONResponse(idem.cached, status_code=idem.cached_status or 200)
    body = _create_rfq(session, user, payload)
    idem.store(200, body)
    return body


@router.get("/v1/rfqs/{rfq_id}")
def read_rfq(
    rfq_id: UUID,
    session: DbSession,
    user: Annotated[User, Depends(require_roles("client", "ops", "cto"))],
) -> dict:
    rfq = session.get(Rfq, rfq_id)
    if rfq is None:
        raise ApiError(404, "RFQ_NOT_FOUND", "RFQ not found")
    if user.role == "client" and rfq.user_id != user.id:
        raise ApiError(404, "RFQ_NOT_FOUND", "RFQ not found")
    quote = session.scalar(select(Quote).where(Quote.rfq_id == rfq.id))
    if quote is None:
        raise ApiError(404, "QUOTE_NOT_FOUND", "No quote for this RFQ")
    now = session.scalar(select(func.now()))
    if quote.status == "quoted" and quote.expires_at <= now:
        quote.status = "expired"
    return quote_public(quote)

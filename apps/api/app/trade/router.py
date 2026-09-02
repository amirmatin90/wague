from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.deps import CurrentUser, DbSession, Idempotency, require_idempotency, require_roles
from app.ledger.service import client_balances
from app.trade.service import get_trade, honor_quote, list_client_trades

router = APIRouter(tags=["trade"])


@router.post("/v1/quotes/{quote_id}/accept")
def accept_quote(
    quote_id: UUID,
    session: DbSession,
    user: Annotated[object, Depends(require_roles("client"))],
    idem: Annotated[Idempotency, Depends(require_idempotency)],
):
    if idem.cached is not None:
        return JSONResponse(idem.cached, status_code=idem.cached_status or 200)
    body = honor_quote(session, user.id, quote_id)
    idem.store(200, body)
    return body


@router.get("/v1/trades/{trade_id}")
def read_trade(trade_id: UUID, session: DbSession, user: CurrentUser) -> dict:
    return get_trade(session, trade_id, user)


@router.get("/v1/trades")
def read_trades(session: DbSession, user: CurrentUser) -> dict:
    return {"trades": list_client_trades(session, user.id)}


@router.get("/v1/balances")
def read_balances(session: DbSession, user: CurrentUser) -> dict:
    return {"balances": client_balances(session, user.id)}

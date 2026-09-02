from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.deps import CurrentUser, DbSession, Idempotency, require_idempotency
from app.deposit.service import simulate_deposit
from app.errors import ApiError
from app.models import Deposit
from app.schemas import deposit_public

router = APIRouter(tags=["deposit"])


class SimulateDepositRequest(BaseModel):
    trade_id: UUID


@router.post("/v1/deposits/simulate")
def simulate(
    payload: SimulateDepositRequest,
    session: DbSession,
    user: CurrentUser,
    idem: Annotated[Idempotency, Depends(require_idempotency)],
):
    if idem.cached is not None:
        return JSONResponse(idem.cached, status_code=idem.cached_status or 200)
    body = simulate_deposit(session, user.id, payload.trade_id)
    idem.store(200, body)
    return body


@router.get("/v1/deposits/{deposit_id}")
def read_deposit(deposit_id: UUID, session: DbSession, user: CurrentUser) -> dict:
    row = session.get(Deposit, deposit_id)
    if row is None or (user.role == "client" and row.user_id != user.id):
        raise ApiError(404, "DEPOSIT_NOT_FOUND", "Deposit not found")
    return deposit_public(row)

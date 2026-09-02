from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from app.deps import ClientUser, CurrentUser, DbSession, Idempotency, require_idempotency
from app.deposit.service import deposit_address, simulate_deposit
from app.errors import ApiError
from app.models import Deposit
from app.schemas import deposit_public

router = APIRouter(tags=["deposit"])


class SimulateDepositRequest(BaseModel):
    trade_id: UUID
    chain_tx_id: str

    @field_validator("chain_tx_id")
    @classmethod
    def sim_chain_tx(cls, value: str) -> str:
        text = value.strip()
        if not (text.startswith("sim:") or text.startswith("sim-")):
            raise ValueError("chain_tx_id must be a synthetic sim: id")
        return text


@router.get("/v1/deposits/address")
def read_address(user: CurrentUser) -> dict:
    return {
        "address": deposit_address(user.id),
        "assets": ["ETH", "USDC"],
    }


@router.post("/v1/deposits/simulate")
def simulate(
    payload: SimulateDepositRequest,
    session: DbSession,
    user: ClientUser,
    idem: Annotated[Idempotency, Depends(require_idempotency)],
):
    if idem.cached is not None:
        return JSONResponse(idem.cached, status_code=idem.cached_status or 200)
    body = simulate_deposit(session, user.id, payload.trade_id, payload.chain_tx_id)
    idem.store(200, body)
    return body


@router.get("/v1/deposits/{deposit_id}")
def read_deposit(deposit_id: UUID, session: DbSession, user: CurrentUser) -> dict:
    row = session.get(Deposit, deposit_id)
    if row is None or (user.role == "client" and row.user_id != user.id):
        raise ApiError(404, "DEPOSIT_NOT_FOUND", "Deposit not found")
    return deposit_public(row)

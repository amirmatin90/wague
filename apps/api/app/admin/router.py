from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.audit.service import write_audit
from app.deps import AdminUser, DbSession, Idempotency, require_idempotency
from app.ledger.service import desk_positions
from app.models import KillSwitch, ReconResult, Trade
from app.realtime.hub import hub
from app.schemas import recon_public, trade_public
from app.trade.service import kill_switch_row, stages_for

router = APIRouter(prefix="/v1/admin", tags=["admin"])


class KillSwitchRequest(BaseModel):
    engaged: bool


@router.get("/trades")
def admin_trades(session: DbSession, _user: AdminUser) -> dict:
    trades = session.scalars(select(Trade).order_by(Trade.created_at.desc())).all()
    return {"trades": [trade_public(trade, stages_for(session, trade.id)) for trade in trades]}


@router.get("/positions")
def admin_positions(session: DbSession, _user: AdminUser) -> dict:
    row = kill_switch_row(session, for_update=False)
    return {
        "positions": desk_positions(session),
        "kill_switch": {
            "present": row is not None,
            "engaged": bool(row.engaged) if row is not None else True,
        },
    }


@router.get("/recon")
def admin_recon(session: DbSession, _user: AdminUser) -> dict:
    rows = session.scalars(select(ReconResult).order_by(ReconResult.created_at.desc())).all()
    return {"recon": [recon_public(row) for row in rows]}


@router.get("/kill-switch")
def get_kill_switch(session: DbSession, _user: AdminUser) -> dict:
    row = kill_switch_row(session, for_update=False)
    return {
        "present": row is not None,
        "engaged": bool(row.engaged) if row is not None else True,
    }


@router.post("/kill-switch")
def set_kill_switch(
    payload: KillSwitchRequest,
    session: DbSession,
    user: AdminUser,
    idem: Annotated[Idempotency, Depends(require_idempotency)],
):
    if idem.cached is not None:
        return JSONResponse(idem.cached, status_code=idem.cached_status or 200)
    row = kill_switch_row(session, for_update=True)
    if row is None:
        row = KillSwitch(id=1, engaged=payload.engaged, updated_by=user.id)
        session.add(row)
    else:
        row.engaged = payload.engaged
        row.updated_by = user.id
    write_audit(
        session,
        user.id,
        "kill_switch.set",
        "kill_switch",
        "1",
        {"engaged": payload.engaged},
    )
    body = {"engaged": payload.engaged}
    hub.publish({"type": "kill_switch", **body}, admin=True)
    idem.store(200, body)
    return body

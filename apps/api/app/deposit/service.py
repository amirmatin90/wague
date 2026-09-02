from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import write_audit
from app.errors import ApiError
from app.ledger.service import credit_deposit, pay_need, reserve_for_trade
from app.models import Deposit, Trade
from app.realtime.hub import hub
from app.schemas import deposit_public, trade_public


def deposit_address(user_id: UUID, asset: str) -> str:
    digest = hashlib.sha256(b"wague-deposit-v1|" + user_id.bytes + b"|" + asset.encode("ascii")).digest()
    return "0x" + digest[:20].hex()


def create_deposit(session: Session, trade: Trade) -> Deposit:
    existing = session.scalar(select(Deposit).where(Deposit.trade_id == trade.id))
    if existing is not None:
        return existing
    asset, amount = pay_need(trade.side, trade.base_qty, trade.quote_qty, trade.fee_amount)
    row = Deposit(
        user_id=trade.user_id,
        trade_id=trade.id,
        asset=asset,
        amount=amount,
        address=deposit_address(trade.user_id, asset),
        status="waiting",
    )
    session.add(row)
    session.flush()
    return row


def deposit_for_trade(session: Session, trade_id: UUID) -> Deposit | None:
    return session.scalar(select(Deposit).where(Deposit.trade_id == trade_id))


def simulate_deposit(session: Session, user_id: UUID, trade_id: UUID) -> dict:
    from app.trade.service import add_stage, stages_for

    trade = session.scalar(select(Trade).where(Trade.id == trade_id).with_for_update())
    if trade is None or trade.user_id != user_id:
        raise ApiError(404, "TRADE_NOT_FOUND", "Trade not found")
    deposit = session.scalar(select(Deposit).where(Deposit.trade_id == trade.id).with_for_update())
    if deposit is None:
        raise ApiError(404, "DEPOSIT_NOT_FOUND", "No deposit is waiting for this trade")
    if deposit.status == "credited":
        return {
            "deposit": deposit_public(deposit),
            "trade": trade_public(trade, stages_for(session, trade.id)),
        }
    if deposit.status not in {"waiting", "confirmed"}:
        raise ApiError(422, "DEPOSIT_CLOSED", "This deposit can no longer be credited")

    deposit.status = "confirmed"
    deposit.chain_tx_id = f"sim-{uuid4()}"
    deposit.confirmed_at = datetime.now(timezone.utc)
    session.flush()
    credit_deposit(
        session,
        user_id=trade.user_id,
        asset=deposit.asset,
        amount=deposit.amount,
        trade_id=trade.id,
    )
    reserve_for_trade(
        session,
        user_id=trade.user_id,
        side=trade.side,
        base=trade.base,
        quote=trade.quote_asset,
        base_qty=trade.base_qty,
        quote_qty=trade.quote_qty,
        fee_amount=trade.fee_amount,
        trade_id=trade.id,
    )
    deposit.status = "credited"
    add_stage(session, trade, "reserved")
    write_audit(
        session,
        user_id,
        "deposit.simulate",
        "deposit",
        str(deposit.id),
        {"asset": deposit.asset, "chain_tx_id": deposit.chain_tx_id},
    )
    body = {
        "deposit": deposit_public(deposit),
        "trade": trade_public(trade, stages_for(session, trade.id)),
    }
    hub.publish({"type": "deposit.updated", **body["deposit"]}, user_id=user_id, admin=True)
    hub.publish({"type": "trade.updated", **body["trade"]}, user_id=user_id, admin=True)
    hub.publish({"type": "balances.changed"}, user_id=user_id, admin=True)
    return body

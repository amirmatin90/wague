from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.service import write_audit
from app.errors import ApiError
from app.hyperliquid.cloid import hedge_cloid
from app.ledger.service import reserve_for_trade
from app.models import KillSwitch, Quote, Trade, TradeStage
from app.realtime.hub import hub
from app.schemas import quote_public, trade_public


STAGE_ORDER = (
    "accepted",
    "reserved",
    "hedging",
    "filling",
    "reconciling",
    "settling",
    "settled",
)


def add_stage(session: Session, trade: Trade, name: str) -> None:
    session.add(TradeStage(trade_id=trade.id, name=name))
    trade.status = name
    trade.updated_at = session.scalar(select(func.now()))
    session.flush()


def stages_for(session: Session, trade_id: UUID) -> list[TradeStage]:
    return list(
        session.scalars(
            select(TradeStage).where(TradeStage.trade_id == trade_id).order_by(TradeStage.at.asc())
        )
    )


def kill_switch_row(session: Session, *, for_update: bool) -> KillSwitch | None:
    stmt = select(KillSwitch).where(KillSwitch.id == 1)
    if for_update:
        stmt = stmt.with_for_update()
    return session.scalar(stmt)


def assert_desk_open(session: Session) -> None:
    row = kill_switch_row(session, for_update=False)
    if row is None or row.engaged:
        raise ApiError(423, "KILL_SWITCH", "Desk is halted")


def honor_quote(session: Session, user_id: UUID, quote_id: UUID) -> dict:
    ks = kill_switch_row(session, for_update=True)
    quote = session.scalar(select(Quote).where(Quote.id == quote_id).with_for_update())
    now = session.scalar(select(func.now()))

    if quote is None:
        raise ApiError(404, "QUOTE_NOT_FOUND", "Quote not found")
    if quote.user_id != user_id:
        raise ApiError(404, "QUOTE_NOT_FOUND", "Quote not found")

    if ks is None or ks.engaged:
        raise ApiError(423, "KILL_SWITCH", "Desk is halted")

    if quote.status == "accepted":
        existing = session.scalar(select(Trade).where(Trade.quote_id == quote.id))
        if existing is not None:
            return trade_public(existing, stages_for(session, existing.id))

    honorable = quote.status == "quoted" and quote.expires_at > now
    if not honorable:
        if quote.status == "quoted":
            quote.status = "expired"
            raise ApiError(422, "QUOTE_EXPIRED", "Quote is no longer firm")
        raise ApiError(422, "QUOTE_NOT_HONORABLE", "Quote cannot be accepted")

    # Last-look is forbidden: the locked quote price is used as-is. No reprice.
    trade_id = uuid4()
    trade = Trade(
        id=trade_id,
        quote_id=quote.id,
        rfq_id=quote.rfq_id,
        user_id=quote.user_id,
        side=quote.side,
        base=quote.base,
        quote_asset=quote.quote_asset,
        base_qty=quote.base_qty,
        quote_qty=quote.quote_qty,
        price=quote.price,
        fee_amount=quote.fee_amount,
        status="accepted",
        cloid=hedge_cloid(trade_id),
    )
    session.add(trade)
    session.flush()
    add_stage(session, trade, "accepted")
    reserve_for_trade(
        session,
        user_id=quote.user_id,
        side=quote.side,
        base=quote.base,
        quote=quote.quote_asset,
        base_qty=quote.base_qty,
        quote_qty=quote.quote_qty,
        fee_amount=quote.fee_amount,
        trade_id=trade.id,
    )
    add_stage(session, trade, "reserved")
    quote.status = "accepted"
    write_audit(
        session,
        user_id,
        "quote.accept",
        "trade",
        str(trade.id),
        {"quote_id": str(quote.id), "price": str(quote.price)},
    )
    body = trade_public(trade, stages_for(session, trade.id))
    hub.publish({"type": "trade.updated", **body}, user_id=user_id, admin=True)
    hub.publish({"type": "balances.changed"}, user_id=user_id, admin=True)
    return body


def get_trade(session: Session, trade_id: UUID, user: object) -> dict:
    trade = session.get(Trade, trade_id)
    if trade is None:
        raise ApiError(404, "TRADE_NOT_FOUND", "Trade not found")
    role = getattr(user, "role", None)
    if role not in {"ops", "cto"} and trade.user_id != getattr(user, "id", None):
        raise ApiError(404, "TRADE_NOT_FOUND", "Trade not found")
    return trade_public(trade, stages_for(session, trade.id))


def list_client_trades(session: Session, user_id: UUID) -> list[dict]:
    trades = session.scalars(
        select(Trade).where(Trade.user_id == user_id).order_by(Trade.created_at.desc())
    ).all()
    return [trade_public(trade, stages_for(session, trade.id)) for trade in trades]

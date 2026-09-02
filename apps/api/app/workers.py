from __future__ import annotations

import logging
import threading
import time

from sqlalchemy import select

from app.db import SessionLocal
from app.hyperliquid.stub import get_hyperliquid
from app.ledger.service import settle_trade
from app.models import Trade
from app.realtime.hub import hub
from app.recon.service import reconcile
from app.schemas import trade_public
from app.trade.service import add_stage, stages_for

log = logging.getLogger("wague.workers")
_stop = threading.Event()

ACTIVE = ("reserved", "hedging", "filling", "reconciling", "settling")


def _advance(session, trade: Trade) -> None:
    venue = get_hyperliquid()
    if trade.status == "reserved":
        add_stage(session, trade, "hedging")
        return
    if trade.status == "hedging":
        fill = venue.hedge(
            cloid=trade.cloid,
            side="sell" if trade.side == "buy" else "buy",
            base=trade.base,
            qty=trade.base_qty,
            price=trade.price,
        )
        trade.hedge_filled_qty = fill.filled_qty
        trade.hedge_avg_price = fill.avg_price
        add_stage(session, trade, "filling")
        return
    if trade.status == "filling":
        add_stage(session, trade, "reconciling")
        return
    if trade.status == "reconciling":
        reconcile(session, trade)
        add_stage(session, trade, "settling")
        return
    if trade.status == "settling":
        settle_trade(
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
        add_stage(session, trade, "settled")


def advance_one() -> bool:
    session = SessionLocal()
    try:
        trade = session.scalar(
            select(Trade)
            .where(Trade.status.in_(ACTIVE))
            .order_by(Trade.updated_at.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if trade is None:
            session.rollback()
            return False
        _advance(session, trade)
        session.commit()
        session.refresh(trade)
        body = trade_public(trade, stages_for(session, trade.id))
        hub.publish({"type": "trade.updated", **body}, user_id=trade.user_id, admin=True)
        if trade.status == "settled":
            hub.publish({"type": "balances.changed"}, user_id=trade.user_id, admin=True)
        return True
    except Exception:
        session.rollback()
        log.exception("worker failed to advance a trade")
        return False
    finally:
        session.close()


def worker_loop() -> None:
    while not _stop.is_set():
        if not advance_one():
            _stop.wait(0.05)


def start_workers() -> None:
    thread = threading.Thread(target=worker_loop, name="otc-workers", daemon=True)
    thread.start()


def stop_workers() -> None:
    _stop.set()

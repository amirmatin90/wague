from __future__ import annotations

import logging
import threading

from sqlalchemy import select

from app.db import SessionLocal
from app.errors import ApiError
from app.hyperliquid.client import place_spot_ioc
from app.ledger.service import pay_need, release_reserve, settle_from_fill
from app.models import Trade
from app.realtime.hub import hub
from app.recon.service import reconcile
from app.trade.service import add_stage, _trade_body

log = logging.getLogger("wague.workers")
_stop = threading.Event()

ACTIVE = ("reserved", "swapping", "settling")


def _fail(session, trade: Trade, message: str) -> None:
    asset, amount = pay_need(trade.side, trade.base_qty, trade.quote_qty, trade.fee_amount)
    if trade.status in {"reserved", "swapping"}:
        try:
            release_reserve(
                session,
                user_id=trade.user_id,
                asset=asset,
                amount=amount,
                trade_id=trade.id,
            )
        except Exception:
            log.exception("failed to release reserve after IOC error")
    trade.error_message = message
    add_stage(session, trade, "failed")


def _advance(session, trade: Trade) -> None:
    if trade.status == "reserved":
        add_stage(session, trade, "swapping")
        return
    if trade.status == "swapping":
        try:
            fill = place_spot_ioc(
                trade_id=trade.id,
                is_buy=trade.side == "buy",
                qty=trade.base_qty,
                limit_px=trade.price,
            )
        except ApiError as exc:
            _fail(session, trade, exc.message)
            return
        if fill.filled_qty < trade.base_qty:
            _fail(session, trade, "IOC did not fill the honored size; no stub fill is applied")
            return
        trade.hedge_filled_qty = fill.filled_qty
        trade.hedge_avg_price = fill.avg_price
        add_stage(session, trade, "settling")
        return
    if trade.status == "settling":
        settle_from_fill(
            session,
            user_id=trade.user_id,
            side=trade.side,
            base=trade.base,
            quote=trade.quote_asset,
            base_qty=trade.base_qty,
            quote_qty=trade.quote_qty,
            fee_amount=trade.fee_amount,
            filled_qty=trade.hedge_filled_qty or trade.base_qty,
            trade_id=trade.id,
        )
        reconcile(session, trade)
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
        body = _trade_body(session, trade)
        hub.publish({"type": "trade.updated", **body}, user_id=trade.user_id, admin=True)
        if trade.status in {"settled", "failed"}:
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

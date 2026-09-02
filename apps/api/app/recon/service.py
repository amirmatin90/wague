from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ReconResult, Trade


def reconcile(session: Session, trade: Trade) -> ReconResult:
    existing = session.scalar(select(ReconResult).where(ReconResult.trade_id == trade.id))
    if existing is not None:
        return existing
    hedge_qty = Decimal(trade.hedge_filled_qty or 0)
    hedge_px = Decimal(trade.hedge_avg_price or 0)
    client_qty = Decimal(trade.base_qty)
    client_px = Decimal(trade.price)
    matched = hedge_qty == client_qty and hedge_px == client_px
    row = ReconResult(
        trade_id=trade.id,
        status="matched" if matched else "break",
        client_base_qty=client_qty,
        hedge_base_qty=hedge_qty,
        client_price=client_px,
        hedge_price=hedge_px,
        notes="stub hedge filled the locked quote size and price"
        if matched
        else "hedge fill does not match the honored quote",
    )
    session.add(row)
    session.flush()
    return row

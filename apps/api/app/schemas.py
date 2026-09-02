from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.money import dec_str
from app.models import Quote, ReconResult, Trade, TradeStage


def iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        return dt.isoformat() + "Z"
    return dt.isoformat()


def quote_public(quote: Quote) -> dict:
    return {
        "quote_id": str(quote.id),
        "rfq_id": str(quote.rfq_id),
        "side": quote.side,
        "base": quote.base,
        "quote": quote.quote_asset,
        "base_qty": dec_str(Decimal(quote.base_qty)),
        "quote_qty": dec_str(Decimal(quote.quote_qty)),
        "price": dec_str(Decimal(quote.price)),
        "fee_amount": dec_str(Decimal(quote.fee_amount)),
        "fee_bps": dec_str(Decimal(quote.fee_bps)),
        "ttl_ms": quote.ttl_ms,
        "expires_at": iso(quote.expires_at),
        "status": quote.status,
    }


def trade_public(trade: Trade, stages: list[TradeStage]) -> dict:
    return {
        "trade_id": str(trade.id),
        "quote_id": str(trade.quote_id),
        "rfq_id": str(trade.rfq_id),
        "side": trade.side,
        "base": trade.base,
        "quote": trade.quote_asset,
        "base_qty": dec_str(Decimal(trade.base_qty)),
        "quote_qty": dec_str(Decimal(trade.quote_qty)),
        "price": dec_str(Decimal(trade.price)),
        "fee_amount": dec_str(Decimal(trade.fee_amount)),
        "status": trade.status,
        "stages": [{"name": stage.name, "at": iso(stage.at)} for stage in stages],
        "created_at": iso(trade.created_at),
        "updated_at": iso(trade.updated_at),
    }


def recon_public(row: ReconResult) -> dict:
    return {
        "recon_id": str(row.id),
        "trade_id": str(row.trade_id),
        "status": row.status,
        "client_base_qty": dec_str(Decimal(row.client_base_qty)),
        "hedge_base_qty": dec_str(Decimal(row.hedge_base_qty)),
        "client_price": dec_str(Decimal(row.client_price)),
        "hedge_price": dec_str(Decimal(row.hedge_price)),
        "notes": row.notes,
        "created_at": iso(row.created_at),
    }


def assert_no_venue_ids(payload: object) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in {"cloid", "oid"}:
                raise RuntimeError("internal venue identifiers must not appear in API payloads")
            assert_no_venue_ids(value)
    elif isinstance(payload, list):
        for item in payload:
            assert_no_venue_ids(item)

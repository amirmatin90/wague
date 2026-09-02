from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.money import BASE_QUANT, USDC_QUANT, dec_str
from app.models import Quote, ReconResult, Trade, TradeStage


def money(value: Decimal, quant) -> str:
    return dec_str(Decimal(value).quantize(quant))


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
        "base_qty": money(quote.base_qty, BASE_QUANT),
        "quote_qty": money(quote.quote_qty, USDC_QUANT),
        "price": money(quote.price, USDC_QUANT),
        "fee_amount": money(quote.fee_amount, USDC_QUANT),
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
        "base_qty": money(trade.base_qty, BASE_QUANT),
        "quote_qty": money(trade.quote_qty, USDC_QUANT),
        "price": money(trade.price, USDC_QUANT),
        "fee_amount": money(trade.fee_amount, USDC_QUANT),
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
        "client_base_qty": money(row.client_base_qty, BASE_QUANT),
        "hedge_base_qty": money(row.hedge_base_qty, BASE_QUANT),
        "client_price": money(row.client_price, USDC_QUANT),
        "hedge_price": money(row.hedge_price, USDC_QUANT),
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

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.money import BASE_QUANT, USDC_QUANT, dec_str
from app.models import Deposit, Quote, ReconResult, Trade, TradeStage


def money(value: Decimal, quant) -> str:
    return dec_str(Decimal(value).quantize(quant))


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.isoformat() + "Z"
    return dt.isoformat()


def quote_public(quote: Quote, extras: dict | None = None) -> dict:
    pay_asset = extras.get("pay_asset") if extras else None
    receive_asset = extras.get("receive_asset") if extras else None
    pay_qty = extras.get("pay_qty") if extras else None
    receive_qty = extras.get("receive_qty") if extras else None
    if pay_asset is None:
        pay_asset = quote.quote_asset if quote.side == "buy" else quote.base
        receive_asset = quote.base if quote.side == "buy" else quote.quote_asset
        pay_qty = quote.quote_qty if quote.side == "buy" else quote.base_qty
        receive_qty = quote.base_qty if quote.side == "buy" else quote.quote_qty
    body = {
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
        "pay_asset": pay_asset,
        "receive_asset": receive_asset,
        "pay_qty": money(pay_qty, USDC_QUANT if pay_asset == "USDC" else BASE_QUANT),
        "receive_qty": money(receive_qty, USDC_QUANT if receive_asset == "USDC" else BASE_QUANT),
    }
    if extras:
        for key in ("pay_usd", "receive_usd", "mid"):
            if key in extras:
                body[key] = money(extras[key], USDC_QUANT)
    assert_no_venue_ids(body)
    return body


def deposit_public(row: Deposit) -> dict:
    return {
        "deposit_id": str(row.id),
        "trade_id": str(row.trade_id),
        "asset": row.asset,
        "amount": money(row.amount, USDC_QUANT if row.asset == "USDC" else BASE_QUANT),
        "address": row.address,
        "status": row.status,
        "chain_tx_id": row.chain_tx_id,
        "created_at": iso(row.created_at),
        "confirmed_at": iso(row.confirmed_at),
    }


def trade_public(trade: Trade, stages: list[TradeStage], deposit: Deposit | None = None) -> dict:
    pay_asset = trade.quote_asset if trade.side == "buy" else trade.base
    receive_asset = trade.base if trade.side == "buy" else trade.quote_asset
    pay_qty = trade.quote_qty if trade.side == "buy" else trade.base_qty
    receive_qty = trade.base_qty if trade.side == "buy" else trade.quote_qty
    body = {
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
        "pay_asset": pay_asset,
        "receive_asset": receive_asset,
        "pay_qty": money(pay_qty, USDC_QUANT if pay_asset == "USDC" else BASE_QUANT),
        "receive_qty": money(receive_qty, USDC_QUANT if receive_asset == "USDC" else BASE_QUANT),
        "status": trade.status,
        "error_message": trade.error_message,
        "stages": [{"name": stage.name, "at": iso(stage.at)} for stage in stages],
        "fill": None
        if trade.hedge_filled_qty is None
        else {
            "filled_qty": money(trade.hedge_filled_qty, BASE_QUANT),
            "avg_price": money(trade.hedge_avg_price or Decimal("0"), USDC_QUANT),
        },
        "created_at": iso(trade.created_at),
        "updated_at": iso(trade.updated_at),
    }
    if deposit is not None:
        body["deposit"] = deposit_public(deposit)
    assert_no_venue_ids(body)
    return body


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

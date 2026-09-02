from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import LedgerAccount, LedgerEntry, LedgerTxn
from app.money import BASE_QUANT, USDC_QUANT, dec_str

DESK_PARTY_ID = UUID("00000000-0000-0000-0000-000000000001")
ASSETS = ("BTC", "ETH", "USDC")


def get_account(
    session: Session,
    party_type: str,
    party_id: UUID,
    asset: str,
    kind: str,
    *,
    for_update: bool,
) -> LedgerAccount | None:
    stmt = select(LedgerAccount).where(
        LedgerAccount.party_type == party_type,
        LedgerAccount.party_id == party_id,
        LedgerAccount.asset == asset,
        LedgerAccount.kind == kind,
    )
    if for_update:
        stmt = stmt.with_for_update()
    return session.scalar(stmt)


def require_account(
    session: Session,
    party_type: str,
    party_id: UUID,
    asset: str,
    kind: str,
) -> LedgerAccount:
    account = get_account(session, party_type, party_id, asset, kind, for_update=True)
    if account is None:
        raise ApiError(500, "LEDGER_MISSING", f"Missing {party_type} {asset} {kind} account")
    return account


def ensure_account(
    session: Session,
    party_type: str,
    party_id: UUID,
    asset: str,
    kind: str,
    opening: Decimal,
) -> LedgerAccount:
    existing = get_account(session, party_type, party_id, asset, kind, for_update=False)
    if existing is not None:
        return existing
    account = LedgerAccount(
        party_type=party_type,
        party_id=party_id,
        asset=asset,
        kind=kind,
        balance=opening,
    )
    session.add(account)
    session.flush()
    return account


def post_entries(
    session: Session,
    *,
    kind: str,
    trade_id: UUID | None,
    legs: list[tuple[LedgerAccount, Decimal]],
) -> LedgerTxn:
    total = sum((amount for _, amount in legs), Decimal("0"))
    if total != Decimal("0"):
        raise RuntimeError(f"ledger legs do not balance: {total}")
    txn = LedgerTxn(trade_id=trade_id, kind=kind)
    session.add(txn)
    session.flush()
    for account, amount in legs:
        account.balance = account.balance + amount
        session.add(LedgerEntry(txn_id=txn.id, account_id=account.id, amount=amount))
    return txn


def reserve_for_trade(
    session: Session,
    *,
    user_id: UUID,
    side: str,
    base: str,
    quote: str,
    base_qty: Decimal,
    quote_qty: Decimal,
    fee_amount: Decimal,
    trade_id: UUID,
) -> None:
    if side == "buy":
        need = quote_qty + fee_amount
        avail = require_account(session, "client", user_id, quote, "available")
        reserved = require_account(session, "client", user_id, quote, "reserved")
        if avail.balance < need:
            raise ApiError(422, "INSUFFICIENT_BALANCE", f"Insufficient {quote} to reserve this quote")
        post_entries(
            session,
            kind="reserve",
            trade_id=trade_id,
            legs=[(avail, -need), (reserved, need)],
        )
    else:
        avail = require_account(session, "client", user_id, base, "available")
        reserved = require_account(session, "client", user_id, base, "reserved")
        if avail.balance < base_qty:
            raise ApiError(422, "INSUFFICIENT_BALANCE", f"Insufficient {base} to reserve this quote")
        post_entries(
            session,
            kind="reserve",
            trade_id=trade_id,
            legs=[(avail, -base_qty), (reserved, base_qty)],
        )


def settle_trade(
    session: Session,
    *,
    user_id: UUID,
    side: str,
    base: str,
    quote: str,
    base_qty: Decimal,
    quote_qty: Decimal,
    fee_amount: Decimal,
    trade_id: UUID,
) -> None:
    if side == "buy":
        need = quote_qty + fee_amount
        client_reserved = require_account(session, "client", user_id, quote, "reserved")
        client_base = require_account(session, "client", user_id, base, "available")
        desk_quote = require_account(session, "desk", DESK_PARTY_ID, quote, "available")
        desk_base = require_account(session, "desk", DESK_PARTY_ID, base, "available")
        if client_reserved.balance < need:
            raise ApiError(500, "LEDGER_BREAK", "Reserved quote currency is short")
        if desk_base.balance < base_qty:
            raise ApiError(500, "LEDGER_BREAK", "Desk base inventory is short")
        post_entries(
            session,
            kind="settle",
            trade_id=trade_id,
            legs=[
                (client_reserved, -need),
                (desk_quote, need),
                (desk_base, -base_qty),
                (client_base, base_qty),
            ],
        )
    else:
        client_reserved = require_account(session, "client", user_id, base, "reserved")
        client_quote = require_account(session, "client", user_id, quote, "available")
        desk_base = require_account(session, "desk", DESK_PARTY_ID, base, "available")
        desk_quote = require_account(session, "desk", DESK_PARTY_ID, quote, "available")
        proceeds = quote_qty - fee_amount
        if client_reserved.balance < base_qty:
            raise ApiError(500, "LEDGER_BREAK", "Reserved base is short")
        if desk_quote.balance < proceeds:
            raise ApiError(500, "LEDGER_BREAK", "Desk quote inventory is short")
        post_entries(
            session,
            kind="settle",
            trade_id=trade_id,
            legs=[
                (client_reserved, -base_qty),
                (desk_base, base_qty),
                (desk_quote, -proceeds),
                (client_quote, proceeds),
            ],
        )


def client_balances(session: Session, user_id: UUID) -> list[dict]:
    rows = session.scalars(
        select(LedgerAccount).where(
            LedgerAccount.party_type == "client", LedgerAccount.party_id == user_id
        )
    ).all()
    by_asset: dict[str, dict[str, Decimal]] = {}
    for row in rows:
        bucket = by_asset.setdefault(row.asset, {"available": Decimal("0"), "reserved": Decimal("0")})
        bucket[row.kind] = Decimal(row.balance)
    return [
        {
            "asset": asset,
            "available": dec_str(by_asset[asset]["available"].quantize(USDC_QUANT if asset == "USDC" else BASE_QUANT)),
            "reserved": dec_str(by_asset[asset]["reserved"].quantize(USDC_QUANT if asset == "USDC" else BASE_QUANT)),
        }
        for asset in ASSETS
        if asset in by_asset
    ]


def desk_positions(session: Session) -> list[dict]:
    rows = session.scalars(
        select(LedgerAccount).where(
            LedgerAccount.party_type == "desk",
            LedgerAccount.party_id == DESK_PARTY_ID,
            LedgerAccount.kind == "available",
        )
    ).all()
    return [
        {
            "asset": row.asset,
            "qty": dec_str(Decimal(row.balance).quantize(USDC_QUANT if row.asset == "USDC" else BASE_QUANT)),
        }
        for row in rows
    ]


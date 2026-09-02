"""initial otc desk schema

Revision ID: 0001_init
Revises:
Create Date: 2026-09-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_init"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "kill_switch",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("engaged", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_table(
        "rfqs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("base", sa.String(8), nullable=False),
        sa.Column("quote_asset", sa.String(8), nullable=False),
        sa.Column("base_qty", sa.Numeric(36, 18), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "quotes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("rfq_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rfqs.id"), nullable=False, unique=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("base", sa.String(8), nullable=False),
        sa.Column("quote_asset", sa.String(8), nullable=False),
        sa.Column("base_qty", sa.Numeric(36, 18), nullable=False),
        sa.Column("quote_qty", sa.Numeric(36, 18), nullable=False),
        sa.Column("price", sa.Numeric(36, 18), nullable=False),
        sa.Column("fee_amount", sa.Numeric(36, 18), nullable=False),
        sa.Column("fee_bps", sa.Numeric(36, 18), nullable=False),
        sa.Column("ttl_ms", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "trades",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("quote_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("quotes.id"), nullable=False, unique=True),
        sa.Column("rfq_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rfqs.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("base", sa.String(8), nullable=False),
        sa.Column("quote_asset", sa.String(8), nullable=False),
        sa.Column("base_qty", sa.Numeric(36, 18), nullable=False),
        sa.Column("quote_qty", sa.Numeric(36, 18), nullable=False),
        sa.Column("price", sa.Numeric(36, 18), nullable=False),
        sa.Column("fee_amount", sa.Numeric(36, 18), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("cloid", sa.String(66), nullable=False, unique=True),
        sa.Column("hedge_filled_qty", sa.Numeric(36, 18), nullable=True),
        sa.Column("hedge_avg_price", sa.Numeric(36, 18), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_trades_status", "trades", ["status"])
    op.create_table(
        "trade_stages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("trade_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("trades.id"), nullable=False),
        sa.Column("name", sa.String(32), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_trade_stages_trade_id", "trade_stages", ["trade_id"])
    op.create_table(
        "ledger_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("party_type", sa.String(16), nullable=False),
        sa.Column("party_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset", sa.String(8), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("balance", sa.Numeric(36, 18), nullable=False),
        sa.UniqueConstraint("party_type", "party_id", "asset", "kind", name="uq_ledger_account_book"),
    )
    op.create_table(
        "ledger_txns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("trade_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "ledger_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("txn_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ledger_txns.id"), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ledger_accounts.id"), nullable=False),
        sa.Column("amount", sa.Numeric(36, 18), nullable=False),
    )
    op.create_table(
        "idempotency_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("route", sa.String(255), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("response_json", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "key", name="uq_idempotency_user_key"),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "recon_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("trade_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("trades.id"), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("client_base_qty", sa.Numeric(36, 18), nullable=False),
        sa.Column("hedge_base_qty", sa.Numeric(36, 18), nullable=False),
        sa.Column("client_price", sa.Numeric(36, 18), nullable=False),
        sa.Column("hedge_price", sa.Numeric(36, 18), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("recon_results")
    op.drop_table("audit_events")
    op.drop_table("idempotency_keys")
    op.drop_table("ledger_entries")
    op.drop_table("ledger_txns")
    op.drop_table("ledger_accounts")
    op.drop_index("ix_trade_stages_trade_id", table_name="trade_stages")
    op.drop_table("trade_stages")
    op.drop_index("ix_trades_status", table_name="trades")
    op.drop_table("trades")
    op.drop_table("quotes")
    op.drop_table("rfqs")
    op.drop_table("kill_switch")
    op.drop_table("users")

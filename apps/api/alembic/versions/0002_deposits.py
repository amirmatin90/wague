"""deposits and trade error message

Revision ID: 0002_deposits
Revises: 0001_init
Create Date: 2026-09-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_deposits"
down_revision: Union[str, None] = "0001_init"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("trades", sa.Column("error_message", sa.Text(), nullable=True))
    op.create_table(
        "deposits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("trade_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("trades.id"), nullable=False, unique=True),
        sa.Column("asset", sa.String(8), nullable=False),
        sa.Column("amount", sa.Numeric(36, 18), nullable=False),
        sa.Column("address", sa.String(66), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("chain_tx_id", sa.String(128), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("deposits")
    op.drop_column("trades", "error_message")

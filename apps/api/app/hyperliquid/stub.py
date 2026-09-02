from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class HedgeFill:
    filled_qty: Decimal
    avg_price: Decimal
    status: str


class StubHyperliquid:
    """Local venue stand-in. Always fills the full size immediately at the locked quote price."""

    def hedge(
        self,
        *,
        cloid: str,
        side: str,
        base: str,
        qty: Decimal,
        price: Decimal,
    ) -> HedgeFill:
        _ = (cloid, side, base)
        return HedgeFill(filled_qty=qty, avg_price=price, status="filled")


def get_hyperliquid() -> StubHyperliquid:
    return StubHyperliquid()

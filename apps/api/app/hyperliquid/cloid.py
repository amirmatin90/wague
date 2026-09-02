from __future__ import annotations

import hashlib
from uuid import UUID


def hedge_cloid(trade_id: UUID) -> str:
    canonical = str(trade_id).encode("ascii")
    digest = hashlib.sha256(b"otc-hedge-v1|" + canonical).digest()
    return "0x" + digest[:16].hex()

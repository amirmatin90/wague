from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN

USDC_QUANT = Decimal("0.01")
BASE_QUANT = Decimal("0.00000001")
BPS_QUANT = Decimal("0.01")


def parse_decimal(value: object, *, field: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} must be a decimal string")
    if isinstance(value, float):
        raise ValueError(f"{field} must be a decimal string, not a float")
    if isinstance(value, int):
        text = str(value)
    elif isinstance(value, Decimal):
        text = format(value, "f")
    elif isinstance(value, str):
        text = value.strip()
    else:
        raise ValueError(f"{field} must be a decimal string")
    if not text or text.lower() in {"nan", "inf", "-inf", "+inf"}:
        raise ValueError(f"{field} is not a valid decimal")
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"{field} is not a valid decimal") from exc
    if amount.is_nan() or amount.is_infinite():
        raise ValueError(f"{field} is not a valid decimal")
    return amount


def dec_str(value: Decimal) -> str:
    return format(value, "f")


def q_usdc(value: Decimal) -> Decimal:
    return value.quantize(USDC_QUANT, rounding=ROUND_HALF_EVEN)


def q_base(value: Decimal) -> Decimal:
    return value.quantize(BASE_QUANT, rounding=ROUND_HALF_EVEN)


def q_bps(value: Decimal) -> Decimal:
    return value.quantize(BPS_QUANT, rounding=ROUND_HALF_EVEN)

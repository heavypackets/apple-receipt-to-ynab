from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

MILLIUNIT_FACTOR = Decimal("1000")


def dollars_to_milliunits(amount: Decimal) -> int:
    return int((amount * MILLIUNIT_FACTOR).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def milliunits_to_dollars(amount: int) -> Decimal:
    return (Decimal(amount) / MILLIUNIT_FACTOR).quantize(Decimal("0.001"))


def now_local_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def clean_text(value: str) -> str:
    return " ".join(value.split())


# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure derivation math for persisted EVM snapshots.

When a schedule's data date advances we freeze a rollup of the time-phased
earned-value figures the schedule already computes (planned value, earned value,
budget at completion) so the cost / schedule performance trend can be charted
over time. This module holds the only *derived* figure in that rollup - the
schedule performance index - as a dependency-free function so it unit-tests on
the local Python 3.11 runner, exactly like :mod:`progress_math`.

Why only the schedule performance index (SPI)?
----------------------------------------------
The schedule domain computes PV, EV and BAC but never an actual cost (AC): no
code path in the progress service reads ``Activity.cost_actual`` into the EVM
rollup. The two cost-performance figures that need AC - the cost performance
index ``CPI = EV / AC`` and any cost variance - are therefore *not* derivable
here and are deliberately omitted from the snapshot rather than fabricated. The
schedule performance index ``SPI = EV / PV`` needs only PV and EV, both of which
are available, so it is the single derived figure we persist.

Money discipline
----------------
PV / EV / BAC are :class:`~decimal.Decimal` end-to-end (never ``float``); the SPI
is a dimensionless ratio, so it is returned as a quantised ``Decimal`` too but
carries no currency. The divide-by-zero case (no planned value yet at this data
date) returns ``None`` rather than raising or inventing a value.

Determinism
-----------
No wall-clock reads and no randomness: every input is passed explicitly so a
recomputed snapshot is bit-for-bit reproducible.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

_ZERO = Decimal("0")
#: Performance-index quantum - three decimals is plenty for a charted ratio.
_INDEX_Q = Decimal("0.001")


def _to_decimal(value: Any, default: Decimal = _ZERO) -> Decimal:
    """Coerce a numeric-ish input to :class:`Decimal`.

    ``None`` and unparseable values fall back to *default*; ``float`` is routed
    through ``str`` so binary-float noise never enters the ratio. Mirrors the
    coercion :mod:`progress_math` uses for money so the two engines agree.
    """
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):  # avoid True == 1 surprises
        return Decimal(int(value))
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        return default


def schedule_performance_index(
    earned_value: Any,
    planned_value: Any,
) -> Decimal | None:
    """Schedule performance index ``SPI = EV / PV``, quantised to three decimals.

    Returns ``None`` when planned value is zero or negative (no schedule baseline
    has accrued at this data date yet), so the divide-by-zero is reported as
    "not applicable" rather than crashing or reading as a misleading ``0`` or
    infinity. ``SPI == 1`` means on schedule, ``< 1`` behind, ``> 1`` ahead.
    """
    pv = _to_decimal(planned_value)
    if pv <= _ZERO:
        return None
    ev = _to_decimal(earned_value)
    spi = ev / pv
    return spi.quantize(_INDEX_Q, rounding=ROUND_HALF_UP)


__all__ = ["schedule_performance_index"]

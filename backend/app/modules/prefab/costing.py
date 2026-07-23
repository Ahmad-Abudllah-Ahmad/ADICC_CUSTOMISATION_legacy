# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Off-site / Prefab / DfMA cost derivation - pure, database-free helpers.

Turns a unit's linked rate (a BOQ position ``unit_rate`` or an assembly
``total_rate``) and its production stage into the read-model cost view: a cost
basis and a simple earned-value hint. Money is a Decimal serialised as a string
throughout - never a float - so large currency values round-trip exactly and
stay locale-neutral.

This module has no import-time database work (it depends only on the pure stage
machine in :mod:`app.modules.prefab.guard` and the stdlib), so it can be unit
tested on any interpreter.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.modules.prefab.guard import STAGE_ORDER, stage_completion_fraction, stage_index

# Cost basis / earned value are money, so they are Decimal serialised as strings
# (never float) - matching the BOQ position and assembly rate storage.
_MONEY_QUANT = Decimal("0.01")

# Progress is reported to the client rounded to this many decimals for a clean,
# stable JSON value; the earned-value money below uses the exact stage ratio.
_FRACTION_DP = 4


def to_decimal(value: str | None) -> Decimal | None:
    """Parse a stored rate string into a Decimal, or ``None`` if unparseable."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def derive_cost(rate: str | None, stage: str) -> tuple[str | None, float, str | None]:
    """Derive a unit's cost view from a linked rate and its production stage.

    The earned-value hint is the linked cost basis scaled by how far the unit
    has moved through production (design earns nothing, installed earns the full
    basis). The earned value is computed from the exact stage ratio in Decimal
    so no float ever enters the money path; the ``completed_fraction`` returned
    alongside is that same ratio rounded for display.

    Args:
        rate: The linked BOQ position ``unit_rate`` or assembly ``total_rate``
            as a stored string, or ``None`` when the unit is not linked.
        stage: The unit's current production stage.

    Returns:
        A ``(cost_basis, completed_fraction, earned_value)`` tuple. ``cost_basis``
        and ``earned_value`` are Decimal values serialised as strings (or
        ``None`` when there is no resolvable rate); ``completed_fraction`` is a
        progress ratio in ``0..1``.
    """
    fraction = round(stage_completion_fraction(stage), _FRACTION_DP)
    basis = to_decimal(rate)
    if basis is None:
        return None, fraction, None

    idx = stage_index(stage)
    last = len(STAGE_ORDER) - 1
    if idx <= 0 or last <= 0:
        earned = Decimal(0)
    else:
        # Exact rational progress (idx / last) kept in Decimal - never a float.
        earned = (basis * Decimal(idx) / Decimal(last)).quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)
    return str(basis), fraction, str(earned)

# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""DB-free tests for the off-site cost-link derivation.

These exercise the pure earned-value math in ``app.modules.prefab.costing`` and
the stage-completion fraction in ``app.modules.prefab.guard`` with no database,
session or fixtures - proving the contract the link feature rests on: a linked
BOQ position / assembly rate becomes the unit's cost basis, and earned value is
that basis scaled by how far the unit has moved through production.

Coverage
--------
* the completion fraction is 0 at design, 0.5 at QA and 1 at installed, and
  advances monotonically along the lifecycle
* an unknown stage yields a 0.0 fraction rather than raising
* cost basis mirrors the linked rate; earned value = basis * fraction
* money stays a Decimal serialised as a string (never a float)
* an unlinked or unparseable rate yields ``None`` basis/earned but still a
  usable progress fraction
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.prefab.costing import derive_cost, to_decimal
from app.modules.prefab.guard import STAGE_ORDER, stage_completion_fraction


def test_completion_fraction_endpoints_and_midpoint() -> None:
    assert stage_completion_fraction("design") == 0.0
    assert stage_completion_fraction("qa") == 0.5
    assert stage_completion_fraction("installed") == 1.0


def test_completion_fraction_is_monotonic_along_the_lifecycle() -> None:
    fractions = [stage_completion_fraction(s) for s in STAGE_ORDER]
    assert fractions == sorted(fractions)
    assert all(0.0 <= f <= 1.0 for f in fractions)
    # Every step strictly increases - no two stages share a progress value.
    assert len(set(fractions)) == len(STAGE_ORDER)


def test_completion_fraction_unknown_stage_is_zero_not_error() -> None:
    assert stage_completion_fraction("nonsense") == 0.0
    assert stage_completion_fraction("") == 0.0


def test_derive_cost_from_boq_rate_at_qa_is_half() -> None:
    basis, fraction, earned = derive_cost("100", "qa")
    assert basis == "100"
    assert fraction == 0.5
    assert earned == "50.00"


def test_derive_cost_installed_earns_the_full_basis() -> None:
    basis, fraction, earned = derive_cost("250.50", "installed")
    assert basis == "250.50"
    assert fraction == 1.0
    # Full basis earned, quantised to two-decimal money.
    assert Decimal(earned) == Decimal("250.50")


def test_derive_cost_design_earns_nothing() -> None:
    basis, fraction, earned = derive_cost("999.99", "design")
    assert basis == "999.99"
    assert fraction == 0.0
    assert Decimal(earned) == Decimal("0.00")


def test_derive_cost_money_is_string_never_float() -> None:
    basis, _fraction, earned = derive_cost("1200.00", "in_production")
    assert isinstance(basis, str)
    assert isinstance(earned, str)
    # 1200 * (2/6) rounded to cents.
    assert earned == "400.00"


def test_derive_cost_zero_rate_stays_zero() -> None:
    basis, fraction, earned = derive_cost("0", "dispatched")
    assert basis == "0"
    # The reported fraction is the stage progress rounded for display.
    assert fraction == round(stage_completion_fraction("dispatched"), 4)
    assert Decimal(earned) == Decimal("0")


@pytest.mark.parametrize("rate", [None, "", "n/a", "abc"])
def test_derive_cost_unlinked_or_unparseable_rate(rate: str | None) -> None:
    basis, fraction, earned = derive_cost(rate, "qa")
    assert basis is None
    assert earned is None
    # Progress is still reported even without a resolvable cost.
    assert fraction == 0.5


def test_derive_cost_preserves_precision_on_large_values() -> None:
    # A large currency value must not lose its tail to float rounding.
    basis, _fraction, earned = derive_cost("999999999.99", "installed")
    assert basis == "999999999.99"
    assert Decimal(earned) == Decimal("999999999.99")


def test_to_decimal_helper() -> None:
    assert to_decimal("12.34") == Decimal("12.34")
    assert to_decimal(None) is None
    assert to_decimal("nope") is None

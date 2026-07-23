# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Retention / withholding ledger rollup - pure, dependency-free arithmetic.

This module rolls the retention/withholding figures the finance module already
stores into a single per-project ledger view. It imports nothing from
SQLAlchemy or FastAPI so the maths can be unit-tested against plain data.

Two distinct bases are reported side by side, never conflated:

* SCHEDULED retention - ``Invoice.retention_amount``, the hold-back planned on
  the invoice / certified claim.
* HELD retainage - the sum of ``Payment.withholding_amount`` actually withheld
  at payment time. This is what "retention held to date" means.

"Released to date" is derived from ``Payment.withholding_release_date``:
retainage counts as released once its contractual release date has been reached
as of the reporting cutoff. The finance module does NOT record a separate
"retention paid back" transaction, so released here means release-DUE (the
release date has passed), not "cash physically returned". "Outstanding" is
``held - released`` clamped at zero.

Nothing is blended across currencies or across payable/receivable direction:
every group and total is scoped to a single (currency, direction) pair.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

_ZERO = Decimal("0")
_CENTS = Decimal("0.01")
_HUNDRED = Decimal("100")


# -- coercion / arithmetic helpers --------------------------------------------


def _to_decimal(value: object, default: Decimal = _ZERO) -> Decimal:
    """Coerce *value* to a finite Decimal; return *default* on any error.

    Local twin of ``app.modules.finance.service._safe_decimal`` so this module
    stays import-free of the service layer. Non-finite results (NaN / Infinity)
    collapse to *default* so a corrupt row can never poison a sum.
    """
    if isinstance(value, Decimal):
        return value if value.is_finite() else default
    if value is None:
        return default
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        return default
    return parsed if parsed.is_finite() else default


def _q2(value: Decimal) -> Decimal:
    """Quantize a money Decimal to 2 places (half-up, the accounting default)."""
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


def _pct(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    """Return ``numerator / denominator * 100`` as a 2dp Decimal, or None.

    Guarded division: a zero (or absent) denominator yields ``None`` rather than
    raising, so the caller renders "n/a" instead of dividing by zero. Never
    returns a float - the percentage is a quantized Decimal.
    """
    if denominator == _ZERO:
        return None
    return (numerator / denominator * _HUNDRED).quantize(_CENTS, rounding=ROUND_HALF_UP)


def _is_released(release_date: str | None, as_of: str | None) -> bool:
    """True when retainage dated *release_date* is released as of *as_of*.

    Retainage counts as released once its contractual release date has been
    reached. ISO-8601 dates order correctly as plain strings, so no date parsing
    is needed:

    * ``release_date`` empty / None -> never released (no scheduled release).
    * ``as_of`` None -> no cutoff supplied, so any dated retainage counts.
    * otherwise -> released iff ``release_date <= as_of``.
    """
    if not release_date:
        return False
    if as_of is None:
        return True
    return release_date <= as_of


# -- input records (plain data, no ORM) ---------------------------------------


@dataclass(frozen=True)
class PaymentWithholding:
    """One payment row's retainage contribution.

    ``withholding_amount`` is the retainage held back at this payment (money,
    accepted as Decimal / str / number). ``release_date`` is the ISO date the
    retainage becomes releasable, or None.
    """

    withholding_amount: object = _ZERO
    release_date: str | None = None


@dataclass(frozen=True)
class InvoiceRetention:
    """One invoice's retention context plus the withholding payments against it.

    ``retention_amount`` is the SCHEDULED hold-back on the invoice. ``payments``
    carry the retainage ACTUALLY withheld. ``contact_id`` is the counterparty
    (the closest thing the schema stores to a contract party) and is the group
    key; ``direction`` is the invoice direction (payable / receivable).
    """

    contact_id: str | None = None
    currency_code: str = ""
    direction: str = ""
    retention_amount: object = _ZERO
    payments: Sequence[PaymentWithholding] = ()


# -- output records -----------------------------------------------------------


@dataclass(frozen=True)
class RetentionRollup:
    """Held / released / outstanding retainage for one scope (a group or total).

    Money values are 2dp Decimals. The ``*_pct`` ratios are guarded: ``None``
    when their denominator is zero (never a divide-by-zero, never a float).

    Basis of each figure:

    * ``scheduled`` - sum of ``Invoice.retention_amount`` (planned hold-back).
    * ``held_to_date`` - sum of ``Payment.withholding_amount``.
    * ``released_to_date`` - held retainage whose release date has been reached.
    * ``outstanding`` - ``held_to_date - released_to_date`` clamped at zero.
    """

    currency_code: str
    direction: str
    contact_id: str | None
    scheduled: Decimal
    held_to_date: Decimal
    released_to_date: Decimal
    outstanding: Decimal
    payment_count: int
    released_pct: Decimal | None
    outstanding_pct: Decimal | None
    held_vs_scheduled_pct: Decimal | None
    earliest_release_date: str | None
    latest_release_date: str | None


@dataclass(frozen=True)
class RetentionLedger:
    """Project-wide retention / withholding rollup.

    ``groups`` breaks retainage down per counterparty within a single currency
    and direction. ``totals`` rolls the groups up per (currency, direction).
    ``as_of`` echoes the release-date cutoff used to classify released retainage.
    """

    as_of: str | None
    groups: list[RetentionRollup]
    totals: list[RetentionRollup]


@dataclass
class _Accumulator:
    """Mutable running totals for one group or total key."""

    scheduled: Decimal = _ZERO
    held: Decimal = _ZERO
    released: Decimal = _ZERO
    payment_count: int = 0
    earliest: str | None = None
    latest: str | None = None

    def note_release_date(self, release_date: str | None) -> None:
        """Widen the earliest / latest release-date span with *release_date*."""
        if not release_date:
            return
        if self.earliest is None or release_date < self.earliest:
            self.earliest = release_date
        if self.latest is None or release_date > self.latest:
            self.latest = release_date


# -- public API ---------------------------------------------------------------


def summarize_retention(
    held: object,
    released: object,
    *,
    scheduled: object | None = None,
    payment_count: int = 0,
    currency_code: str = "",
    direction: str = "",
    contact_id: str | None = None,
    earliest_release_date: str | None = None,
    latest_release_date: str | None = None,
) -> RetentionRollup:
    """Assemble a :class:`RetentionRollup` from held / released / scheduled money.

    Pure arithmetic core shared by every group and total. ``outstanding`` is
    clamped at zero: a caller feeding an inconsistent ``released`` larger than
    ``held`` (which cannot happen for date-derived rollups, where released is a
    subset of held, but can if released is supplied independently) yields
    ``outstanding == 0`` rather than a negative liability. Every ratio is guarded
    via :func:`_pct`, so a zero denominator returns ``None``.
    """
    held_d = _q2(_to_decimal(held))
    released_d = _q2(_to_decimal(released))
    scheduled_d = _q2(_to_decimal(scheduled)) if scheduled is not None else _ZERO
    # Clamp at zero: released can never leave a negative liability outstanding.
    outstanding_d = _q2(max(_ZERO, held_d - released_d))
    return RetentionRollup(
        currency_code=currency_code,
        direction=direction,
        contact_id=contact_id,
        scheduled=scheduled_d,
        held_to_date=held_d,
        released_to_date=released_d,
        outstanding=outstanding_d,
        payment_count=payment_count,
        released_pct=_pct(released_d, held_d),
        outstanding_pct=_pct(outstanding_d, held_d),
        held_vs_scheduled_pct=_pct(held_d, scheduled_d),
        earliest_release_date=earliest_release_date,
        latest_release_date=latest_release_date,
    )


def _rollup_sort_key(rollup: RetentionRollup) -> tuple[str, str, bool, str]:
    """Deterministic order: currency, direction, then contact (None last)."""
    return (
        rollup.currency_code,
        rollup.direction,
        rollup.contact_id is None,
        rollup.contact_id or "",
    )


def build_retention_ledger(
    invoices: Iterable[InvoiceRetention],
    *,
    as_of: str | None = None,
) -> RetentionLedger:
    """Roll a project's invoices + withholding payments into a retention ledger.

    Groups by (currency_code, direction, contact_id) so nothing blends across
    currencies or across payable / receivable, then totals per (currency,
    direction). ``as_of`` is the release-date cutoff (usually today, supplied by
    the caller): retainage whose ``release_date <= as_of`` counts as released.
    Pure and deterministic - no DB, no clock read.
    """
    group_acc: dict[tuple[str, str, str | None], _Accumulator] = {}
    total_acc: dict[tuple[str, str], _Accumulator] = {}

    for inv in invoices:
        currency = inv.currency_code or ""
        direction = inv.direction or ""
        scheduled = _to_decimal(inv.retention_amount)

        group = group_acc.setdefault((currency, direction, inv.contact_id), _Accumulator())
        total = total_acc.setdefault((currency, direction), _Accumulator())
        group.scheduled += scheduled
        total.scheduled += scheduled

        for pay in inv.payments:
            withheld = _to_decimal(pay.withholding_amount)
            if withheld == _ZERO:
                continue
            released = withheld if _is_released(pay.release_date, as_of) else _ZERO
            for acc in (group, total):
                acc.held += withheld
                acc.released += released
                acc.payment_count += 1
                acc.note_release_date(pay.release_date)

    groups = [
        summarize_retention(
            acc.held,
            acc.released,
            scheduled=acc.scheduled,
            payment_count=acc.payment_count,
            currency_code=key[0],
            direction=key[1],
            contact_id=key[2],
            earliest_release_date=acc.earliest,
            latest_release_date=acc.latest,
        )
        for key, acc in group_acc.items()
    ]
    totals = [
        summarize_retention(
            acc.held,
            acc.released,
            scheduled=acc.scheduled,
            payment_count=acc.payment_count,
            currency_code=key[0],
            direction=key[1],
            contact_id=None,
            earliest_release_date=acc.earliest,
            latest_release_date=acc.latest,
        )
        for key, acc in total_acc.items()
    ]
    groups.sort(key=_rollup_sort_key)
    totals.sort(key=_rollup_sort_key)
    return RetentionLedger(as_of=as_of, groups=groups, totals=totals)

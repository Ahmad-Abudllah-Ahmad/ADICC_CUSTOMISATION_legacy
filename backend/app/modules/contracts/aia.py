# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""AIA G702/G703 payment-application support (US/CA/AU only).

The AIA G702 (Application and Certificate for Payment) and G703
(Continuation Sheet) are the standard progress-billing documents used in the
United States and, by close adoption, Canada and Australia. They are NOT used
in DACH (DIN/Abschlagsrechnung), the UK (JCT interim certificate) or most other
markets, so this layer is country-gated: it only renders for projects whose
country resolves to US, CA or AU.

This module is deliberately additive on top of the existing progress-claim
engine (``ContractsService``/``ProgressClaim``/``ProgressClaimLine``). It does
NOT duplicate the claim FSM, the retention math or the finance invoice bridge.
What it adds is the AIA presentation layer:

* the gate (:func:`is_aia_eligible`),
* the G703 continuation-line math (:func:`build_g703_line`), and
* the G702 summary roll-up (:func:`build_g702_summary`).

All money is ``Decimal``; no float ever touches a currency value. The builders
are pure functions with hand-verifiable arithmetic so they can be unit-tested
against fixtures without a database.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

DEC_ZERO = Decimal("0")
DEC_HUNDRED = Decimal("100")
_QUANT = Decimal("0.01")

#: ISO 3166-1 alpha-2 codes whose projects may use AIA G702/G703.
AIA_COUNTRY_CODES: frozenset[str] = frozenset({"US", "CA", "AU"})

#: Full-name aliases (project.address["country"] stores display names like
#: "United States"). Mapped to the alpha-2 code so either representation gates
#: correctly. Lower-cased keys; lookup lower-cases the input.
_AIA_COUNTRY_ALIASES: dict[str, str] = {
    "us": "US",
    "usa": "US",
    "u.s.": "US",
    "u.s.a.": "US",
    "united states": "US",
    "united states of america": "US",
    "ca": "CA",
    "can": "CA",
    "canada": "CA",
    "au": "AU",
    "aus": "AU",
    "australia": "AU",
}


def normalise_country(value: str | None) -> str | None:
    """Map a country code or display name to its ISO alpha-2 code.

    Accepts an alpha-2 code (``"US"``), a three-letter code (``"USA"``) or a
    display name (``"United States"``). Returns the alpha-2 code, or ``None``
    when the input is empty or unrecognised.
    """
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    upper = raw.upper()
    if len(upper) == 2 and upper.isalpha():
        return upper
    return _AIA_COUNTRY_ALIASES.get(raw.lower())


def is_aia_eligible(country_code: str | None, address: Any = None) -> bool:
    """Return True when a project may use AIA G702/G703.

    Gating is purely a function of the project country. The project's
    ``country_code`` column is checked first; when it is empty or not a clean
    alpha-2 we fall back to ``address["country"]`` (a display name). A project
    is eligible only when the resolved country is one of US, CA, AU.
    """
    resolved = normalise_country(country_code)
    if resolved is None and isinstance(address, dict):
        resolved = normalise_country(address.get("country"))
    return resolved in AIA_COUNTRY_CODES


def _dec(value: Any) -> Decimal:
    """Coerce any stored money/number to Decimal, treating None/blank as 0."""
    if value in (None, ""):
        return DEC_ZERO
    return Decimal(str(value))


def _q(value: Decimal) -> Decimal:
    """Round to 2 dp, the AIA presentation precision (cents)."""
    return value.quantize(_QUANT, rounding=ROUND_HALF_UP)


def build_g703_line(
    contract_line: Any,
    claim_line: Any | None,
    *,
    line_number: int,
    retainage_percent: Decimal,
) -> dict[str, Any]:
    """Build one G703 continuation row from a SoV line + its claim line.

    Maps onto the standard AIA G703 columns:

    * A  item number
    * B  description of work
    * C  scheduled value (the contract/SoV line total)
    * D  work completed from previous applications
    * E  work completed this period
    * F  materials presently stored (not in D or E)
    * G  total completed and stored to date (= D + E + F)
    * G% percent G / C
    * H  balance to finish (= C - G)
    * I  retainage (= retainage_percent x G)

    ``claim_line`` may be ``None`` for an SoV line not billed in this period;
    its D/E/F columns are then zero. Previous-period value (column D) is read
    from the claim line's ``prior_completed_value`` when present, else derived
    from ``cumulative_completed_value - period_completed_value``. Stored
    materials (column F) come from ``materials_stored_value`` if present, else
    from the claim-line metadata key ``materials_stored_value`` (no DDL needed).

    All amounts are ``Decimal`` rounded to cents.
    """
    scheduled = _dec(getattr(contract_line, "total_value", 0))

    if claim_line is None:
        previous = DEC_ZERO
        this_period = DEC_ZERO
        stored = DEC_ZERO
    else:
        this_period = _dec(getattr(claim_line, "period_completed_value", 0))
        # Column D: prefer an explicit prior-value column when the schema has
        # it; otherwise derive from the running cumulative minus this period.
        prior_attr = getattr(claim_line, "prior_completed_value", None)
        if prior_attr not in (None, ""):
            previous = _dec(prior_attr)
        else:
            cumulative = _dec(getattr(claim_line, "cumulative_completed_value", 0))
            previous = cumulative - this_period
            if previous < DEC_ZERO:
                previous = DEC_ZERO
        # Column F: stored materials, from a dedicated column or metadata.
        stored_attr = getattr(claim_line, "materials_stored_value", None)
        if stored_attr not in (None, ""):
            stored = _dec(stored_attr)
        else:
            meta = getattr(claim_line, "metadata_", None) or {}
            stored = _dec(meta.get("materials_stored_value")) if isinstance(meta, dict) else DEC_ZERO

    total_to_date = previous + this_period + stored
    balance_to_finish = scheduled - total_to_date
    pct = (total_to_date / scheduled * DEC_HUNDRED) if scheduled > DEC_ZERO else DEC_ZERO
    retainage = retainage_percent * total_to_date / DEC_HUNDRED

    return {
        "line_number": line_number,
        "item_number": getattr(contract_line, "code", "") or str(line_number),
        "description": getattr(contract_line, "description", "") or "",
        "scheduled_value": _q(scheduled),
        "previous_value": _q(previous),
        "this_period_value": _q(this_period),
        "materials_stored": _q(stored),
        "total_completed_stored": _q(total_to_date),
        "percent_complete": _q(pct),
        "balance_to_finish": _q(balance_to_finish),
        "retainage": _q(retainage),
    }


def build_g703(
    contract_lines: list[Any],
    claim_lines_by_contract_line: dict[Any, Any],
    *,
    retainage_percent: Decimal,
) -> list[dict[str, Any]]:
    """Build the full G703 continuation sheet, one row per SoV line."""
    rows: list[dict[str, Any]] = []
    for idx, cl in enumerate(contract_lines, start=1):
        claim_line = claim_lines_by_contract_line.get(getattr(cl, "id", None))
        rows.append(
            build_g703_line(
                cl,
                claim_line,
                line_number=idx,
                retainage_percent=retainage_percent,
            )
        )
    return rows


def build_g702_summary(
    g703_rows: list[dict[str, Any]],
    *,
    original_contract_sum: Decimal,
    change_orders_net: Decimal = DEC_ZERO,
    previous_certificates_total: Decimal = DEC_ZERO,
) -> dict[str, Any]:
    """Roll the G703 rows into the G702 summary (the certificate face).

    Implements the standard G702 line numbering:

    * 1  original contract sum
    * 2  net change by change orders
    * 3  contract sum to date (= 1 + 2)
    * 4  total completed and stored to date (sum of G703 column G)
    * 5  retainage (sum of G703 column I)
    * 6  total earned less retainage (= 4 - 5)
    * 7  less previous certificates for payment
    * 8  current payment due (= 6 - 7, floored at zero)
    * 9  balance to finish including retainage (= 3 - 6)

    Pure roll-up over already-built G703 rows; all ``Decimal``.
    """
    contract_sum_to_date = original_contract_sum + change_orders_net
    total_completed_stored = sum((_dec(r["total_completed_stored"]) for r in g703_rows), DEC_ZERO)
    total_retainage = sum((_dec(r["retainage"]) for r in g703_rows), DEC_ZERO)
    total_earned_less_retainage = total_completed_stored - total_retainage
    current_payment_due = total_earned_less_retainage - previous_certificates_total
    if current_payment_due < DEC_ZERO:
        current_payment_due = DEC_ZERO
    balance_to_finish = contract_sum_to_date - total_earned_less_retainage

    return {
        "original_contract_sum": _q(original_contract_sum),
        "change_orders_net": _q(change_orders_net),
        "contract_sum_to_date": _q(contract_sum_to_date),
        "total_completed_stored": _q(total_completed_stored),
        "retainage": _q(total_retainage),
        "total_earned_less_retainage": _q(total_earned_less_retainage),
        "previous_certificates_total": _q(previous_certificates_total),
        "current_payment_due": _q(current_payment_due),
        "balance_to_finish": _q(balance_to_finish),
    }

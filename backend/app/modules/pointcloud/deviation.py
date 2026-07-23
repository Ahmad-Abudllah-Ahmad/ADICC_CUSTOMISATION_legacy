# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""Scan-vs-design deviation classification - pure, DB-free helpers.

The heavy point-to-mesh deviation math runs out of process and lands its
result on a :class:`~app.modules.pointcloud.models.ScanRegistration` row
(``rms_error`` in mm, ``out_of_tolerance_count``, ``coverage_pct``,
``hole_area``, ``deviation_map_uri``). This module does NOT recompute any of
that; it only classifies an already-computed registration into the traffic-
light severity the viewer overlay + legend paint, using the same USIBD LOA
tolerance the register-time validator uses (passed in by the service so this
module stays free of the ORM / DB import and is unit-testable on its own).

Severity bands (mirror the viewer's red/amber/green validation palette):

* ``unknown`` - no RMS measured yet (alignment not run). Grey.
* ``within``  - RMS at or below the scan's accuracy-tier tolerance AND no
                points beyond the deviation band. Green: the as-built matches
                the design within survey tolerance.
* ``warning`` - RMS within tolerance but some points fall outside the
                deviation band (local out-of-tolerance spots), OR coverage is
                too low to trust a clean verdict. Amber.
* ``over``    - RMS above the accuracy-tier tolerance. Red: the as-built
                deviates from the design beyond what the scan can certify.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

# Coverage below this percent makes even a clean RMS untrustworthy - the rest
# of the surface was filled by interpolation, so we downgrade "within" to a
# "warning" so the estimator never reads a green verdict off a sparse scan.
LOW_COVERAGE_PCT = Decimal("80")

# Stable, translatable severity codes (the API emits the code; the UI maps it
# to a colour + label). Not prose.
SEVERITY_UNKNOWN = "unknown"
SEVERITY_WITHIN = "within"
SEVERITY_WARNING = "warning"
SEVERITY_OVER = "over"

# Severity -> hex colour token the viewer legend paints. Kept here so the
# colour contract is shared by any consumer and unit-tested. These match the
# existing BIM viewer validation palette (red / amber / green / grey).
SEVERITY_COLOR: dict[str, str] = {
    SEVERITY_UNKNOWN: "#cbd5e1",  # slate-300
    SEVERITY_WITHIN: "#10b981",  # emerald-500
    SEVERITY_WARNING: "#f59e0b",  # amber-500
    SEVERITY_OVER: "#ef4444",  # red-500
}


def _as_decimal(value: Decimal | float | int | str | None) -> Decimal | None:
    """Coerce a numeric-ish value to a finite ``Decimal``, else ``None``.

    A non-finite or unparseable value reads as "not measured" rather than
    poisoning the comparison.
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return d if d.is_finite() else None


def classify_deviation(
    *,
    rms_mm: Decimal | float | int | str | None,
    tolerance_mm: Decimal | float | int | str | None,
    out_of_tolerance_count: int | None = 0,
    coverage_pct: Decimal | float | int | str | None = None,
) -> str:
    """Classify a registration's deviation into a traffic-light severity.

    ``tolerance_mm`` is the scan's accuracy-tier LOA bound (the service reads
    it from :func:`app.modules.pointcloud.validators.tier_tolerance_mm` and
    passes it here, so this function never needs the tolerance table or any DB
    import). Returns one of the ``SEVERITY_*`` codes; never raises.

    Decision order:
      1. No RMS measured -> ``unknown``.
      2. RMS above tolerance -> ``over`` (worst case wins).
      3. RMS within tolerance but out-of-tolerance points exist, or coverage
         is below :data:`LOW_COVERAGE_PCT` -> ``warning``.
      4. Otherwise -> ``within``.

    When the tolerance itself is unknown we can still flag the presence of
    out-of-tolerance points as a ``warning`` rather than claim ``within``.
    """
    rms = _as_decimal(rms_mm)
    if rms is None:
        return SEVERITY_UNKNOWN

    tol = _as_decimal(tolerance_mm)
    if tol is not None and rms > tol:
        return SEVERITY_OVER

    oot = int(out_of_tolerance_count or 0)
    cov = _as_decimal(coverage_pct)
    low_coverage = cov is not None and cov < LOW_COVERAGE_PCT
    if oot > 0 or low_coverage:
        return SEVERITY_WARNING

    # RMS measured and within tolerance (or tolerance unknown but no
    # out-of-tolerance points / coverage concern).
    return SEVERITY_WITHIN


def severity_color(severity: str) -> str:
    """Return the hex colour the viewer legend paints for a severity code.

    An unknown code falls back to the neutral grey so a future band never
    renders an empty swatch.
    """
    return SEVERITY_COLOR.get(severity, SEVERITY_COLOR[SEVERITY_UNKNOWN])


def worst_severity(severities: list[str]) -> str:
    """Reduce a list of per-registration severities to the model's headline.

    Order of seriousness: ``over`` > ``warning`` > ``within`` > ``unknown``.
    An empty list reads as ``unknown`` (no deviation data for the model).
    """
    rank = {
        SEVERITY_OVER: 3,
        SEVERITY_WARNING: 2,
        SEVERITY_WITHIN: 1,
        SEVERITY_UNKNOWN: 0,
    }
    worst = SEVERITY_UNKNOWN
    worst_rank = -1
    for sev in severities:
        r = rank.get(sev, 0)
        if r > worst_rank:
            worst_rank = r
            worst = sev
    return worst


__all__ = [
    "LOW_COVERAGE_PCT",
    "SEVERITY_COLOR",
    "SEVERITY_OVER",
    "SEVERITY_UNKNOWN",
    "SEVERITY_WARNING",
    "SEVERITY_WITHIN",
    "classify_deviation",
    "severity_color",
    "worst_severity",
]

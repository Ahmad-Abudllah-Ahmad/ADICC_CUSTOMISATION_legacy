# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""Tests for the pure scan-vs-design deviation classifier.

These exercise the DB-free verdict logic that drives the viewer's deviation
overlay + legend (``app.modules.pointcloud.deviation``). The heavy point-to-
mesh math is NOT here - this only classifies an already-computed registration
into a traffic-light severity given the scan's accuracy-tier tolerance. No ORM
/ DB import, so it runs on every deployment (including local py3.11 where the
service / router pull PostgreSQL at import).
"""

from __future__ import annotations

from decimal import Decimal

from app.modules.pointcloud.deviation import (
    SEVERITY_COLOR,
    SEVERITY_OVER,
    SEVERITY_UNKNOWN,
    SEVERITY_WARNING,
    SEVERITY_WITHIN,
    classify_deviation,
    severity_color,
    worst_severity,
)


def test_no_rms_is_unknown() -> None:
    # Alignment not run yet -> no verdict, paints neutral grey.
    assert classify_deviation(rms_mm=None, tolerance_mm=Decimal("6")) == SEVERITY_UNKNOWN


def test_rms_above_tolerance_is_over() -> None:
    # Survey tier bound is 6 mm; an 8 mm RMS deviates beyond what the scan
    # can certify -> red, regardless of coverage / out-of-tolerance count.
    assert classify_deviation(rms_mm=Decimal("8"), tolerance_mm=Decimal("6")) == SEVERITY_OVER


def test_rms_at_tolerance_bound_is_within() -> None:
    # Boundary is inclusive (<= bound passes), mirroring rms_within_tier.
    assert (
        classify_deviation(
            rms_mm=Decimal("6"),
            tolerance_mm=Decimal("6"),
            out_of_tolerance_count=0,
            coverage_pct=Decimal("99"),
        )
        == SEVERITY_WITHIN
    )


def test_within_rms_but_out_of_tolerance_points_is_warning() -> None:
    # RMS is fine overall, but local spots fall outside the band -> amber.
    assert (
        classify_deviation(
            rms_mm=Decimal("3"),
            tolerance_mm=Decimal("6"),
            out_of_tolerance_count=42,
            coverage_pct=Decimal("99"),
        )
        == SEVERITY_WARNING
    )


def test_low_coverage_downgrades_within_to_warning() -> None:
    # A clean RMS over a sparsely-covered surface is untrustworthy -> amber.
    assert (
        classify_deviation(
            rms_mm=Decimal("3"),
            tolerance_mm=Decimal("6"),
            out_of_tolerance_count=0,
            coverage_pct=Decimal("55"),
        )
        == SEVERITY_WARNING
    )


def test_high_coverage_clean_rms_is_within() -> None:
    assert (
        classify_deviation(
            rms_mm=Decimal("2.5"),
            tolerance_mm=Decimal("15"),
            out_of_tolerance_count=0,
            coverage_pct=Decimal("92"),
        )
        == SEVERITY_WITHIN
    )


def test_unknown_tolerance_still_flags_out_of_tolerance_points() -> None:
    # Tolerance not known, but the engine reported out-of-tolerance points:
    # never claim "within", flag a warning instead.
    assert (
        classify_deviation(
            rms_mm=Decimal("3"),
            tolerance_mm=None,
            out_of_tolerance_count=5,
        )
        == SEVERITY_WARNING
    )


def test_unknown_tolerance_clean_reads_within() -> None:
    assert classify_deviation(rms_mm=Decimal("3"), tolerance_mm=None) == SEVERITY_WITHIN


def test_non_finite_or_unparseable_values_never_crash() -> None:
    assert classify_deviation(rms_mm=float("nan"), tolerance_mm=Decimal("6")) == SEVERITY_UNKNOWN
    assert classify_deviation(rms_mm="oops", tolerance_mm=Decimal("6")) == SEVERITY_UNKNOWN
    # A non-finite coverage is treated as "not measured", not low coverage.
    assert (
        classify_deviation(
            rms_mm=Decimal("3"),
            tolerance_mm=Decimal("6"),
            coverage_pct=float("inf"),
        )
        == SEVERITY_WITHIN
    )


def test_float_and_string_inputs_coerce() -> None:
    # The service passes Decimals, but the helper accepts float / str too.
    assert classify_deviation(rms_mm=8.0, tolerance_mm=6.0) == SEVERITY_OVER
    assert classify_deviation(rms_mm="2", tolerance_mm="6") == SEVERITY_WITHIN


def test_severity_color_maps_each_band() -> None:
    assert severity_color(SEVERITY_OVER) == SEVERITY_COLOR[SEVERITY_OVER]
    assert severity_color(SEVERITY_WITHIN) == SEVERITY_COLOR[SEVERITY_WITHIN]
    assert severity_color(SEVERITY_WARNING) == SEVERITY_COLOR[SEVERITY_WARNING]
    assert severity_color(SEVERITY_UNKNOWN) == SEVERITY_COLOR[SEVERITY_UNKNOWN]
    # An unknown code falls back to neutral grey, never an empty swatch.
    assert severity_color("nonsense") == SEVERITY_COLOR[SEVERITY_UNKNOWN]


def test_worst_severity_reduces_to_most_serious() -> None:
    assert worst_severity([]) == SEVERITY_UNKNOWN
    assert worst_severity([SEVERITY_WITHIN, SEVERITY_UNKNOWN]) == SEVERITY_WITHIN
    assert worst_severity([SEVERITY_WITHIN, SEVERITY_WARNING, SEVERITY_UNKNOWN]) == SEVERITY_WARNING
    assert worst_severity([SEVERITY_WARNING, SEVERITY_OVER, SEVERITY_WITHIN]) == SEVERITY_OVER

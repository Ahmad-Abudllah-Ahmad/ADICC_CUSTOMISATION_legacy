# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""Tests for the lightweight point-cloud header sniff.

These exercise the cheap, DB-free preview logic added in the foundation wedge:
the header sniff (``app.modules.pointcloud.sniff``) and the pure header ->
column mapping the service uses to persist it. No laspy / pye57 needed - the
reader-present path is integration-tested elsewhere; here we prove the parts
that run on every deployment, including the ones with no reader installed.

Coverage
--------
* test_scan_header_coordinate_ranges - the header exposes per-axis [min, max]
  ranges, or None when it carried no bbox.
* test_finite_triplet_rejects_bad_input - NaN / short / non-numeric mins/maxs
  collapse to None so a poisoned bbox is never persisted.
* test_sniff_unsupported_format_is_unavailable - an unknown / proprietary
  format reports the reader as the limiter (mapped to an honest "pending"),
  never a crash.
* test_e57_prefix_needs_file_path - an E57 byte prefix correctly signals it
  needs a real file handle rather than guessing from a head slice.
* test_fields_from_header_ok - a populated header yields point_count, a
  units-tagged bbox and a status=ok scan_metadata with the scalar-field flags.
* test_fields_from_header_no_bbox - a header with no bbox still yields a
  status=ok summary and never invents extents or a CRS.
* test_fields_from_header_preserves_existing_crs - the CRS guess never
  overwrites a row that already carries an EPSG.
"""

from __future__ import annotations

import pytest

from app.modules.pointcloud import sniff
from app.modules.pointcloud.service import PointCloudService


def _header(**overrides: object) -> sniff.ScanHeader:
    base = {
        "point_count": 1_000_000,
        "bbox_min": (10.0, 20.0, 0.0),
        "bbox_max": (40.0, 60.0, 5.0),
        "units": "m",
        "has_rgb": True,
        "has_intensity": False,
        "has_classification": True,
        "extra": {"reader": "laspy", "point_format_id": 7, "extra_dimensions": []},
    }
    base.update(overrides)
    return sniff.ScanHeader(**base)  # type: ignore[arg-type]


def test_scan_header_coordinate_ranges() -> None:
    header = _header()
    assert header.coordinate_ranges == {
        "x": [10.0, 40.0],
        "y": [20.0, 60.0],
        "z": [0.0, 5.0],
    }
    no_bbox = _header(bbox_min=None, bbox_max=None)
    assert no_bbox.coordinate_ranges is None


def test_finite_triplet_rejects_bad_input() -> None:
    assert sniff._finite_triplet([1.0, 2.0, 3.0]) == (1.0, 2.0, 3.0)
    assert sniff._finite_triplet([1.0, 2.0]) is None  # too short
    assert sniff._finite_triplet([float("nan"), 2.0, 3.0]) is None  # non-finite
    assert sniff._finite_triplet(None) is None  # not a sequence


def test_sniff_unsupported_format_is_unavailable() -> None:
    # A proprietary / unknown format never crashes; it reports the reader as the
    # limiter so the service can record an honest "pending" state.
    with pytest.raises(sniff.HeaderSniffUnavailable):
        sniff.sniff_header_from_prefix(b"whatever", "rcp")


def test_e57_prefix_needs_file_path() -> None:
    # E57's reader needs random file access; a head prefix must not be guessed.
    with pytest.raises(sniff.HeaderSniffUnavailable) as exc:
        sniff.sniff_header_from_prefix(b"E57 head bytes", "e57")
    assert exc.value.fmt == "e57"


def test_fields_from_header_ok() -> None:
    svc = PointCloudService.__new__(PointCloudService)  # no DB / session needed
    fields = svc._fields_from_header(_header(), fmt="laz", had_crs=False)

    assert fields["point_count"] == 1_000_000
    assert fields["bbox_json"]["min"] == [10.0, 20.0, 0.0]
    assert fields["bbox_json"]["max"] == [40.0, 60.0, 5.0]
    assert fields["bbox_json"]["units"] == "m"

    meta = fields["scan_metadata"]
    assert meta["status"] == "ok"
    assert meta["format"] == "laz"
    assert meta["reader"] == "laspy"
    assert meta["scalar_fields"] == {"rgb": True, "intensity": False, "classification": True}
    assert meta["units"] == "m"
    assert meta["coordinate_ranges"]["z"] == [0.0, 5.0]
    # Header extras flow through (point format etc.) for the "what's in this scan" view.
    assert meta["point_format_id"] == 7


def test_fields_from_header_no_bbox() -> None:
    svc = PointCloudService.__new__(PointCloudService)
    header = _header(bbox_min=None, bbox_max=None, point_count=0)
    fields = svc._fields_from_header(header, fmt="ply", had_crs=False)

    # No bbox => no bbox_json, no crs guess, no invented point_count.
    assert "bbox_json" not in fields
    assert "crs_epsg" not in fields
    assert "point_count" not in fields
    assert fields["scan_metadata"]["status"] == "ok"
    assert fields["scan_metadata"]["coordinate_ranges"] is None


def test_fields_from_header_preserves_existing_crs() -> None:
    # A bbox that the CAD detector could resolve must NOT overwrite a row that
    # already carries a CRS (had_crs=True). The guess is additive only.
    svc = PointCloudService.__new__(PointCloudService)
    # A UTM-32N-shaped bbox (Germany) the detector recognises.
    header = _header(bbox_min=(500_000.0, 5_700_000.0, 0.0), bbox_max=(500_100.0, 5_700_100.0, 12.0))
    fields = svc._fields_from_header(header, fmt="laz", had_crs=True)
    assert "crs_epsg" not in fields
    assert "crs_confidence" not in fields
    # The bbox itself is still persisted.
    assert fields["bbox_json"]["min"][0] == 500_000.0

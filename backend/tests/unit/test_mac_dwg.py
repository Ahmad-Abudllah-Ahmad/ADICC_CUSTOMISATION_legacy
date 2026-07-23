"""Unit tests for macOS / LibreDWG DWG helpers."""

from __future__ import annotations

import json
from pathlib import Path

from app.modules.dwg_takeoff import mac_dwg


def test_parse_libredwg_geojson_geometry_only(tmp_path: Path) -> None:
    geo = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "SubClasses": "AcDbEntity : AcDbLine",
                    "Color": 3,
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[0.0, 0.0], [10.0, 0.0]],
                },
            },
            {
                "type": "Feature",
                "properties": {
                    "SubClasses": "AcDbEntity : AcDbLwPolyline",
                    "Color": 7,
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[0.0, 0.0], [10.0, 0.0], [10.0, 5.0]],
                },
            },
            {
                "type": "Feature",
                "properties": {
                    "SubClasses": "AcDbEntity : AcDbMText",
                    "Color": 1,
                    "Text": "Room A",
                },
                "geometry": {"type": "Point", "coordinates": [2.0, 3.0]},
            },
            {
                "type": "Feature",
                "properties": {
                    "SubClasses": "AcDbEntity : AcDbBlockReference",
                    "Color": 2,
                },
                "geometry": {"type": "Point", "coordinates": [5.0, 5.0]},
            },
            {
                "type": "Feature",
                "properties": {
                    "SubClasses": "AcDbEntity : AcDbPoint",
                    "Color": 7,
                },
                "geometry": {"type": "Point", "coordinates": [1.0, 1.0]},
            },
        ],
    }
    path = tmp_path / "sample.geo.json"
    path.write_text(json.dumps(geo), encoding="utf-8")

    result = mac_dwg.parse_libredwg_geojson(str(path), geometry_only=True)
    assert result["entity_count"] == 2
    assert {e["entity_type"] for e in result["entities"]} == {"LINE", "LWPOLYLINE"}
    assert result["extents"]["max_x"] >= 9.0
    assert result["extents"]["min_x"] <= 1.0
    assert any(l["name"] == "LINE" for l in result["layers"])
    svg = mac_dwg.entities_to_svg_thumbnail(result)
    assert svg.startswith("<svg")
    assert "line" in svg.lower() or "polyline" in svg.lower()

    with_text = mac_dwg.parse_libredwg_geojson(
        str(path), geometry_only=True, include_text=True
    )
    types = {e["entity_type"] for e in with_text["entities"]}
    assert "TEXT" in types or "MTEXT" in types
    assert "INSERT" not in types and "POINT" not in types
    text_ent = next(
        e for e in with_text["entities"] if e["entity_type"] in ("TEXT", "MTEXT")
    )
    assert text_ent["geometry_data"]["text"] == "Room A"
    assert text_ent["geometry_data"]["height"] > 1.0


def test_plain_mtext_strips_formatting() -> None:
    raw = r"{\fTimes New Roman|b0|i1|c0|p18;TEL. OFFICE\P041-730742}"
    assert mac_dwg.plain_mtext(raw) == "TEL. OFFICE\n041-730742"


def test_parse_libredwg_svg_paths() -> None:
    svg = """<?xml version="1.0"?>
<svg viewBox="0 0 100 100">
  <defs>
    <g id="symbol-1">
      <path d="M 0,0 L 10,0" style="stroke:black" />
      <path d="M 0,0 L 10,0 L 10,5" style="stroke:black" />
      <circle cx="50" cy="50" r="0.1" />
      <circle cx="20" cy="20" r="2.5" />
    </g>
  </defs>
</svg>
"""
    result = mac_dwg.parse_libredwg_svg(svg)
    types = {e["entity_type"] for e in result["entities"]}
    assert "LINE" in types
    assert "LWPOLYLINE" in types
    assert "CIRCLE" in types
    assert result["entity_count"] == 3  # tiny r=0.1 circle skipped


def test_offline_readiness_reports_libredwg(monkeypatch) -> None:
    from app.modules.dwg_takeoff.service import DwgTakeoffService

    monkeypatch.setattr(
        "app.modules.boq.cad_import.find_converter",
        lambda _ext: None,
    )
    monkeypatch.setattr(mac_dwg, "find_oda_file_converter", lambda: None)
    fake = Path("/opt/homebrew/bin/dwg2SVG")
    monkeypatch.setattr(mac_dwg, "find_libredwg_dwg2svg", lambda: fake)
    monkeypatch.setattr(mac_dwg, "find_libredwg_dwgread", lambda: None)

    payload = DwgTakeoffService.get_offline_readiness()
    assert payload["ready"] is True
    assert payload["converter_available"] is True
    assert payload["version"] == "dwg2SVG"
    assert "preview" in (payload.get("message") or "").lower()

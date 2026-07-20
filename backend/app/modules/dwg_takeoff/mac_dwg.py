# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""macOS / POSIX DWG helpers when DDC DwgExporter is unavailable.

Priority for reading ``.dwg`` without the Windows/Linux DDC binary:

1. **ODA File Converter** → DXF → existing ezdxf pipeline (full layer fidelity).
2. **LibreDWG** ``dwg2SVG`` (block-aware linework) merged with geometry-only
   ``dwgread -O GeoJSON`` (sheet frames / loose lines). CAD layer names are
   usually missing, so entities are grouped by type for the Layers panel.

LibreDWG is a best-effort preview: architectural DWGs with paperspace sheets,
xrefs, and complex blocks will not match AutoCAD 1:1. Prefer ODA or a native
DXF export for takeoff-accurate drawings.

These paths are also probed on Linux as a fallback when DDC is missing.
"""

from __future__ import annotations

import glob
import json
import logging
import math
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_EXTENT_ABS_MAX = 1.0e9
_PATH_D_RE = re.compile(r'([ML])\s*([-\d.eE+]+)\s*,\s*([-\d.eE+]+)')
_SVG_PATH_RE = re.compile(r'<path[^>]*\bd="([^"]+)"', re.IGNORECASE)
_SVG_CIRCLE_RE = re.compile(
    r'<circle[^>]*\bcx="([^"]+)"[^>]*\bcy="([^"]+)"[^>]*\br="([^"]+)"',
    re.IGNORECASE,
)
_SVG_POLYGON_RE = re.compile(r'<polygon[^>]*\bpoints="([^"]+)"', re.IGNORECASE)

# ACI → hex (subset used by dxf_processor)
_ACI_HEX: dict[int, str] = {
    1: "#ff0000",
    2: "#ffff00",
    3: "#00ff00",
    4: "#00ffff",
    5: "#0000ff",
    6: "#ff00ff",
    7: "#ffffff",
    8: "#808080",
    9: "#c0c0c0",
}

_SUBCLASS_TO_ENTITY: dict[str, str] = {
    "acdbline": "LINE",
    "acdblwpolyline": "LWPOLYLINE",
    "acdbpolyline": "POLYLINE",
    "acdbcircle": "CIRCLE",
    "acdbarc": "ARC",
    "acdbellipse": "ELLIPSE",
    "acdbpoint": "POINT",
    "acdbtext": "TEXT",
    "acdbmtext": "MTEXT",
    "acdbblockreference": "INSERT",
    "acdbhatch": "HATCH",
    "acdbspline": "SPLINE",
    "acdbdimension": "DIMENSION",
}


def find_oda_file_converter() -> Path | None:
    """Locate the ODA File Converter CLI binary if installed."""
    env = os.environ.get("OE_ODA_FILE_CONVERTER") or os.environ.get("ODA_FILE_CONVERTER")
    if env:
        p = Path(env)
        if p.is_file() and os.access(p, os.X_OK):
            return p

    which = shutil.which("ODAFileConverter") or shutil.which("TeighaFileConverter")
    if which:
        return Path(which)

    patterns = [
        "/Applications/ODA File Converter*.app/Contents/MacOS/ODAFileConverter",
        "/Applications/ODAFileConverter*.app/Contents/MacOS/ODAFileConverter",
        "/Applications/Teigha File Converter*.app/Contents/MacOS/TeighaFileConverter",
        str(Path.home() / "Applications" / "ODA File Converter*.app" / "Contents" / "MacOS" / "ODAFileConverter"),
        "/usr/bin/ODAFileConverter",
        "/usr/local/bin/ODAFileConverter",
        "/opt/homebrew/bin/ODAFileConverter",
    ]
    for pattern in patterns:
        for match in glob.glob(pattern):
            cand = Path(match)
            if cand.is_file() and os.access(cand, os.X_OK):
                return cand
    return None


def find_libredwg_dwgread() -> Path | None:
    """Locate LibreDWG ``dwgread`` (Homebrew: ``brew install libredwg``)."""
    env = os.environ.get("OE_DWGREAD") or os.environ.get("DWGREAD")
    if env:
        p = Path(env)
        if p.is_file() and os.access(p, os.X_OK):
            return p
    which = shutil.which("dwgread")
    if which:
        return Path(which)
    for cand in (
        Path("/opt/homebrew/bin/dwgread"),
        Path("/usr/local/bin/dwgread"),
        Path("/usr/bin/dwgread"),
    ):
        if cand.is_file() and os.access(cand, os.X_OK):
            return cand
    return None


def find_libredwg_dwg2dxf() -> Path | None:
    """Locate LibreDWG ``dwg2dxf`` (often produces DXF that ezdxf cannot load)."""
    which = shutil.which("dwg2dxf")
    if which:
        return Path(which)
    for cand in (
        Path("/opt/homebrew/bin/dwg2dxf"),
        Path("/usr/local/bin/dwg2dxf"),
        Path("/usr/bin/dwg2dxf"),
    ):
        if cand.is_file() and os.access(cand, os.X_OK):
            return cand
    return None


def find_libredwg_dwg2svg() -> Path | None:
    """Locate LibreDWG ``dwg2SVG`` (best LibreDWG geometry; expands many blocks)."""
    env = os.environ.get("OE_DWG2SVG") or os.environ.get("DWG2SVG")
    if env:
        p = Path(env)
        if p.is_file() and os.access(p, os.X_OK):
            return p
    which = shutil.which("dwg2SVG") or shutil.which("dwg2svg")
    if which:
        return Path(which)
    for cand in (
        Path("/opt/homebrew/bin/dwg2SVG"),
        Path("/opt/homebrew/bin/dwg2svg"),
        Path("/usr/local/bin/dwg2SVG"),
        Path("/usr/local/bin/dwg2svg"),
        Path("/usr/bin/dwg2SVG"),
        Path("/usr/bin/dwg2svg"),
    ):
        if cand.is_file() and os.access(cand, os.X_OK):
            return cand
    return None


def any_mac_dwg_backend() -> Path | None:
    """Return the preferred non-DDC DWG tool path, or None."""
    return (
        find_oda_file_converter()
        or find_libredwg_dwg2svg()
        or find_libredwg_dwgread()
    )


def oda_download_url() -> str:
    return "https://www.opendesign.com/guestfiles/oda_file_converter"


def convert_dwg_to_dxf_via_oda(
    dwg_path: str,
    *,
    timeout_s: int = 300,
    version: str = "ACAD2018",
) -> str:
    """Convert a single DWG to DXF using ODA File Converter.

    Returns the absolute path to the produced ``.dxf`` file.
    Raises ``RuntimeError`` on failure.
    """
    oda = find_oda_file_converter()
    if oda is None:
        raise RuntimeError("ODA File Converter is not installed")

    src = Path(dwg_path).resolve()
    if not src.is_file():
        raise RuntimeError(f"DWG file not found: {dwg_path}")

    out_dir = Path(tempfile.mkdtemp(prefix="oe_oda_"))
    # ODA requires separate input/output directories and a filter glob.
    in_dir = out_dir / "in"
    dxf_dir = out_dir / "out"
    in_dir.mkdir()
    dxf_dir.mkdir()
    # Copy (don't symlink): macOS ODA often skips symlinked inputs.
    # Keep a lowercase .dwg suffix — the default "*.DWG" filter misses *.dwg.
    linked = in_dir / (src.stem + ".dwg")
    shutil.copy2(src, linked)

    # CLI: InputFolder OutputFolder OutputVersion OutputFileType Recurse Audit Filter
    # OutputFileType: DWG | DXF | DXB
    # Try lowercase filter first (macOS), then uppercase for Windows-built packs.
    last_err = ""
    for file_filter in ("*.dwg", "*.DWG", "*.*"):
        args = [
            str(oda),
            str(in_dir),
            str(dxf_dir),
            version,
            "DXF",
            "0",
            "1",
            file_filter,
        ]
        logger.info("ODA convert: %s", " ".join(args))
        proc = subprocess.run(
            args,
            capture_output=True,
            timeout=timeout_s,
            check=False,
        )
        candidates = list(dxf_dir.glob("*.dxf")) + list(dxf_dir.glob("*.DXF"))
        if candidates:
            break
        err = (proc.stderr or b"").decode("utf-8", errors="replace")[:400]
        out = (proc.stdout or b"").decode("utf-8", errors="replace")[:200]
        last_err = (err or out or f"exit {proc.returncode}").strip()
    else:
        raise RuntimeError(
            f"ODA File Converter produced no DXF. {last_err}".strip()
        )
    candidates = list(dxf_dir.glob("*.dxf")) + list(dxf_dir.glob("*.DXF"))

    # Prefer matching stem
    preferred = dxf_dir / f"{src.stem}.dxf"
    dxf_path = preferred if preferred.exists() else candidates[0]
    if dxf_path.stat().st_size < 64:
        raise RuntimeError("ODA File Converter produced an empty DXF")
    return str(dxf_path.resolve())


def _entity_type_from_subclass(subclass: str) -> str:
    low = (subclass or "").lower()
    # "AcDbEntity : AcDbLwPolyline" → last token
    token = low.split(":")[-1].strip()
    return _SUBCLASS_TO_ENTITY.get(token, "LINE" if "line" in token else "POINT")


def _aci_to_hex(aci: int) -> str:
    if aci in (0, 256):
        return "#ffffff"
    return _ACI_HEX.get(aci, "#ffffff")


def _sane_xy(x: float, y: float) -> bool:
    return (
        math.isfinite(x)
        and math.isfinite(y)
        and abs(x) <= _EXTENT_ABS_MAX
        and abs(y) <= _EXTENT_ABS_MAX
    )


def _coords_to_points(coords: Any) -> list[dict[str, float]]:
    points: list[dict[str, float]] = []
    if not isinstance(coords, list):
        return points
    for c in coords:
        if isinstance(c, (list, tuple)) and len(c) >= 2:
            # Polygon rings are nested one level deeper
            if isinstance(c[0], (list, tuple)):
                for inner in c:
                    if isinstance(inner, (list, tuple)) and len(inner) >= 2:
                        try:
                            points.append({"x": float(inner[0]), "y": float(inner[1])})
                        except (TypeError, ValueError):
                            continue
            else:
                try:
                    points.append({"x": float(c[0]), "y": float(c[1])})
                except (TypeError, ValueError):
                    continue
    return points


def _path_d_to_points(d: str) -> list[dict[str, float]]:
    points: list[dict[str, float]] = []
    for match in _PATH_D_RE.finditer(d or ""):
        try:
            x, y = float(match.group(2)), float(match.group(3))
        except (TypeError, ValueError):
            continue
        if _sane_xy(x, y):
            points.append({"x": x, "y": y})
    return points


def plain_mtext(text: str) -> str:
    """Strip AutoCAD MTEXT formatting codes to plain readable text."""
    t = str(text or "")
    t = t.replace("\\P", "\n").replace("\\p", "\n")
    # Font / stack / color / alignment escapes: \fArial|...;  \A1;  \W0.6; …
    t = re.sub(r"\\[A-Za-z][^;\\]*;", "", t)
    t = re.sub(r"[{}]", "", t)
    t = t.replace("\\~", " ").replace("\\\\", "\\")
    # Drop leftover control crumbs
    t = re.sub(r"\\[A-Za-z]", "", t)
    lines = [ln.strip() for ln in t.splitlines()]
    return "\n".join(ln for ln in lines if ln).strip()


def _entity_sample_points(
    ent: dict[str, Any],
    *,
    include_text: bool = False,
) -> list[tuple[float, float]]:
    etype = ent.get("entity_type")
    if etype in ("POINT", "INSERT"):
        return []
    gd = ent.get("geometry_data") or {}
    pts: list[dict[str, float]] = []
    if etype in ("TEXT", "MTEXT"):
        if not include_text:
            return []
        ins = gd.get("insert") or gd.get("insertion_point")
        if isinstance(ins, dict):
            pts = [ins]
    elif "start" in gd and "end" in gd:
        pts = [gd["start"], gd["end"]]
    elif "points" in gd:
        pts = list(gd.get("points") or [])
    elif "center" in gd:
        c = gd["center"]
        r = float(gd.get("radius") or 0.0)
        pts = [
            {"x": c["x"] - r, "y": c["y"] - r},
            {"x": c["x"] + r, "y": c["y"] + r},
        ]
    out: list[tuple[float, float]] = []
    for p in pts:
        try:
            x, y = float(p["x"]), float(p["y"])
        except (TypeError, ValueError, KeyError):
            continue
        if _sane_xy(x, y):
            out.append((x, y))
    return out


def _robust_extents(
    entities: list[dict[str, Any]],
    *,
    low: float = 0.02,
    high: float = 0.98,
) -> dict[str, float]:
    """Fit extents to the densest linework cluster (not sparse outliers).

    Architectural DWGs often scatter sheets across a huge model space. A plain
    min/max (or even global percentiles) zooms out so far that floor plans look
    like dust. Prefer the 2D histogram cell with the most segment length, then
    grow to a compact neighborhood that still covers most of that cluster.
    """
    samples: list[tuple[float, float, float]] = []  # cx, cy, length
    xs: list[float] = []
    ys: list[float] = []
    for ent in entities:
        pts = _entity_sample_points(ent)
        if len(pts) < 2:
            continue
        length = 0.0
        for i in range(len(pts) - 1):
            length += math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
        if length <= 0:
            continue
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        samples.append((cx, cy, length))
        for x, y in pts:
            xs.append(x)
            ys.append(y)
    if not xs:
        return {"min_x": 0.0, "min_y": 0.0, "max_x": 1000.0, "max_y": 1000.0}

    xs.sort()
    ys.sort()

    def _pct(vals: list[float], p: float) -> float:
        return vals[int((len(vals) - 1) * p)]

    # Global percentile box as a fallback / outer clamp.
    g_min_x, g_max_x = _pct(xs, low), _pct(xs, high)
    g_min_y, g_max_y = _pct(ys, low), _pct(ys, high)

    # Tiny / simple drawings: skip clustering (grid math is unstable).
    if len(samples) < 80 or (g_max_x - g_min_x) < 50 or (g_max_y - g_min_y) < 50:
        return {
            "min_x": float(g_min_x),
            "min_y": float(g_min_y),
            "max_x": float(g_max_x if g_max_x > g_min_x else g_min_x + 1.0),
            "max_y": float(g_max_y if g_max_y > g_min_y else g_min_y + 1.0),
        }

    # Density grid over the global percentile box.
    nx = ny = 24
    span_x = max(g_max_x - g_min_x, 1.0)
    span_y = max(g_max_y - g_min_y, 1.0)
    grid = [[0.0 for _ in range(nx)] for _ in range(ny)]
    for cx, cy, length in samples:
        if not (g_min_x <= cx <= g_max_x and g_min_y <= cy <= g_max_y):
            continue
        ix = min(nx - 1, max(0, int((cx - g_min_x) / span_x * nx)))
        iy = min(ny - 1, max(0, int((cy - g_min_y) / span_y * ny)))
        grid[iy][ix] += length

    # Prefer the densest *horizontal band* (sheet strip). A single hot cell
    # near the origin (logos / title junk) otherwise wins and zooms there.
    row_totals = [sum(grid[iy]) for iy in range(ny)]
    best_row = max(range(ny), key=lambda iy: row_totals[iy])
    y0 = y1 = best_row
    band_len = row_totals[best_row]
    total = sum(row_totals) or 1.0
    # Cover most of the sheet strip (floor plans + elevations). Stop early
    # only when neighboring rows are empty relative to the peak row.
    peak = max(row_totals[best_row], 1.0)
    while band_len / total < 0.72:
        gain_down = row_totals[y0 - 1] if y0 > 0 else -1.0
        gain_up = row_totals[y1 + 1] if y1 < ny - 1 else -1.0
        if gain_down < 0 and gain_up < 0:
            break
        # Keep absorbing adjacent sheet rows that still carry real content.
        if max(gain_down, gain_up) < peak * 0.04 and band_len / total >= 0.50:
            break
        if gain_down >= gain_up:
            y0 -= 1
            band_len += max(gain_down, 0.0)
        else:
            y1 += 1
            band_len += max(gain_up, 0.0)

    col_totals = [sum(grid[iy][ix] for iy in range(y0, y1 + 1)) for ix in range(nx)]
    best_col = max(range(nx), key=lambda ix: col_totals[ix])
    x0 = x1 = best_col
    strip_len = col_totals[best_col]
    strip_total = sum(col_totals) or 1.0
    peak_c = max(col_totals[best_col], 1.0)
    while strip_len / strip_total < 0.85:
        gain_l = col_totals[x0 - 1] if x0 > 0 else -1.0
        gain_r = col_totals[x1 + 1] if x1 < nx - 1 else -1.0
        if gain_l < 0 and gain_r < 0:
            break
        if max(gain_l, gain_r) < peak_c * 0.03 and strip_len / strip_total >= 0.60:
            break
        if gain_l >= gain_r:
            x0 -= 1
            strip_len += max(gain_l, 0.0)
        else:
            x1 += 1
            strip_len += max(gain_r, 0.0)

    # Pad so title blocks / elevation frames are not clipped.
    x0 = max(0, x0 - 2)
    y0 = max(0, y0 - 2)
    x1 = min(nx - 1, x1 + 2)
    y1 = min(ny - 1, y1 + 2)

    min_x = g_min_x + (x0 / nx) * span_x
    max_x = g_min_x + ((x1 + 1) / nx) * span_x
    min_y = g_min_y + (y0 / ny) * span_y
    max_y = g_min_y + ((y1 + 1) / ny) * span_y
    if max_x <= min_x:
        max_x = min_x + 1.0
    if max_y <= min_y:
        max_y = min_y + 1.0
    return {
        "min_x": float(min_x),
        "min_y": float(min_y),
        "max_x": float(max_x),
        "max_y": float(max_y),
    }


def entity_intersects_extents(
    ent: dict[str, Any],
    extents: dict[str, float],
    *,
    pad_ratio: float = 0.12,
) -> bool:
    """True when any sample point lies inside a padded extents box."""
    min_x = float(extents["min_x"])
    min_y = float(extents["min_y"])
    max_x = float(extents["max_x"])
    max_y = float(extents["max_y"])
    pad_x = max((max_x - min_x) * pad_ratio, 1.0)
    pad_y = max((max_y - min_y) * pad_ratio, 1.0)
    x0, x1 = min_x - pad_x, max_x + pad_x
    y0, y1 = min_y - pad_y, max_y + pad_y
    for x, y in _entity_sample_points(ent, include_text=True):
        if x0 <= x <= x1 and y0 <= y <= y1:
            return True
    return False


def _assign_text_heights(entities: list[dict[str, Any]], extents: dict[str, float]) -> None:
    """LibreDWG GeoJSON omits text height — estimate from sheet span."""
    span = max(
        float(extents["max_x"]) - float(extents["min_x"]),
        float(extents["max_y"]) - float(extents["min_y"]),
        1.0,
    )
    base = max(span / 400.0, 20.0)
    for ent in entities:
        if ent.get("entity_type") not in ("TEXT", "MTEXT"):
            continue
        gd = ent.setdefault("geometry_data", {})
        text = str(gd.get("text") or "")
        height = base
        if len(text) <= 2:
            height = base * 0.55
        elif len(text) <= 6:
            height = base * 0.75
        elif len(text) > 48 or "\n" in text:
            height = base * 1.35
        gd["height"] = float(height)


def _finalize_entities(
    entities: list[dict[str, Any]],
    *,
    source: str,
) -> dict[str, Any]:
    extents = _robust_extents(entities)
    # Drop far outliers so the viewer fit (and stored JSON) stay on the real sheets.
    clipped = [e for e in entities if entity_intersects_extents(e, extents)]
    if len(clipped) >= max(50, int(len(entities) * 0.15)):
        entities = clipped
        extents = _robust_extents(entities)

    _assign_text_heights(entities, extents)

    layer_counts: dict[str, int] = {}
    for ent in entities:
        layer = str(ent.get("layer") or "0")
        layer_counts[layer] = layer_counts.get(layer, 0) + 1

    from app.modules.dwg_takeoff.ddc_dwg_parser import infer_units_from_extents

    units = infer_units_from_extents(extents) or "unitless"
    layers = [
        {
            "name": name,
            "color": "#ffffff",
            "visible": True,
            "entity_count": count,
        }
        for name, count in sorted(layer_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    return {
        "layers": layers,
        "entities": entities,
        "extents": extents,
        "units": units,
        "entity_count": len(entities),
        "skipped_count": 0,
        "layouts": ["Model"],
        "source": source,
    }


def parse_libredwg_geojson(
    geojson_path: str,
    *,
    geometry_only: bool = True,
    include_text: bool = False,
) -> dict[str, Any]:
    """Parse LibreDWG GeoJSON into the same shape as ``parse_dxf`` / DDC parser.

    POINT / INSERT are always skipped when ``geometry_only`` is True (block
    inserts are markers only — geometry comes from ``dwg2SVG``). TEXT / MTEXT
    are included when ``include_text`` is True (formatting stripped; height
    estimated later from sheet extents).
    """
    with open(geojson_path, encoding="utf-8", errors="replace") as fh:
        data = json.load(fh)

    features = data.get("features") or []
    entities: list[dict[str, Any]] = []

    for ft in features:
        props = ft.get("properties") or {}
        geom = ft.get("geometry") or {}
        if not geom or not geom.get("type"):
            continue
        etype = _entity_type_from_subclass(str(props.get("SubClasses") or ""))
        if geometry_only and etype in ("POINT", "INSERT"):
            continue
        if geometry_only and etype in ("TEXT", "MTEXT") and not include_text:
            continue
        # LibreDWG GeoJSON rarely includes CAD layer names; group by entity
        # type so the Layers panel can still toggle geometry classes.
        layer = str(props.get("layer") or props.get("Layer") or etype or "0")
        try:
            color = _aci_to_hex(int(props.get("Color", 7)))
        except (TypeError, ValueError):
            color = "#ffffff"

        gtype = geom.get("type")
        coords = geom.get("coordinates")
        geometry_data: dict[str, Any] = {}

        if gtype == "LineString":
            pts = [p for p in _coords_to_points(coords) if _sane_xy(p["x"], p["y"])]
            if len(pts) < 2:
                continue
            if etype == "LINE" and len(pts) == 2:
                geometry_data = {"start": pts[0], "end": pts[1]}
            else:
                etype = "LWPOLYLINE" if etype == "LINE" else etype
                geometry_data = {"points": pts, "closed": False}
        elif gtype == "Polygon":
            pts = [p for p in _coords_to_points(coords) if _sane_xy(p["x"], p["y"])]
            if len(pts) < 2:
                continue
            etype = "LWPOLYLINE"
            geometry_data = {"points": pts, "closed": True}
        elif gtype == "Point":
            if not isinstance(coords, (list, tuple)) or len(coords) < 2:
                continue
            try:
                x, y = float(coords[0]), float(coords[1])
            except (TypeError, ValueError):
                continue
            if not _sane_xy(x, y):
                continue
            raw_text = props.get("Text")
            if etype in ("TEXT", "MTEXT") or (include_text and raw_text):
                plain = plain_mtext(str(raw_text or ""))
                if not plain or plain in {";", ".", "-", "_"}:
                    continue
                etype = "MTEXT" if "mtext" in str(props.get("SubClasses") or "").lower() else "TEXT"
                layer = "TEXT"
                geometry_data = {
                    "insert": {"x": x, "y": y},
                    "text": plain,
                    "height": 1.0,  # replaced in _finalize_entities
                    "rotation": 0.0,
                    "style": "Standard",
                    "font": "",
                }
            elif not geometry_only and etype == "CIRCLE":
                geometry_data = {"center": {"x": x, "y": y}, "radius": 0.5}
            elif not geometry_only:
                continue
            else:
                continue
        else:
            continue

        entities.append(
            {
                "entity_type": etype,
                "layer": layer,
                "color": color,
                "geometry_data": geometry_data,
                "layout": "Model",
            }
        )

    return _finalize_entities(entities, source="libredwg_geojson")


def parse_libredwg_svg(svg_text: str) -> dict[str, Any]:
    """Parse LibreDWG ``dwg2SVG`` output into takeoff line/polyline entities.

    LibreDWG often nests all geometry under ``<defs>`` with world coordinates
    already baked into ``<path d="...">`` values, so we collect every path /
    polygon / meaningful circle in the file.
    """
    entities: list[dict[str, Any]] = []

    for d in _SVG_PATH_RE.findall(svg_text):
        pts = _path_d_to_points(d)
        if len(pts) < 2:
            continue
        if len(pts) == 2:
            entities.append(
                {
                    "entity_type": "LINE",
                    "layer": "LINE",
                    "color": "#ffffff",
                    "geometry_data": {"start": pts[0], "end": pts[1]},
                    "layout": "Model",
                }
            )
        else:
            entities.append(
                {
                    "entity_type": "LWPOLYLINE",
                    "layer": "LWPOLYLINE",
                    "color": "#ffffff",
                    "geometry_data": {"points": pts, "closed": False},
                    "layout": "Model",
                }
            )

    for points_attr in _SVG_POLYGON_RE.findall(svg_text):
        pts: list[dict[str, float]] = []
        raw_nums = re.findall(r"[-\d.eE+]+", points_attr)
        for i in range(0, len(raw_nums) - 1, 2):
            try:
                x, y = float(raw_nums[i]), float(raw_nums[i + 1])
            except (TypeError, ValueError):
                continue
            if _sane_xy(x, y):
                pts.append({"x": x, "y": y})
        if len(pts) >= 2:
            entities.append(
                {
                    "entity_type": "LWPOLYLINE",
                    "layer": "LWPOLYLINE",
                    "color": "#ffffff",
                    "geometry_data": {"points": pts, "closed": True},
                    "layout": "Model",
                }
            )

    for match in _SVG_CIRCLE_RE.finditer(svg_text):
        try:
            cx, cy, r = float(match.group(1)), float(match.group(2)), float(match.group(3))
        except (TypeError, ValueError):
            continue
        # dwg2SVG emits r≈0.1 for POINT markers — skip those.
        if r < 0.5 or not _sane_xy(cx, cy) or not math.isfinite(r):
            continue
        entities.append(
            {
                "entity_type": "CIRCLE",
                "layer": "CIRCLE",
                "color": "#ffffff",
                "geometry_data": {"center": {"x": cx, "y": cy}, "radius": r},
                "layout": "Model",
            }
        )

    return _finalize_entities(entities, source="libredwg_svg")


def _merge_entity_lists(
    primary: list[dict[str, Any]],
    extra: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Append ``extra`` linework that does not duplicate short primary segments."""
    seen: set[tuple[float, float, float, float]] = set()

    def _key(ent: dict[str, Any]) -> tuple[float, float, float, float] | None:
        gd = ent.get("geometry_data") or {}
        if "start" in gd and "end" in gd:
            s, e = gd["start"], gd["end"]
            return (
                round(float(s["x"]), 2),
                round(float(s["y"]), 2),
                round(float(e["x"]), 2),
                round(float(e["y"]), 2),
            )
        pts = gd.get("points") or []
        if len(pts) >= 2:
            s, e = pts[0], pts[-1]
            return (
                round(float(s["x"]), 2),
                round(float(s["y"]), 2),
                round(float(e["x"]), 2),
                round(float(e["y"]), 2),
            )
        return None

    merged = list(primary)
    for ent in primary:
        k = _key(ent)
        if k is not None:
            seen.add(k)
    for ent in extra:
        if ent.get("entity_type") not in (
            "LINE",
            "LWPOLYLINE",
            "CIRCLE",
            "ARC",
            "TEXT",
            "MTEXT",
        ):
            continue
        k = _key(ent)
        if k is not None and k in seen:
            continue
        if k is not None:
            seen.add(k)
        merged.append(ent)
    return merged


def convert_dwg_via_libredwg_geojson(
    dwg_path: str,
    *,
    timeout_s: int = 300,
    geometry_only: bool = True,
    include_text: bool = True,
) -> dict[str, Any]:
    """Run ``dwgread -O GeoJSON`` and parse into takeoff entities."""
    dwgread = find_libredwg_dwgread()
    if dwgread is None:
        raise RuntimeError(
            "LibreDWG dwgread not found. Install with: brew install libredwg"
        )

    src = Path(dwg_path).resolve()
    if not src.is_file():
        raise RuntimeError(f"DWG file not found: {dwg_path}")

    out_dir = Path(tempfile.mkdtemp(prefix="oe_libredwg_"))
    geo_path = out_dir / f"{src.stem}.geo.json"
    args = [str(dwgread), "-O", "GeoJSON", "-o", str(geo_path), str(src)]
    logger.info("LibreDWG convert: %s", " ".join(args))
    proc = subprocess.run(
        args,
        capture_output=True,
        timeout=timeout_s,
        check=False,
    )
    if not geo_path.is_file() or geo_path.stat().st_size < 64:
        err = (proc.stderr or b"").decode("utf-8", errors="replace")[:400]
        raise RuntimeError(
            f"LibreDWG produced no GeoJSON (exit {proc.returncode}): {err}".strip()
        )

    result = parse_libredwg_geojson(
        str(geo_path),
        geometry_only=geometry_only,
        include_text=include_text,
    )
    if result["entity_count"] == 0:
        raise RuntimeError("LibreDWG GeoJSON contained no drawable entities")
    return result


def convert_dwg_via_libredwg(
    dwg_path: str,
    *,
    timeout_s: int = 300,
) -> dict[str, Any]:
    """Best-effort LibreDWG conversion: ``dwg2SVG`` + GeoJSON (lines + text).

    ``dwg2SVG`` expands many block references into real linework (what GeoJSON
    alone cannot do). GeoJSON contributes sheet linework and TEXT/MTEXT labels
    (``dwg2SVG`` ignores MTEXT). POINT/INSERT markers are dropped.
    """
    src = Path(dwg_path).resolve()
    if not src.is_file():
        raise RuntimeError(f"DWG file not found: {dwg_path}")

    svg_entities: list[dict[str, Any]] = []
    geo_entities: list[dict[str, Any]] = []
    source = "libredwg"

    dwg2svg = find_libredwg_dwg2svg()
    if dwg2svg is not None:
        try:
            # dwg2SVG writes SVG to stdout; --mspace prefers model space.
            args = [str(dwg2svg), "--mspace", str(src)]
            logger.info("LibreDWG SVG convert: %s", " ".join(args))
            proc = subprocess.run(
                args,
                capture_output=True,
                timeout=timeout_s,
                check=False,
            )
            svg_text = (proc.stdout or b"").decode("utf-8", errors="replace")
            if len(svg_text) > 64 and "<path" in svg_text:
                parsed = parse_libredwg_svg(svg_text)
                svg_entities = list(parsed.get("entities") or [])
                source = "libredwg_svg"
                logger.info(
                    "LibreDWG dwg2SVG produced %d entities for %s",
                    len(svg_entities),
                    src.name,
                )
            else:
                err = (proc.stderr or b"").decode("utf-8", errors="replace")[:300]
                logger.warning(
                    "LibreDWG dwg2SVG produced little/no SVG (exit %s): %s",
                    proc.returncode,
                    err,
                )
        except Exception as exc:  # noqa: BLE001 - fall through to GeoJSON
            logger.warning("LibreDWG dwg2SVG failed for %s: %s", src.name, exc)

    if find_libredwg_dwgread() is not None:
        try:
            geo = convert_dwg_via_libredwg_geojson(
                str(src),
                timeout_s=timeout_s,
                geometry_only=True,
                include_text=True,
            )
            geo_entities = list(geo.get("entities") or [])
            if not svg_entities:
                source = "libredwg_geojson"
        except Exception as exc:  # noqa: BLE001
            if not svg_entities:
                raise
            logger.warning("LibreDWG GeoJSON merge skipped for %s: %s", src.name, exc)

    if svg_entities and geo_entities:
        entities = _merge_entity_lists(svg_entities, geo_entities)
        source = "libredwg_svg+geojson"
    elif svg_entities:
        entities = svg_entities
    else:
        entities = geo_entities

    if not entities:
        raise RuntimeError(
            "LibreDWG produced no drawable geometry. Install ODA File Converter "
            f"from {oda_download_url()} or export DXF from your CAD app."
        )

    result = _finalize_entities(entities, source=source)
    return result


def entities_to_svg_thumbnail(result: dict[str, Any], *, max_entities: int = 4000) -> str:
    """Build a lightweight SVG preview from parsed entities (no ezdxf needed)."""
    extents = result.get("extents") or {}
    min_x = float(extents.get("min_x", 0))
    min_y = float(extents.get("min_y", 0))
    max_x = float(extents.get("max_x", 1000))
    max_y = float(extents.get("max_y", 1000))
    width = max(max_x - min_x, 1.0)
    height = max(max_y - min_y, 1.0)
    pad = 0.02 * max(width, height)
    stroke = max(width, height) / 4000.0
    vb = f"{min_x - pad} {-(max_y + pad)} {width + 2 * pad} {height + 2 * pad}"

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" '
        f'width="800" height="600" style="background:#1a1a1a">',
        '<g transform="scale(1,-1)">',
    ]
    count = 0
    for ent in result.get("entities") or []:
        if count >= max_entities:
            break
        if ent.get("entity_type") in ("POINT", "INSERT", "TEXT", "MTEXT"):
            continue
        gd = ent.get("geometry_data") or {}
        color = ent.get("color") or "#cccccc"
        if "start" in gd and "end" in gd:
            s, e = gd["start"], gd["end"]
            parts.append(
                f'<line x1="{s["x"]}" y1="{s["y"]}" x2="{e["x"]}" y2="{e["y"]}" '
                f'stroke="{color}" stroke-width="{stroke}" />'
            )
            count += 1
        elif "points" in gd and gd["points"]:
            pts = " ".join(f'{p["x"]},{p["y"]}' for p in gd["points"])
            close = " Z" if gd.get("closed") else ""
            parts.append(
                f'<polyline points="{pts}{close}" fill="none" stroke="{color}" '
                f'stroke-width="{stroke}" />'
            )
            count += 1
        elif "center" in gd and gd.get("radius", 0):
            c = gd["center"]
            r = float(gd["radius"])
            if r > 0 and math.isfinite(r):
                parts.append(
                    f'<circle cx="{c["x"]}" cy="{c["y"]}" r="{r}" '
                    f'fill="none" stroke="{color}" '
                    f'stroke-width="{stroke}" />'
                )
                count += 1
    parts.append("</g></svg>")
    return "\n".join(parts)

# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""DWG/DXF file processor - ezdxf wrapper.

Parses DXF files to extract layers, entities, extents, and units.
Generates SVG thumbnail previews and calculates entity measurements.

ezdxf is an optional dependency - functions degrade gracefully with a
clear error message if it is not installed.
"""

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)

try:
    import ezdxf
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing import svg as ezdxf_svg

    HAS_EZDXF = True
except ImportError:
    HAS_EZDXF = False
    logger.info("ezdxf not installed - DXF processing will be unavailable")


def _require_ezdxf() -> None:
    """Raise ImportError with a helpful message if ezdxf is not available."""
    if not HAS_EZDXF:
        raise ImportError("ezdxf is required for DXF processing. Install it with: pip install 'ezdxf>=0.18.0'")


def _aci_to_hex(aci: int) -> str:
    """Convert AutoCAD Color Index (ACI) to hex color string.

    Returns a hex color for common ACI values, falls back to #ffffff.
    """
    aci_map = {
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
    return aci_map.get(aci, "#ffffff")


def _serialize_entity(
    entity: Any,
    layer_colors: dict[str, str] | None = None,
    styles: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Convert an ezdxf entity to a JSON-serializable dict.

    ``styles`` maps a text-style name to the font file it references (built
    once from the STYLE table in :func:`parse_dxf`). TEXT/MTEXT entities
    carry both their style name and resolved font so the viewer can render
    the drawing's real font instead of a generic fallback. A missing style
    resolves to an empty font string, never a crash.
    """
    if styles is None:
        styles = {}
    dxf = entity.dxf
    aci = dxf.get("color", 256)  # 256 = ByLayer (default)
    layer_name = dxf.get("layer", "0")
    # ACI 0 (ByBlock) or 256 (ByLayer): use layer color
    if aci in (0, 256) and layer_colors and layer_name in layer_colors:
        color = layer_colors[layer_name]
    else:
        color = _aci_to_hex(aci)
    result: dict[str, Any] = {
        "entity_type": entity.dxftype(),
        "layer": layer_name,
        "color": color,
        "geometry_data": {},
    }

    entity_type = entity.dxftype()

    if entity_type == "LINE":
        result["geometry_data"] = {
            "start": {"x": dxf.start.x, "y": dxf.start.y},
            "end": {"x": dxf.end.x, "y": dxf.end.y},
        }
    elif entity_type == "CIRCLE":
        result["geometry_data"] = {
            "center": {"x": dxf.center.x, "y": dxf.center.y},
            "radius": dxf.radius,
        }
    elif entity_type == "ARC":
        result["geometry_data"] = {
            "center": {"x": dxf.center.x, "y": dxf.center.y},
            "radius": dxf.radius,
            "start_angle": math.radians(dxf.start_angle),
            "end_angle": math.radians(dxf.end_angle),
        }
    elif entity_type in ("LWPOLYLINE", "POLYLINE"):
        try:
            points = []
            if entity_type == "LWPOLYLINE":
                for x, y, *_ in entity.get_points(format="xy"):
                    points.append({"x": x, "y": y})
            else:
                for vertex in entity.vertices:
                    loc = vertex.dxf.location
                    points.append({"x": loc.x, "y": loc.y})
            result["geometry_data"] = {
                "points": points,
                "closed": getattr(entity, "closed", False),
            }
        except Exception:
            result["geometry_data"] = {"points": [], "closed": False}
    elif entity_type == "TEXT":
        insert = dxf.get("insert", None)
        style_name = dxf.get("style", "Standard")
        result["geometry_data"] = {
            "insert": {"x": insert.x, "y": insert.y} if insert else {"x": 0, "y": 0},
            "text": dxf.get("text", ""),
            "height": dxf.get("height", 1.0),
            "rotation": dxf.get("rotation", 0.0),
            "style": style_name,
            "font": styles.get(style_name, ""),
        }
    elif entity_type == "MTEXT":
        insert = dxf.get("insert", None)
        style_name = dxf.get("style", "Standard")
        # Attachment point (1–9): insert is top-left for 1, mid-left for 4, etc.
        # The viewer must match this or schedule rows stack into each other.
        result["geometry_data"] = {
            "insert": {"x": insert.x, "y": insert.y} if insert else {"x": 0, "y": 0},
            "text": entity.plain_text() if hasattr(entity, "plain_text") else str(entity.text),
            "height": dxf.get("char_height", 1.0),
            "attachment_point": int(dxf.get("attachment_point", 1) or 1),
            "style": style_name,
            "font": styles.get(style_name, ""),
        }
    elif entity_type == "INSERT":
        insert = dxf.get("insert", None)
        result["geometry_data"] = {
            "insert": {"x": insert.x, "y": insert.y} if insert else {"x": 0, "y": 0},
            "block_name": dxf.get("name", ""),
            "x_scale": dxf.get("xscale", 1.0),
            "y_scale": dxf.get("yscale", 1.0),
            "rotation": dxf.get("rotation", 0.0),
        }
    elif entity_type == "ELLIPSE":
        center = dxf.get("center", None)
        major_axis = dxf.get("major_axis", None)
        result["geometry_data"] = {
            "center": {"x": center.x, "y": center.y} if center else {"x": 0, "y": 0},
            "major_axis": ({"x": major_axis.x, "y": major_axis.y} if major_axis else {"x": 1, "y": 0}),
            "ratio": dxf.get("ratio", 1.0),
        }
    elif entity_type == "SPLINE":
        try:
            points = [{"x": p.x, "y": p.y} for p in entity.control_points]
            result["geometry_data"] = {"control_points": points}
        except Exception:
            result["geometry_data"] = {"control_points": []}
    elif entity_type in ("SOLID", "TRACE", "3DFACE"):
        try:
            v0 = entity.dxf.vtx0
            v1 = entity.dxf.vtx1
            v2 = entity.dxf.vtx2
            v3 = getattr(entity.dxf, "vtx3", v2)
            if entity_type in ("SOLID", "TRACE"):
                points = [
                    {"x": v0.x, "y": v0.y},
                    {"x": v1.x, "y": v1.y},
                    {"x": v3.x, "y": v3.y},
                    {"x": v2.x, "y": v2.y},
                ]
            else:
                points = [
                    {"x": v0.x, "y": v0.y},
                    {"x": v1.x, "y": v1.y},
                    {"x": v2.x, "y": v2.y},
                    {"x": v3.x, "y": v3.y},
                ]
            result["geometry_data"] = {"points": points, "closed": True, "is_solid": True}
        except Exception:
            result["geometry_data"] = {"points": [], "closed": True, "is_solid": True}
    elif entity_type == "HATCH":
        points = []
        is_solid = False
        try:
            is_solid = getattr(entity, "solid_fill", False) or dxf.get("pattern_name", "").upper() == "SOLID"
            for p in getattr(entity, "paths", []):
                p_type = type(p).__name__
                if p_type == "PolylinePath" and hasattr(p, "vertices"):
                    for v in p.vertices:
                        points.append({"x": v[0], "y": v[1]})
                elif p_type == "EdgePath" and hasattr(p, "edges"):
                    for edge in p.edges:
                        if hasattr(edge, "start"):
                            points.append({"x": edge.start[0], "y": edge.start[1]})
                        if hasattr(edge, "end"):
                            points.append({"x": edge.end[0], "y": edge.end[1]})
        except Exception:
            pass
        result["geometry_data"] = {
            "points": points,
            "closed": True,
            "pattern_name": dxf.get("pattern_name", "SOLID"),
            "is_solid": is_solid,
        }
    elif entity_type == "DIMENSION":
        result["geometry_data"] = {
            "dimension_type": dxf.get("dimtype", 0),
            "text_override": dxf.get("text", ""),
        }

    return result


def parse_dxf(file_path: str) -> dict[str, Any]:
    """Parse a DXF file and extract layers, entities, extents, and units.

    Args:
        file_path: Path to the DXF file on disk.

    Returns:
        Dict with keys: layers, entities, extents, units, entity_count.

    Raises:
        ImportError: If ezdxf is not installed.
        ValueError: If the file cannot be parsed.
    """
    _require_ezdxf()

    try:
        doc = ezdxf.readfile(file_path)
    except Exception as exc:
        try:
            from ezdxf import recover
            doc, _ = recover.readfile(file_path)
        except Exception as recover_exc:
            raise ValueError(f"Failed to parse DXF file: {exc} (recover failed: {recover_exc})") from exc

    # Extract layers
    #
    # BUG-005: ``not layer.is_off and not layer.is_frozen`` returned
    # False for every layer on certain DXF imports (notably layer "0"
    # on R2018-vintage files).  ezdxf reports ``is_off`` based on the
    # signed-color encoding which some CAD packages don't honour, so
    # we now default to visible and only flip to hidden when the
    # source file *explicitly* marks the layer off.  Pulls each bit
    # in its own try/except - ezdxf 1.4 occasionally raises on
    # malformed layer entries, and a single exception used to silently
    # collapse the whole expression to False (the canvas would then
    # render empty after import).
    layers: list[dict[str, Any]] = []
    for layer in doc.layers:
        is_off = False
        is_frozen = False
        try:
            # ezdxf exposes is_off / is_frozen as methods — must call them.
            # ``bool(layer.is_off)`` is always True (bound method), which
            # marked every layer invisible and hid room/door/window labels.
            off_fn = layer.is_off
            is_off = bool(off_fn() if callable(off_fn) else off_fn)
        except Exception:  # noqa: BLE001 - defensive: see comment above
            pass
        try:
            frozen_fn = layer.is_frozen
            is_frozen = bool(frozen_fn() if callable(frozen_fn) else frozen_fn)
        except Exception:  # noqa: BLE001
            pass
        layers.append(
            {
                "name": layer.dxf.name,
                "color": _aci_to_hex(layer.color),
                "visible": not (is_off or is_frozen),
                "entity_count": 0,
            }
        )

    # Build layer color map for ByLayer color resolution
    layer_color_map: dict[str, str] = {layer["name"]: layer["color"] for layer in layers}

    # Read the STYLE table once: map each text-style name to the font it
    # references so TEXT/MTEXT entities can carry the drawing's real font
    # for the viewer. Defensive on every axis - ``doc.styles`` may be empty
    # or raise on a malformed record; a missing font degrades to "" rather
    # than crashing the whole parse.
    styles: dict[str, str] = {}
    try:
        for style in doc.styles:
            try:
                styles[style.dxf.name] = style.dxf.get("font", "") or style.dxf.get("bigfont", "") or ""
            except Exception:  # noqa: BLE001 - skip a single malformed style record
                continue
    except Exception:  # noqa: BLE001 - no/unreadable STYLE table
        styles = {}

    # Build layer name set for counting
    layer_counts: dict[str, int] = {}

    # Extract entities from ALL layouts (Model, Layout1, Layout2, etc.)
    entities: list[dict[str, Any]] = []
    layout_names: list[str] = []
    skipped_count = 0
    total_count = 0
    for layout in doc.layouts:
        layout_name = layout.name
        layout_names.append(layout_name)
        for entity in layout:
            total_count += 1
            try:
                serialized = _serialize_entity(entity, layer_color_map, styles)
                serialized["layout"] = layout_name
                entities.append(serialized)
                layer_name = serialized.get("layer", "0")
                layer_counts[layer_name] = layer_counts.get(layer_name, 0) + 1
            except Exception:
                skipped_count += 1
                logger.debug("Skipping unprocessable entity: %s", entity.dxftype())

    if total_count > 0 and skipped_count / total_count > 0.10:
        logger.warning(
            "DXF parse: %d of %d entities skipped (%.1f%%) in %s",
            skipped_count,
            total_count,
            100.0 * skipped_count / total_count,
            file_path,
        )

    # Update layer entity counts
    for layer_info in layers:
        layer_info["entity_count"] = layer_counts.get(layer_info["name"], 0)

    # Calculate extents from parsed entities (more reliable than msp.get_extents)
    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")
    for ent in entities:
        gd = ent.get("geometry_data", {})
        points: list[tuple[float, float]] = []
        if "start" in gd and "end" in gd:
            points.append((gd["start"]["x"], gd["start"]["y"]))
            points.append((gd["end"]["x"], gd["end"]["y"]))
        if "points" in gd:
            for v in gd["points"]:
                points.append((v["x"], v["y"]))
        if "center" in gd:
            r = gd.get("radius", 0)
            cx, cy = gd["center"]["x"], gd["center"]["y"]
            points.append((cx - r, cy - r))
            points.append((cx + r, cy + r))
        if "insertion_point" in gd:
            points.append((gd["insertion_point"]["x"], gd["insertion_point"]["y"]))
        for px, py in points:
            min_x = min(min_x, px)
            min_y = min(min_y, py)
            max_x = max(max_x, px)
            max_y = max(max_y, py)

    if min_x == float("inf"):
        min_x = min_y = 0.0
        max_x = max_y = 1000.0
    extents = {"min_x": float(min_x), "min_y": float(min_y), "max_x": float(max_x), "max_y": float(max_y)}

    # Extract units
    units_map = {
        0: "unitless",
        1: "inches",
        2: "feet",
        3: "miles",
        4: "mm",
        5: "cm",
        6: "m",
        7: "km",
    }
    insunits = doc.header.get("$INSUNITS", 0)
    units = units_map.get(insunits, "unitless")

    # BUG-D-TKC-002c - when $INSUNITS is absent/0 ("unitless") fall back to
    # an extents-based guess. A drawing whose largest extent is >=1000 units
    # is almost certainly authored in millimetres; without this an mm DXF
    # with no header reads 1000x too large (service.py applies a 1.0 factor
    # for "unitless"). Mirrors the DDC parser path.
    if units == "unitless":
        from app.modules.dwg_takeoff.ddc_dwg_parser import infer_units_from_extents

        units = infer_units_from_extents(extents) or units

    # Deduplicate and sort layout names, ensure "Model" comes first
    unique_layouts = list(dict.fromkeys(layout_names))

    return {
        "layers": layers,
        "entities": entities,
        "extents": extents,
        "units": units,
        "entity_count": len(entities),
        "skipped_count": skipped_count,
        "layouts": unique_layouts,
    }


def generate_svg_thumbnail(file_path: str) -> str:
    """Generate an SVG thumbnail from a DXF file.

    Args:
        file_path: Path to the DXF file on disk.

    Returns:
        SVG content as a string.

    Raises:
        ImportError: If ezdxf is not installed.
        ValueError: If the file cannot be processed.
    """
    _require_ezdxf()

    try:
        try:
            doc = ezdxf.readfile(file_path)
        except Exception:
            from ezdxf import recover
            doc, _ = recover.readfile(file_path)
        msp = doc.modelspace()

        # ezdxf 1.4 reorganised the drawing add-on: the SVG bytes now come
        # from ``backend.get_string()`` (or its xml-tree variant), not
        # ``frontend.out`` - that attribute was removed when the backend
        # registry replaced the legacy ``Frontend.out`` slot (BUG-014).
        # Fall through to the placeholder branch only on real errors -
        # don't let a single AttributeError silently downgrade the
        # thumbnail for every drawing.
        ctx = RenderContext(doc)
        backend = ezdxf_svg.SVGBackend()
        Frontend(ctx, backend).draw_layout(msp)
        if hasattr(backend, "get_string"):
            # ezdxf 1.1+ changed the signature to ``get_string(page)`` where
            # ``page`` is a ``layout.Page`` describing the output size;
            # ``Page(0, 0)`` auto-fits the page to the drawing extents. Older
            # 0.x builds exposed ``get_string()`` with no argument, so fall
            # back to that when the new signature isn't accepted.
            try:
                from ezdxf.addons.drawing import layout as ezdxf_layout

                return backend.get_string(ezdxf_layout.Page(0, 0))
            except TypeError:
                return backend.get_string()
        # ezdxf 1.5+ - backend exposes ``get_xml_root()`` instead; fall
        # back to that and serialise via the stdlib.
        if hasattr(backend, "get_xml_root"):
            from xml.etree import ElementTree

            return ElementTree.tostring(backend.get_xml_root(), encoding="unicode")
        raise RuntimeError(
            "SVGBackend exposes neither get_string nor get_xml_root; "
            "ezdxf API may have shifted again - bump the dependency pin."
        )
    except Exception as exc:
        # Fallback: generate a minimal placeholder SVG
        logger.exception("SVG generation failed, returning placeholder: %s", exc)
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 600">'
            '<rect width="800" height="600" fill="#1a1a2e" />'
            '<text x="400" y="300" text-anchor="middle" fill="#888" '
            'font-size="24">DXF Preview Unavailable</text>'
            "</svg>"
        )


def calculate_entity_measurement(entity_data: dict[str, Any]) -> float:
    """Calculate a measurement value for a DWG entity.

    Supports LINE (length), CIRCLE (circumference), ARC (arc length),
    LWPOLYLINE/POLYLINE (total length), and area for closed polylines.

    Args:
        entity_data: Serialized entity dict from _serialize_entity.

    Returns:
        Measurement value in drawing units.
    """
    entity_type = entity_data.get("entity_type", "")
    geometry = entity_data.get("geometry_data", {})

    if entity_type == "LINE":
        start = geometry.get("start", {})
        end = geometry.get("end", {})
        dx = end.get("x", 0) - start.get("x", 0)
        dy = end.get("y", 0) - start.get("y", 0)
        return math.sqrt(dx * dx + dy * dy)

    elif entity_type == "CIRCLE":
        radius = geometry.get("radius", 0)
        return 2 * math.pi * radius

    elif entity_type == "ARC":
        # Bugfix (C3): start_angle/end_angle are ALREADY in radians (see
        # _extract_geometry above which writes math.radians(dxf.start_angle)).
        # The previous code applied math.radians() a second time, so arc
        # lengths came out off by (π/180)² ≈ 3.05e-4 - a 90° arc rendered
        # as ~0 metres. Use the stored radians directly; defensive modulo
        # 2π keeps sweep angles in [0, 2π) regardless of source orientation.
        radius = geometry.get("radius", 0)
        start_angle = geometry.get("start_angle", 0)
        end_angle = geometry.get("end_angle", 0)
        angle = end_angle - start_angle
        if angle < 0:
            angle += 2 * math.pi
        return radius * angle

    elif entity_type in ("LWPOLYLINE", "POLYLINE"):
        points = geometry.get("points", [])
        if len(points) < 2:
            return 0.0
        total = 0.0
        for i in range(len(points) - 1):
            dx = points[i + 1].get("x", 0) - points[i].get("x", 0)
            dy = points[i + 1].get("y", 0) - points[i].get("y", 0)
            total += math.sqrt(dx * dx + dy * dy)
        # Add closing segment if closed
        if geometry.get("closed", False) and len(points) > 2:
            dx = points[0].get("x", 0) - points[-1].get("x", 0)
            dy = points[0].get("y", 0) - points[-1].get("y", 0)
            total += math.sqrt(dx * dx + dy * dy)
        return total

    return 0.0

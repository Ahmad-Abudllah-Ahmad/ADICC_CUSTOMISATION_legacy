# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""DWG Takeoff service - business logic.

Stateless service layer. Handles:
- Drawing upload, processing, and retrieval
- DXF parsing via ezdxf (layers, entities, SVG thumbnail)
- Annotation CRUD and BOQ position linking
- Task/punchlist pin queries
"""

import asyncio
import json
import logging
import os
import shutil
import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.modules.dwg_takeoff.models import (
    DwgAnnotation,
    DwgDrawing,
    DwgDrawingVersion,
    DwgEntityGroup,
)
from app.modules.dwg_takeoff.repository import (
    DwgAnnotationRepository,
    DwgDrawingRepository,
    DwgDrawingVersionRepository,
    DwgEntityGroupRepository,
)
from app.modules.dwg_takeoff.schemas import (
    DwgAnnotationCreate,
    DwgAnnotationUpdate,
    DwgEntityGroupCreate,
)

logger = logging.getLogger(__name__)


# Strong references to in-flight background conversion tasks. asyncio only
# keeps a WEAK reference to a task, so a detached ``create_task`` whose
# handle is dropped can be garbage-collected mid-run - cancelling the
# conversion and leaving the drawing stuck at status=uploaded/processing
# forever (the frontend poll of /drawings/{id} never completes). Holding
# the task here until it finishes prevents that; the done-callback evicts
# it so the set does not grow unbounded.
_BACKGROUND_CONVERSION_TASKS: set["asyncio.Task[None]"] = set()


def _spawn_dwg_conversion(drawing_id: uuid.UUID, file_path: str) -> "asyncio.Task[None]":
    """Launch the detached DWG conversion and retain a strong reference.

    Wraps ``asyncio.create_task`` so the returned task is stored in a
    module-level set (preventing premature garbage collection) and removed
    again once it completes. Returns the created task for callers/tests.
    """
    task = asyncio.create_task(_run_dwg_conversion_in_background(drawing_id, file_path))
    _BACKGROUND_CONVERSION_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_CONVERSION_TASKS.discard)
    return task


# ── Orphaned-conversion (stale) detection ───────────────────────────────────
# A live DWG conversion self-fails at OE_DWG_CONVERT_TIMEOUT_S (default 300s):
# subprocess.run(timeout=...) hard-kills the converter at that bound. So a
# drawing still sitting at "processing"/"uploaded" with NO parsed entities long
# past that bound is orphaned - its detached background task died with the
# process (a server restart / reinstall / crash), and asyncio tasks never
# survive a restart, so nothing will ever complete or fail it. Left alone the
# frontend polls "processing" forever - the "Converting... 2547m" infinite
# spinner a real user hit after reinstalling. Treat anything older than the
# convert timeout plus a generous margin as dead and surface an actionable error.


def _stale_conversion_cutoff_seconds() -> int:
    """Seconds after which a still-``processing`` drawing is deemed orphaned."""
    convert_timeout = int(os.getenv("OE_DWG_CONVERT_TIMEOUT_S", "300"))
    # Twice the convert timeout, floored at 10 minutes - comfortably past any
    # real run (which is force-killed at the timeout) without false positives.
    return max(convert_timeout * 2, 600)


_STALE_CONVERSION_MESSAGE = (
    "Conversion did not finish - it was most likely interrupted by a server "
    "restart or update while processing. Please remove this drawing and upload "
    "it again."
)


def _seconds_since(ts: datetime | None) -> float | None:
    """Age in seconds of a timestamp, or ``None`` if unset.

    Naive timestamps are treated as UTC (the app persists UTC).
    """
    if ts is None:
        return None
    now = datetime.now(UTC)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return (now - ts).total_seconds()


# ── DWG version sniff & gating (Indian-user stability ticket 2026-05-13) ────


# DWG R14 (1997) is the oldest format we will hand to DDC. Older
# versions are exotic and DDC genuinely cannot read them. Anything
# between R14 and R18 sometimes works and sometimes does not - we
# used to pre-emptively reject R14-R17 to spare users a misleading
# "empty output" error, but the 2026-05-14 bench showed several
# R16/R17 files DO convert successfully, so we now let DDC have a
# go and surface its real error if it fails.
_DWG_MIN_SUPPORTED_VERSION_CODE = "AC1014"

# Human-readable labels for the DWG magic-byte version codes we care
# about. The mapping comes from Open Design Alliance's specs.
_DWG_VERSION_LABELS: dict[str, str] = {
    "AC1014": "DWG R14 (1997)",
    "AC1015": "DWG 2000 (R15)",
    "AC1018": "DWG 2004 (R16)",
    "AC1021": "DWG 2007 (R17)",
    "AC1024": "DWG 2010 (R18)",
    "AC1027": "DWG 2013 (R19)",
    "AC1032": "DWG 2018 (R22)",
}


def _sniff_dwg_version(path: str) -> tuple[str | None, str]:
    """Read the 6-byte DWG magic prefix and return ``(code, label)``.

    Returns ``(None, "")`` for anything that doesn't match the
    ``AC\\d{4}`` pattern - that includes:

    * Renamed PDFs (start with ``%PDF-``)
    * Renamed ZIPs (start with ``PK\\x03\\x04``)
    * Empty / truncated files
    * Files whose first 6 bytes are non-ASCII or arbitrary text

    Without this guard, the upstream DDC DwgExporter spends 90+ s
    chewing on the garbage input and then returns a misleading "empty
    output" error to the user. The Indian-user ticket (2026-05-13)
    traced 4 of 5 reported failures to PDF/ZIP files renamed with a
    ``.dwg`` extension by mistake.
    """
    try:
        with open(path, "rb") as f:
            head = f.read(6)
    except OSError:
        return None, ""

    if len(head) < 6:
        return None, ""

    # Must be ASCII first, then match the AC#### pattern.
    try:
        text = head.decode("ascii")
    except UnicodeDecodeError:
        return None, ""

    if not (text.startswith("AC") and text[2:].isdigit()):
        return None, ""

    label = _DWG_VERSION_LABELS.get(text, f"DWG ({text})")
    return text, label


def _looks_like_dxf(head: bytes) -> bool:
    """Return True if a 64-byte header looks like an ASCII or binary DXF.

    Binary DXF files start with the literal ``AutoCAD Binary DXF\\r\\n``
    sentinel (22 bytes, per the DXF reference). ASCII DXF files always
    begin with a group code line - the very first non-whitespace token
    is ``0`` followed by the line break and the ``SECTION`` keyword. We
    accept the broader ``0\\r?\\n\\s*SECTION`` shape because some CAD
    exporters use ``LF`` line endings on Linux and pad with spaces.

    A renamed PDF (``%PDF-``), ZIP (``PK\\x03\\x04``) or DWG (``AC####``)
    will fail this check, so the upload endpoint can return a clean 400
    instead of writing garbage to disk and waiting for the parse failure.
    """
    if not head:
        return False
    # Binary DXF sentinel - case-sensitive per the spec.
    if head.startswith(b"AutoCAD Binary DXF"):
        return True
    # ASCII DXF: skip leading whitespace, then group code "0", newline,
    # then "SECTION" within the first ~60 bytes. ezdxf is more lenient
    # than this but we only need to disambiguate from "this is clearly
    # something else" (PDF / ZIP / DWG / random text).
    stripped = head.lstrip()
    if not stripped.startswith(b"0"):
        return False
    # Scan a small window for the SECTION keyword to handle whitespace /
    # comment variations without bringing in a real DXF parser.
    return b"SECTION" in head[:128]


def _validate_cad_magic_bytes(content: bytes, file_format: str) -> tuple[bool, str]:
    """Sniff the first bytes of an upload and confirm the declared format.

    Returns ``(True, "")`` if the content matches the declared format, or
    ``(False, reason)`` with a user-friendly message otherwise. The upload
    endpoint surfaces this as a 400 so renamed PDFs / ZIPs / images never
    reach disk or the DDC subprocess.

    No i18n here - the message is consumed by the existing error wrapper
    which translates at render time.
    """
    head = content[:128] if content else b""
    if file_format == "dwg":
        code, _ = _sniff_dwg_version_bytes(head)
        if code is None:
            return False, (
                "This file does not look like a valid DWG. If you renamed "
                "a PDF / ZIP / image to .dwg, please upload the original "
                "CAD file instead."
            )
        return True, ""
    if file_format == "dxf":
        if not _looks_like_dxf(head):
            return False, (
                "This file does not look like a valid DXF. The file must "
                "start with a DXF group code (ASCII) or the "
                "'AutoCAD Binary DXF' sentinel."
            )
        return True, ""
    # Unknown format slips through - caller has already rejected by
    # extension by the time we get here.
    return True, ""


def _sniff_dwg_version_bytes(head: bytes) -> tuple[str | None, str]:
    """In-memory variant of :func:`_sniff_dwg_version` for upload streams.

    Operates on already-read bytes so we don't have to write the file to
    disk before deciding whether to accept it.
    """
    if len(head) < 6:
        return None, ""
    try:
        text = head[:6].decode("ascii")
    except UnicodeDecodeError:
        return None, ""
    if not (text.startswith("AC") and text[2:].isdigit()):
        return None, ""
    label = _DWG_VERSION_LABELS.get(text, f"DWG ({text})")
    return text, label


def _dwg_version_too_old(code: str | None) -> bool:
    """Return True if a sniffed DWG version code predates R18 (2010).

    ``None`` is the "couldn't sniff" sentinel - we say False (not too
    old) so the caller's downstream "is this a real DWG at all?"
    check fires first with the friendlier error message. Non-numeric
    tails are also tolerated as forward-compat: a future AC#### we
    don't recognise gets a chance instead of a blanket refusal.
    """
    if code is None:
        return False
    if not (code.startswith("AC") and code[2:].isdigit()):
        return False
    try:
        version_num = int(code[2:])
        floor_num = int(_DWG_MIN_SUPPORTED_VERSION_CODE[2:])
    except ValueError:
        return False
    return version_num < floor_num


def _normalize_entity(raw: dict[str, Any], index: int) -> dict[str, Any]:
    """Flatten stored entity format to the shape the frontend DxfViewer expects.

    Stored format: {entity_type, layer, color, geometry_data: {…}}
    Frontend format: {id, type, layer, color, start?, end?, vertices?, …}
    """
    gd = raw.get("geometry_data", {})
    entity_type = raw.get("entity_type", "")
    # Map MTEXT → TEXT for the frontend renderer
    front_type = "TEXT" if entity_type == "MTEXT" else entity_type

    result: dict[str, Any] = {
        "id": f"e_{index}",
        "type": front_type,
        "layer": raw.get("layer", "0"),
        "color": raw.get("color", "#cccccc"),
    }

    # Pass through layout field (DXF layout name or DWG BlockId)
    if "layout" in raw:
        result["layout"] = raw["layout"]

    if entity_type == "LINE":
        result["start"] = gd.get("start")
        result["end"] = gd.get("end")
    elif entity_type in ("LWPOLYLINE", "POLYLINE"):
        result["vertices"] = gd.get("points", [])
        result["closed"] = gd.get("closed", False)
        if "is_solid" in gd:
            result["is_solid"] = gd["is_solid"]
        if "pattern_name" in gd:
            result["pattern_name"] = gd["pattern_name"]
    elif entity_type == "CIRCLE":
        result["start"] = gd.get("center")
        result["radius"] = gd.get("radius")
    elif entity_type == "ARC":
        result["start"] = gd.get("center")
        result["radius"] = gd.get("radius")
        result["start_angle"] = gd.get("start_angle", 0)
        result["end_angle"] = gd.get("end_angle", 6.283185307179586)
    elif entity_type == "ELLIPSE":
        result["start"] = gd.get("center")
        result["major_radius"] = gd.get("major_radius")
        result["minor_radius"] = gd.get("minor_radius")
        result["rotation"] = gd.get("rotation", 0)
        result["start_angle"] = gd.get("start_angle", 0)
        result["end_angle"] = gd.get("end_angle", 0)
        # Also provide major_axis for ezdxf-style format
        if "major_axis" in gd:
            result["major_axis"] = gd["major_axis"]
            result["ratio"] = gd.get("ratio", 1.0)
    elif entity_type in ("TEXT", "MTEXT"):
        result["start"] = gd.get("insert") or gd.get("insertion_point")
        result["text"] = gd.get("text", "")
        result["height"] = gd.get("height", 2.5)
        result["rotation"] = gd.get("rotation", 0)
        # Carry the text style + resolved font through to the viewer so it
        # renders the drawing's real font instead of a generic fallback.
        result["style"] = gd.get("style", "")
        result["font"] = gd.get("font", "")
        # MTEXT insert is an attachment point (default top-left=1), not baseline.
        if entity_type == "MTEXT":
            result["attachment_point"] = int(gd.get("attachment_point") or 1)
    elif entity_type == "INSERT":
        result["start"] = gd.get("insert") or gd.get("insertion_point")
        result["block_name"] = gd.get("block_name") or gd.get("name", "")
        result["rotation"] = gd.get("rotation", 0)
        result["x_scale"] = gd.get("x_scale", 1.0)
        result["y_scale"] = gd.get("y_scale", 1.0)
    elif entity_type in ("HATCH", "SOLID", "TRACE", "3DFACE"):
        result["vertices"] = gd.get("points", []) or gd.get("vertices", [])
        result["closed"] = gd.get("closed", True)
        result["pattern_name"] = gd.get("pattern_name", "SOLID")
        result["is_solid"] = gd.get("is_solid", True)
    elif entity_type == "SPLINE":
        result["type"] = "LWPOLYLINE"
        result["vertices"] = gd.get("control_points", [])
        result["closed"] = False
    elif entity_type == "DIMENSION":
        result["start"] = gd.get("start")
        result["end"] = gd.get("end")

    return result


def _dwg_data_base() -> str:
    """Base directory for DWG blobs (the ACTIVE writable root).

    Defers to :func:`app.core.storage.resolve_data_dir` (lazy import) so this
    module can never disagree with where the platform actually writes blobs.
    That resolver honours ``OE_DATA_DIR`` > ``DATA_DIR`` > ``OE_CLI_DATA_DIR``
    before its persistent per-user / repo-relative default.

    Crucially this is the single root that :func:`safe_data_roots` always
    contains, so a DWG written here passes the download route's safe-root gate
    instead of being rejected and served as a placeholder. The old body
    defaulted to ``<cwd>/data`` - never a member of ``safe_data_roots()`` and
    sensitive to the process CWD - which is exactly what broke "ready" drawings
    on standalone / Docker / macOS deployments.

    Resolved PER CALL (not cached at import) so ``OE_DATA_DIR`` and test
    monkeypatching take effect. WRITES always target this root; READS may fall
    back across :func:`safe_data_roots` via :func:`_dwg_existing_path`.
    """
    from app.core.storage import resolve_data_dir

    return str(resolve_data_dir())


def _dwg_existing_path(base_subdir: str, key: str) -> str | None:
    """Resolve ``<base>/<base_subdir>/<key>`` to an existing file, READ-ONLY.

    Tries the ACTIVE data root first (``_dwg_data_base()``); if the blob is not
    there, probes every OTHER platform-owned data root from
    :func:`app.core.storage.safe_data_roots` for the same relative location.
    This lets a blob written under a prior data-dir resolution (e.g. before
    ``OE_DATA_DIR`` was honoured, the package-relative default a ``pip -U``
    replaced, or a different CWD) still be served instead of going missing.

    Reads fall back; WRITES never do. Containment is re-checked against each
    candidate root with ``relative_to`` so a crafted ``key`` can never escape a
    data root. Returns ``None`` when the file exists nowhere.
    """
    from app.core.storage import safe_data_roots

    # Reject path-traversal in the key before touching the filesystem.
    parts = [p for p in str(key).replace("\\", "/").split("/") if p and p != "."]
    if any(p == ".." for p in parts) or os.path.isabs(key):
        return None

    seen: set[str] = set()
    active = os.path.realpath(_dwg_data_base())
    roots = [active]
    for root in safe_data_roots():
        roots.append(os.path.realpath(str(root)))

    for root in roots:
        if root in seen:
            continue
        seen.add(root)
        candidate = os.path.realpath(os.path.join(root, base_subdir, *parts))
        # Containment: candidate must stay under this root.
        if os.path.commonpath([candidate, root]) != root:
            continue
        if os.path.isfile(candidate):
            if root != active:
                logger.info(
                    "dwg: %s/%s absent under active root %s; served from back-compat data root %s",
                    base_subdir,
                    key,
                    active,
                    root,
                )
            return candidate
    return None


def _get_upload_dir() -> str:
    """Get the upload directory for DWG files."""
    upload_dir = os.path.join(_dwg_data_base(), "dwg_uploads")
    os.makedirs(upload_dir, exist_ok=True)
    return upload_dir


def _get_entities_dir() -> str:
    """Get the storage directory for parsed entity JSON files."""
    entities_dir = os.path.join(_dwg_data_base(), "dwg_entities")
    os.makedirs(entities_dir, exist_ok=True)
    return entities_dir


def resolve_source_drawing_path(stored_file_path: str | None) -> str | None:
    """Resolve a drawing's source-blob path for READ, with back-compat fallback.

    The stored ``file_path`` is the absolute path captured at upload time under
    whatever data root was active then. If the data-dir resolution has since
    changed (e.g. the old ``<cwd>/data`` default, or before ``OE_DATA_DIR`` was
    honoured) that absolute path may no longer point at the file. We:

    1. return the stored path verbatim when it still exists as a regular file
       AND lives inside a platform-owned safe root (preserves the existing
       symlink / safe-root guarantees the download route relies on);
    2. otherwise recover the blob by its basename under ``dwg_uploads/`` across
       every :func:`safe_data_roots` (READ-ONLY fallback).

    Returns ``None`` when nothing resolves, so the caller keeps its existing
    placeholder / 404 behaviour. This never writes and never escapes a data
    root (``_dwg_existing_path`` re-checks containment per candidate).
    """
    from pathlib import Path

    from app.core.storage import is_within_safe_root

    if stored_file_path:
        try:
            resolved = os.path.realpath(stored_file_path)
        except OSError:
            resolved = ""
        if (
            resolved
            and os.path.isfile(resolved)
            and not os.path.islink(stored_file_path)
            and is_within_safe_root(Path(resolved))
        ):
            return resolved
        # Recover by basename across the back-compat read roots.
        basename = os.path.basename(stored_file_path)
        if basename:
            return _dwg_existing_path("dwg_uploads", basename)
    return None


def _extents_from_raw_entities(entities: list[dict[str, Any]]) -> dict[str, float] | None:
    """Compute a bounding box from stored (un-normalised) entity records.

    Mirrors the parser's ``expand`` pass over the stored
    ``{entity_type, geometry_data: {…}}`` shape. Used by the lazy units
    backfill to recover extents for legacy/seeded drawings whose version row
    stored ``extents == {}``. Returns ``None`` when no coordinates are found.
    """
    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")
    found = False

    def expand(x: Any, y: Any) -> None:
        nonlocal min_x, min_y, max_x, max_y, found
        try:
            fx, fy = float(x), float(y)
        except (TypeError, ValueError):
            return
        min_x, min_y = min(min_x, fx), min(min_y, fy)
        max_x, max_y = max(max_x, fx), max(max_y, fy)
        found = True

    for ent in entities:
        gd = ent.get("geometry_data", {}) or {}
        start = gd.get("start")
        end = gd.get("end")
        if isinstance(start, dict):
            expand(start.get("x"), start.get("y"))
        if isinstance(end, dict):
            expand(end.get("x"), end.get("y"))
        for v in gd.get("points", []) or []:
            if isinstance(v, dict):
                expand(v.get("x"), v.get("y"))
        center = gd.get("center")
        if isinstance(center, dict):
            r = gd.get("radius") or gd.get("major_radius") or 0
            try:
                rr = float(r)
            except (TypeError, ValueError):
                rr = 0.0
            expand(center.get("x", 0) - rr, center.get("y", 0) - rr)
            expand(center.get("x", 0) + rr, center.get("y", 0) + rr)
        for key in ("insert", "insertion_point"):
            pt = gd.get(key)
            if isinstance(pt, dict):
                expand(pt.get("x"), pt.get("y"))

    if not found:
        return None
    return {
        "min_x": float(min_x),
        "min_y": float(min_y),
        "max_x": float(max_x),
        "max_y": float(max_y),
    }


def _process_dxf_sync(file_path: str, entities_key: str, thumbnail_key: str) -> dict[str, Any]:
    """Synchronous DXF processing - runs in a thread via asyncio.to_thread.

    Parses the DXF file, saves entities JSON, and generates SVG thumbnail.
    Returns a dict with parse results and storage keys.
    """
    from app.modules.dwg_takeoff.dxf_processor import generate_svg_thumbnail, parse_dxf

    result = parse_dxf(file_path)

    # Save entities JSON to disk
    entities_path = os.path.join(_get_entities_dir(), entities_key)
    os.makedirs(os.path.dirname(entities_path), exist_ok=True)
    with open(entities_path, "w", encoding="utf-8") as f:
        json.dump(result["entities"], f)

    # Generate and save SVG thumbnail
    svg_content = generate_svg_thumbnail(file_path)
    thumb_dir = os.path.join(_dwg_data_base(), "dwg_thumbnails")
    thumb_path = os.path.join(thumb_dir, thumbnail_key)
    os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
    with open(thumb_path, "w", encoding="utf-8") as f:
        f.write(svg_content)

    return result


# ── Revision compare (Item 17) ──────────────────────────────────────────────


def _layer_count_map(layers: Any) -> dict[str, int]:
    """Reduce a stored ``layers`` blob to ``{layer_name: entity_count}``.

    Accepts both the canonical list-of-dicts shape and the legacy
    dict-keyed-by-name shape (mirrors
    ``DwgDrawingVersionResponse._normalize_layers``). A layer missing an
    ``entity_count`` contributes 0 so a count-less layer still appears in
    the diff as present. Never raises - a malformed blob yields ``{}`` so
    the compare degrades to "no entity changes" rather than a 500.
    """
    rows: list[Any]
    if isinstance(layers, dict):
        rows = list(layers.values())
    elif isinstance(layers, list):
        rows = layers
    else:
        return {}

    out: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        try:
            count = int(row.get("entity_count") or 0)
        except (TypeError, ValueError):
            count = 0
        # Sum duplicates defensively (some parsers emit one row per layout).
        out[name] = out.get(name, 0) + count
    return out


def _compute_entity_diff(
    from_layers: Any,
    to_layers: Any,
) -> list[dict[str, Any]]:
    """Diff two versions' layer profiles into entity-diff rows.

    Entities carry no stable cross-parse identity, so we compare the
    per-layer entity count. A layer present only in the new version is
    ``added``; only in the old version ``removed``; present in both with
    a different count ``modified``; identical count ``unchanged``. Rows
    are returned sorted by layer name for deterministic output.
    """
    from_map = _layer_count_map(from_layers)
    to_map = _layer_count_map(to_layers)

    rows: list[dict[str, Any]] = []
    for layer in sorted(set(from_map) | set(to_map)):
        old_count = from_map.get(layer, 0)
        new_count = to_map.get(layer, 0)
        if layer not in from_map:
            change_type = "added"
        elif layer not in to_map:
            change_type = "removed"
        elif old_count != new_count:
            change_type = "modified"
        else:
            change_type = "unchanged"
        rows.append(
            {
                "change_type": change_type,
                "entity_id": layer,
                "entity_type": "layer",
                "layer": layer,
                "old_count": old_count,
                "new_count": new_count,
                "delta": new_count - old_count,
            }
        )
    return rows


def _summarize_diff(
    entity_rows: list[dict[str, Any]],
    annotation_rows: list[dict[str, Any]],
    *,
    from_entity_count: int,
    to_entity_count: int,
) -> dict[str, Any]:
    """Roll entity + annotation diff rows into the compare summary block.

    Shared by the single-drawing version compare and the drawing-pair
    compare so both emit an identical summary shape: per-bucket
    traffic-light tallies for entities and annotations, plus the net cost
    impact in a single base currency (never blended across currencies).
    ``unchanged`` is excluded from the headline change tallies but still
    returned in the rows for the "show all" view.
    """

    def _tally(rows: list[dict[str, Any]]) -> dict[str, int]:
        tally = {"added": 0, "removed": 0, "modified": 0, "unchanged": 0}
        for row in rows:
            tally[row["change_type"]] = tally.get(row["change_type"], 0) + 1
        return tally

    # Net cost impact across all linked annotations whose value changed.
    net_impact = Decimal("0")
    cost_currency: str | None = None
    has_cost = False
    for row in annotation_rows:
        if row.get("cost_impact") is not None:
            has_cost = True
            cost_currency = row.get("cost_currency") or cost_currency
            try:
                net_impact += Decimal(str(row["cost_impact"]))
            except (InvalidOperation, ValueError, TypeError):
                continue

    return {
        "entities": _tally(entity_rows),
        "annotations": _tally(annotation_rows),
        "net_cost_impact": (str(net_impact.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)) if has_cost else None),
        "cost_currency": cost_currency,
        "from_entity_count": from_entity_count,
        "to_entity_count": to_entity_count,
    }


def _to_float(value: Any) -> float | None:
    """Coerce a ``Decimal``/number/string measurement to ``float`` or None.

    ``DwgAnnotation.measurement_value`` round-trips as ``Decimal`` (the
    Numeric(18,6) column); the diff response exposes plain floats. A
    ``None`` or unparseable value collapses to ``None`` so a value-less
    annotation never reads as ``0`` in the diff.
    """
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError, InvalidOperation):
        return None


def _annotation_label(ann: "DwgAnnotation") -> str | None:
    """Short human label for an annotation row in the diff table."""
    text = (ann.text or "").strip()
    if text:
        return text[:120]
    return ann.annotation_type


def _calculate_cost_impact(
    *,
    old_value: float | None,
    new_value: float | None,
    unit_rate: str | int | float | Decimal | None,
) -> str | None:
    """Signed money delta ``(new - old) * unit_rate`` as a Decimal string.

    Returns ``None`` when the impact cannot be computed (either value
    missing, or the rate is unparseable / zero). The result is quantised
    to 2 fractional digits with commercial rounding (ROUND_HALF_UP), the
    same boundary the BOQ rollups use, and is expressed in the project's
    base currency - the caller never blends currencies because a BOQ
    position's ``unit_rate`` is already stored in that base currency.
    """
    if old_value is None or new_value is None:
        return None
    try:
        rate = Decimal(str(unit_rate).strip()) if unit_rate not in (None, "") else Decimal("0")
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not rate.is_finite() or rate == 0:
        return None
    try:
        delta = Decimal(repr(float(new_value))) - Decimal(repr(float(old_value)))
    except (InvalidOperation, ValueError, TypeError):
        return None
    impact = (delta * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return str(impact)


def _build_revision_narrative(
    *,
    entity_tally: dict[str, Any],
    annotation_tally: dict[str, Any],
    changed_linked_count: int,
) -> str:
    """Plain-text description of a revision delta for a draft variation.

    Built only from the deterministic summary tallies (no AI). Reads like
    "3 layers added, 1 removed, 2 changed; 4 annotations added, 1 removed,
    5 changed; 2 priced (linked-to-BOQ) annotation values changed." so the
    estimator sees what moved before they confirm the variation.
    """

    def _n(tally: dict[str, Any], key: str) -> int:
        try:
            return int(tally.get(key, 0) or 0)
        except (ValueError, TypeError):
            return 0

    parts = [
        (
            f"{_n(entity_tally, 'added')} layers added, "
            f"{_n(entity_tally, 'removed')} removed, "
            f"{_n(entity_tally, 'modified')} changed"
        ),
        (
            f"{_n(annotation_tally, 'added')} annotations added, "
            f"{_n(annotation_tally, 'removed')} removed, "
            f"{_n(annotation_tally, 'modified')} changed"
        ),
        f"{changed_linked_count} priced (linked-to-BOQ) annotation values changed",
    ]
    return (
        "Auto-generated from a drawing revision compare. "
        + "; ".join(parts)
        + ". Review and confirm before submitting this variation."
    )


class DwgTakeoffService:
    """Business logic for DWG drawings, versions, and annotations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.drawing_repo = DwgDrawingRepository(session)
        self.version_repo = DwgDrawingVersionRepository(session)
        self.annotation_repo = DwgAnnotationRepository(session)
        self.group_repo = DwgEntityGroupRepository(session)

    # ── Drawing upload & processing ─────────────────────────────────────

    async def upload_drawing(
        self,
        project_id: uuid.UUID,
        file: UploadFile,
        user_id: str,
        *,
        name: str | None = None,
        discipline: str | None = None,
        sheet_number: str | None = None,
    ) -> DwgDrawing:
        """Upload a DWG/DXF file and create a database record.

        The file is saved to disk and processing is triggered in a background thread.
        """
        filename = file.filename or "drawing.dxf"
        ext = os.path.splitext(filename)[1].lower()
        if ext not in (".dwg", ".dxf"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only .dwg and .dxf files are supported",
            )

        file_format = ext.lstrip(".")
        content = await file.read()
        size_bytes = len(content)

        # Magic-byte validation - reject renamed PDFs/ZIPs/images BEFORE
        # writing them to disk or burning a DB row. The extension check
        # above only confirms the user typed ``.dwg`` / ``.dxf``; this
        # confirms the bytes match. Closes the class of "90+s DDC chew
        # on garbage input" reports from the 2026-05-13 stability ticket
        # for the DXF path too (the previous sniff fired only on DWG).
        ok, reason = _validate_cad_magic_bytes(content, file_format)
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=reason,
            )

        # Create drawing record FIRST (before writing file to disk)
        upload_dir = _get_upload_dir()
        file_id = str(uuid.uuid4())
        file_path = os.path.join(upload_dir, f"{file_id}{ext}")

        drawing = DwgDrawing(
            project_id=project_id,
            name=name or os.path.splitext(filename)[0],
            filename=filename,
            file_format=file_format,
            file_path=file_path,
            size_bytes=size_bytes,
            status="uploaded",
            discipline=discipline,
            sheet_number=sheet_number,
            created_by=user_id,
            metadata_={},
        )
        drawing = await self.drawing_repo.create(drawing)
        drawing_id = drawing.id

        # Save file to disk AFTER DB record exists; clean up on failure
        try:
            with open(file_path, "wb") as f:
                f.write(content)
        except Exception:
            await self.drawing_repo.delete(drawing_id)
            raise

        logger.info(
            "Drawing uploaded: %s (%s, %d bytes) project=%s",
            filename,
            file_format,
            size_bytes,
            project_id,
        )

        # Cross-link: create a Document row pointing at the same file on
        # disk so the drawing also appears in the Documents hub.  This is
        # best-effort - failure here MUST NOT break the drawing upload.
        # The document is NOT a copy: ``file_path`` references the same
        # blob already persisted by the dwg_takeoff module.
        try:
            from app.modules.documents.models import Document

            xlink_doc = Document(
                project_id=project_id,
                name=filename,
                description=f"DWG/DXF drawing: {name or filename}",
                category="drawing",
                file_size=size_bytes,
                mime_type=f"image/vnd.{file_format}",
                file_path=file_path,
                version=1,
                uploaded_by=user_id or "",
                tags=["dwg-takeoff", file_format] + ([discipline] if discipline else []),
                metadata_={
                    "source_module": "dwg_takeoff",
                    "source_id": str(drawing_id),
                },
            )
            self.session.add(xlink_doc)
            await self.session.flush()
            logger.info(
                "Cross-linked DWG drawing %s → document %s",
                drawing_id,
                xlink_doc.id,
            )
        except Exception as exc:
            logger.warning("Failed to cross-link DWG to documents hub: %s", exc)

        # Trigger processing.
        #
        # DXF: parsed locally with ezdxf - fast (<2 s for typical
        # drawings), runs inline so the response carries final
        # status=ready / entity counts.
        #
        # DWG: handed to the DDC DwgExporter binary which can take
        # 30-120 s and occasionally hangs / crashes. Awaiting it
        # inline used to exhaust the uvicorn worker pool - a single
        # stuck conversion would queue subsequent uploads behind it
        # until they hit the client's read timeout (observed
        # 2026-05-14: one R16 crash poisoned the next 5+ uploads with
        # HTTP 500 / ReadTimeout). We commit the upload row first so
        # a fresh AsyncSession in the background task can see it,
        # then fire-and-forget the conversion. The frontend already
        # polls /drawings/{id} to observe status transition
        # uploaded → processing → ready/error.
        if file_format == "dxf":
            await self._process_drawing(drawing_id, file_path)
        elif file_format == "dwg":
            await self.session.commit()
            # Retain a strong reference so the detached task isn't GC'd
            # mid-conversion (see _spawn_dwg_conversion).
            _spawn_dwg_conversion(drawing_id, file_path)

        await self.session.refresh(drawing)
        return drawing

    async def upload_revision(
        self,
        drawing_id: uuid.UUID,
        file: UploadFile,
        user_id: str,
    ) -> DwgDrawing:
        """Upload a new revision onto an EXISTING drawing.

        Unlike :meth:`upload_drawing`, this reuses the drawing row and
        appends the new parse as version N+1 instead of creating a second
        drawing. Mirrors the upload path for the extension check, magic-byte
        validation and on-disk storage (to a fresh path so the previous
        revision's blob is left intact), then repoints the existing row at
        the new file and re-runs the SAME processing dispatch. Both
        ``_process_drawing`` (DXF) and ``_handle_dwg`` (DWG) resolve the next
        version number via ``get_next_version_number``, so the revision
        history accrues on one drawing and the revision-compare flow works
        off a single drawing id.

        Raises 404 if the drawing does not exist, 400 on a bad extension or
        content that fails magic-byte validation.
        """
        drawing = await self.get_drawing(drawing_id)  # 404 if missing
        # Capture the project id NOW, before ``update_fields`` runs
        # ``session.expire_all()``. Reading ``drawing.project_id`` after that
        # would trigger a lazy reload on the async path and raise
        # MissingGreenlet (BUG-D-TKC-002d). The cross-link bump below uses
        # this captured value instead of a live attribute access.
        project_id = drawing.project_id

        filename = file.filename or "drawing.dxf"
        ext = os.path.splitext(filename)[1].lower()
        if ext not in (".dwg", ".dxf"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only .dwg and .dxf files are supported",
            )

        file_format = ext.lstrip(".")
        content = await file.read()
        size_bytes = len(content)

        # Same magic-byte gate as the direct upload path - reject a renamed
        # PDF/ZIP/image before it reaches disk or the DDC subprocess.
        ok, reason = _validate_cad_magic_bytes(content, file_format)
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=reason,
            )

        # Write the revision to a NEW path so the previous version's blob is
        # left untouched. Any write failure leaves the existing row (and its
        # current file) intact - we never delete the drawing here.
        upload_dir = _get_upload_dir()
        file_id = str(uuid.uuid4())
        new_path = os.path.join(upload_dir, f"{file_id}{ext}")
        with open(new_path, "wb") as f:
            f.write(content)

        # Repoint the existing drawing row at the new revision. status resets
        # to "uploaded" so the viewer shows the in-flight state until the new
        # parse completes; error_message is cleared from any prior failure.
        await self.drawing_repo.update_fields(
            drawing_id,
            file_path=new_path,
            filename=filename,
            file_format=file_format,
            size_bytes=size_bytes,
            status="uploaded",
            error_message=None,
        )

        logger.info(
            "Drawing revision uploaded: %s (%s, %d bytes) drawing=%s",
            filename,
            file_format,
            size_bytes,
            drawing_id,
        )

        # Best-effort: bump the cross-linked Document (created by the original
        # upload) so the Documents hub reflects the new revision and points at
        # the current blob. Never break the revision upload on failure.
        try:
            from sqlalchemy import select as _sa_select

            from app.modules.documents.models import Document

            stmt = _sa_select(Document).where(Document.project_id == project_id).limit(500)
            docs = (await self.session.execute(stmt)).scalars().all()
            target = str(drawing_id)
            for doc in docs:
                meta = doc.metadata_ or {}
                if str(meta.get("source_id") or "") == target:
                    doc.version = int(doc.version or 1) + 1
                    doc.file_path = new_path
                    doc.file_size = size_bytes
                    self.session.add(doc)
                    await self.session.flush()
                    break
        except Exception as exc:  # noqa: BLE001 - cross-link bump is best-effort
            logger.warning(
                "Failed to bump cross-linked document for drawing %s: %s",
                drawing_id,
                exc,
            )

        # Same dispatch policy as upload_drawing: DXF parses inline so the
        # response already carries the new version; DWG is committed first and
        # converted in a detached task while the client polls /drawings/{id}.
        # Both paths store the parse as version N+1 via get_next_version_number.
        if file_format == "dxf":
            await self._process_drawing(drawing_id, new_path)
        elif file_format == "dwg":
            await self.session.commit()
            # Retain a strong reference so the detached task isn't GC'd
            # mid-conversion (see _spawn_dwg_conversion).
            _spawn_dwg_conversion(drawing_id, new_path)

        await self.session.refresh(drawing)
        return drawing

    async def import_drawing_from_document(
        self,
        document_id: uuid.UUID,
        user_id: str,
        *,
        name: str | None = None,
        discipline: str | None = None,
    ) -> DwgDrawing:
        """Create a DWG/DXF drawing from an already-uploaded Document.

        The Documents hub and DWG takeoff module both persist files on
        disk; a CAD file uploaded through /files (or any other module)
        lives only as a ``Document`` row and has no ``DwgDrawing`` to
        render in the takeoff viewer. Opening it via "Open in DWG Takeoff"
        previously produced a blank page because the deep-link handler
        could only resolve an *existing* drawing. This method materialises
        the missing drawing on demand so the document opens immediately.

        Behaviour:

        * **Idempotent** - if a drawing already references this document
          (cross-link ``source_id`` / ``imported_from_document_id``) or
          points at the same blob on disk, the existing one is returned
          instead of creating a duplicate (re-clicking is a no-op).
        * Reads the document's bytes from disk, runs the same magic-byte
          validation as the direct upload path, copies the blob into the
          DWG upload dir, creates the drawing row, and dispatches
          processing (DXF inline → ``ready``; DWG fire-and-forget).
        * Raises 404 when the document or its file is missing, 400 when
          it is not a ``.dwg`` / ``.dxf`` file.

        The owning project's access has already been gated by the router
        (``verify_project_access`` on ``document.project_id``) before this
        runs, so ``project_id`` here is trusted.
        """
        from app.modules.documents.models import Document

        document = await self.session.get(Document, document_id)
        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )

        project_id = document.project_id
        source_filename = document.name or "drawing.dxf"
        ext = os.path.splitext(source_filename)[1].lower()
        if ext not in (".dwg", ".dxf"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This document is not a DWG/DXF file and cannot be opened in DWG Takeoff.",
            )
        file_format = ext.lstrip(".")

        # Idempotency - never create a second drawing for the same
        # document. Two earlier rows can reference it:
        #   1. A drawing imported here before (``imported_from_document_id``).
        #   2. The drawing whose own upload created this document via the
        #      cross-link (``Document.metadata.source_id`` → drawing id).
        # Both are checked so re-clicking "Open in DWG Takeoff" reuses the
        # existing drawing instead of duplicating files + DB rows.
        doc_meta = dict(document.metadata_ or {})
        if doc_meta.get("source_module") == "dwg_takeoff" and doc_meta.get("source_id"):
            try:
                existing = await self.drawing_repo.get_by_id(
                    uuid.UUID(str(doc_meta["source_id"])),
                )
            except (ValueError, TypeError):
                existing = None
            if existing is not None and existing.project_id == project_id:
                return existing

        existing_by_link = await self._find_drawing_for_document(project_id, document_id)
        if existing_by_link is not None:
            return existing_by_link

        # Read the source bytes from disk. A missing blob is a 404 (the
        # document row exists but the file is gone) rather than a 500.
        src_path = document.file_path or ""
        if not src_path or not os.path.exists(src_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="The document's file is no longer available on disk.",
            )
        try:
            with open(src_path, "rb") as f:
                content = f.read()
        except OSError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Unable to read the document's file.",
            ) from exc

        size_bytes = len(content)

        # Same magic-byte gate as the direct upload path - a document
        # whose name ends in .dwg/.dxf but whose bytes are a renamed
        # PDF/ZIP/image is rejected before we burn a drawing row.
        ok, reason = _validate_cad_magic_bytes(content, file_format)
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=reason,
            )

        # Copy the blob into the DWG upload dir under a fresh id so the
        # drawing owns its own file (deleting the drawing won't strand the
        # original document, and vice versa).
        upload_dir = _get_upload_dir()
        file_id = str(uuid.uuid4())
        file_path = os.path.join(upload_dir, f"{file_id}{ext}")

        drawing = DwgDrawing(
            project_id=project_id,
            name=name or os.path.splitext(source_filename)[0],
            filename=source_filename,
            file_format=file_format,
            file_path=file_path,
            size_bytes=size_bytes,
            status="uploaded",
            discipline=discipline,
            created_by=user_id or "",
            metadata_={"imported_from_document_id": str(document_id)},
        )
        drawing = await self.drawing_repo.create(drawing)
        drawing_id = drawing.id

        try:
            with open(file_path, "wb") as f:
                f.write(content)
        except Exception:
            await self.drawing_repo.delete(drawing_id)
            raise

        # Point the source document back at its new drawing so the
        # Documents hub deep-link resolves the drawing directly next time
        # (and the idempotency check above short-circuits future imports).
        try:
            document.metadata_ = {
                **doc_meta,
                "source_module": "dwg_takeoff",
                "source_id": str(drawing_id),
            }
            self.session.add(document)
            await self.session.flush()
        except Exception as exc:  # noqa: BLE001 - best-effort cross-link
            logger.warning(
                "Failed to back-link document %s → drawing %s: %s",
                document_id,
                drawing_id,
                exc,
            )

        logger.info(
            "Imported drawing %s from document %s (%s, %d bytes) project=%s",
            drawing_id,
            document_id,
            file_format,
            size_bytes,
            project_id,
        )

        # Same dispatch policy as upload_drawing: DXF parses inline so the
        # response already carries status=ready; DWG is committed first and
        # converted in a detached task while the client polls /drawings/{id}.
        if file_format == "dxf":
            await self._process_drawing(drawing_id, file_path)
        elif file_format == "dwg":
            await self.session.commit()
            # Retain a strong reference so the detached task isn't GC'd
            # mid-conversion (see _spawn_dwg_conversion).
            _spawn_dwg_conversion(drawing_id, file_path)

        await self.session.refresh(drawing)
        return drawing

    async def _find_drawing_for_document(
        self,
        project_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> DwgDrawing | None:
        """Return a drawing already imported from ``document_id``, if any.

        Scans the project's drawings for one whose metadata carries the
        ``imported_from_document_id`` back-reference. The drawing count
        per project is small (tens, not thousands), so a list scan is
        cheaper than adding an indexed JSON column for a once-per-open
        idempotency check.
        """
        items, _ = await self.drawing_repo.list_for_project(
            project_id,
            offset=0,
            limit=200,
        )
        target = str(document_id)
        for item in items:
            meta = item.metadata_ or {}
            if str(meta.get("imported_from_document_id") or "") == target:
                return item
        return None

    async def _process_drawing(self, drawing_id: uuid.UUID, file_path: str) -> None:
        """Process a DXF file: parse layers/entities, generate thumbnail."""
        await self.drawing_repo.update_fields(drawing_id, status="processing")
        # Large ODA DXFs can take tens of seconds to parse — do not hold a
        # write transaction across that work (blocks scale PATCH / polls).
        await self.session.commit()

        # Prepare storage keys
        entities_key = f"{drawing_id}/entities.json"
        thumbnail_key = f"{drawing_id}/thumbnail.svg"

        try:
            result = await asyncio.to_thread(_process_dxf_sync, file_path, entities_key, thumbnail_key)

            # Create drawing version
            version_number = await self.version_repo.get_next_version_number(drawing_id)
            # Treat 0-entity DXFs as a user-visible failure rather than a
            # silent ``ready`` row. Without this the frontend mounts the
            # canvas, sees an empty entity list, and shows an indefinite
            # loading spinner - there's nothing to render and no banner to
            # explain. Surfaced as ``empty`` so an explicit message is
            # shown ("This DXF contains no entities"). DDC- and ezdxf-
            # generated empty files (e.g. mozman/ezdxf empty_handles.dxf
            # fixture, 1.3 KB) both land here.
            entity_count_val = int(result.get("entity_count") or 0)
            is_empty = entity_count_val == 0
            version = DwgDrawingVersion(
                drawing_id=drawing_id,
                version_number=version_number,
                layers=result["layers"],
                entities_key=entities_key,
                entity_count=entity_count_val,
                extents=result["extents"],
                units=result["units"],
                status="empty" if is_empty else "ready",
                metadata_={},
            )
            await self.version_repo.create(version)

            # Update drawing status
            await self.drawing_repo.update_fields(
                drawing_id,
                status="empty" if is_empty else "ready",
                thumbnail_key=thumbnail_key,
                error_message=(
                    "This DXF/DWG contains no drawable entities - the file is empty or contains only metadata."
                    if is_empty
                    else None
                ),
            )
            await self.session.commit()

            if is_empty:
                logger.warning(
                    "Drawing %s parsed as empty (0 entities, %d layers) - surfacing status=empty to the user",
                    drawing_id,
                    len(result["layers"]),
                )
            else:
                logger.info(
                    "Drawing processed: %s - %d entities, %d layers",
                    drawing_id,
                    result["entity_count"],
                    len(result["layers"]),
                )

        except ImportError:
            await self.drawing_repo.update_fields(
                drawing_id,
                status="error",
                error_message="ezdxf is not installed - cannot process DXF files",
            )
            logger.error("ezdxf not installed - cannot process drawing %s", drawing_id)

        except Exception as exc:
            await self.drawing_repo.update_fields(
                drawing_id,
                status="error",
                error_message=str(exc)[:500],
            )
            logger.exception("Failed to process drawing %s: %s", drawing_id, exc)

    async def _handle_dwg(self, drawing_id: uuid.UUID, file_path: str) -> None:
        """Process DWG via DDC DwgExporter → Excel → parse entities.

        Pre-conversion stability guards (Indian-user ticket 2026-05-13):

        1. ``_sniff_dwg_version`` checks the 6-byte ``AC####`` magic
           prefix. Renamed PDFs/ZIPs and truncated files are rejected
           here with a clean 422 instead of being handed to the
           converter (which spends 90+ s on them and then returns a
           confusing "empty output" error).

        2. ``_dwg_version_too_old`` rejects DWGs older than the
           2010 (R18) format. DDC's DwgExporter occasionally produces silent
           empty output for R14/R15/R16/R17 files; the upgrade hint
           is a much better UX than "no entities found".
        """
        version_code, version_label = _sniff_dwg_version(file_path)
        if version_code is None:
            await self.drawing_repo.update_fields(
                drawing_id,
                status="error",
                error_message=(
                    "This file does not look like a valid DWG. "
                    "If you renamed a PDF or ZIP archive to .dwg, please "
                    "upload the original CAD file instead."
                ),
            )
            return
        if _dwg_version_too_old(version_code):
            await self.drawing_repo.update_fields(
                drawing_id,
                status="error",
                error_message=(
                    f"{version_label} is older than the supported DWG "
                    f"format. Re-save it in DWG 2010 (R18) format or "
                    f"newer from your CAD application and upload again."
                ),
            )
            return

        try:
            from app.modules.boq.cad_import import (
                _converter_subprocess_env,
                build_ddc_args,
                detect_converter_capabilities,
                find_converter,
            )

            converter = find_converter("dwg")
        except ImportError:
            converter = None
            build_ddc_args = None  # type: ignore[assignment]
            detect_converter_capabilities = None  # type: ignore[assignment]
            _converter_subprocess_env = None  # type: ignore[assignment]

        # Prefer DDC when present (Windows/Linux). On macOS (and as a
        # Linux fallback) use ODA File Converter → DXF, then LibreDWG
        # dwg2SVG + GeoJSON. LibreDWG's dwg2dxf is intentionally NOT used:
        # it often emits DXF that ezdxf cannot load for modern AC#### files.
        if converter is None:
            await self.drawing_repo.update_fields(drawing_id, status="processing")
            # Release the row lock BEFORE ODA/LibreDWG runs (can take minutes).
            # Holding the transaction across conversion blocked concurrent
            # PATCHes (e.g. scale) for 45s+ and the UI showed "Request timed out".
            await self.session.commit()
            convert_timeout_s = int(os.getenv("OE_DWG_CONVERT_TIMEOUT_S", "300"))
            handled = await self._handle_dwg_without_ddc(
                drawing_id,
                file_path,
                timeout_s=convert_timeout_s,
            )
            if handled:
                return
            import sys

            from app.modules.dwg_takeoff.mac_dwg import oda_download_url

            is_mac = sys.platform == "darwin"
            if is_mac:
                msg = (
                    "No DWG reader found on this Mac. Install ODA File Converter "
                    f"from {oda_download_url()} into /Applications (best quality, "
                    "keeps layer names), or run `brew install libredwg` for a "
                    "geometry fallback. You can also export DXF from your CAD "
                    "app and upload that instead."
                )
            else:
                msg = (
                    "DWG conversion requires the DDC DwgExporter binary, "
                    "which was not found on this server. Click the "
                    '"Install converter" pill at the top right of /dwg-takeoff, '
                    "or download manually from "
                    "https://github.com/datadrivenconstruction/cad2data-Revit-IFC-DWG-DGN. "
                    "DXF files work without the converter."
                )
            await self.drawing_repo.update_fields(
                drawing_id,
                status="error",
                error_message=msg,
            )
            return

        await self.drawing_repo.update_fields(drawing_id, status="processing")
        # Same as the ODA path: commit before the long subprocess so other
        # requests (scale PATCH, status polls) are not stuck on a row lock.
        await self.session.commit()

        import subprocess
        from pathlib import Path as _Path

        # DDC DwgExporter → Excel. Compose the CLI through the same
        # capability-aware builder the takeoff router uses so we don't
        # hand v18 flag-driven binaries the legacy positional shape
        # (``<input> <output> -no-collada``) - that returns exit 15 with
        # ``arguments were not expected: ... -no-collada``, the same root
        # cause that previously surfaced as "CAD conversion failed for
        # .rvt" in the CAD/BIM Data Explorer. Once DDC ships a v18
        # DwgExporter this code keeps working without any further patch.
        # DWG conversion can legitimately take minutes on large drawings, so
        # match the 300s the CAD/BIM Data Explorer (boq.cad_import) already
        # allows. The old 120s cap timed out files the explorer converts fine.
        # Overridable via env for very large sets or slow boxes.
        convert_timeout_s = int(os.getenv("OE_DWG_CONVERT_TIMEOUT_S", "300"))
        xlsx_path = file_path.rsplit(".", 1)[0] + "_dwg.xlsx"
        try:
            caps = detect_converter_capabilities("dwg")
            args = build_ddc_args(
                converter,
                _Path(file_path).resolve(),
                caps=caps,
                xlsx_out=_Path(xlsx_path).resolve(),
                # DWG converters historically do not support a mode preset
                # (the takeoff router only emits ``standard`` for RVT/IFC).
                # build_ddc_args' v18 path emits ``-m standard`` only when
                # ``caps.accepts_flag_mode`` is True, which currently fires
                # for RVT - harmless on DWG should DDC adopt it later.
                mode="standard",
                include_no_dae=True,
            )
            # Pass the converter launch environment. On Linux this sets
            # LD_LIBRARY_PATH to the extracted .deb tree so the DDC cad2data
            # DwgExporter resolves its bundled SDK shared libraries
            # (ddc-deps-kernel/drawings/architecture, ddc-thirdparty) at launch.
            # The frontend "Install converter" flow downloads and unpacks those
            # .deb packages into a user-writable dir (no apt/root), so the libs
            # are not on the system linker path; without LD_LIBRARY_PATH the
            # binary starts but conversion produces empty output on a headless
            # server. Returns None on Windows/macOS, where inheriting the parent
            # environment is correct. This mirrors every other converter launch
            # site (cad_import.convert_cad_to_excel, smoke_test_converter,
            # detect_converter_capabilities).
            proc = await asyncio.to_thread(
                lambda: subprocess.run(
                    args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=str(converter.parent),
                    env=_converter_subprocess_env(converter),
                    input=b"\n",
                    timeout=convert_timeout_s,
                )
            )
            if not os.path.exists(xlsx_path) or os.path.getsize(xlsx_path) < 100:
                stderr_msg = proc.stderr.decode(errors="replace")[:300] if proc.stderr else ""
                rc = proc.returncode
                low = stderr_msg.lower()
                # Surface the actual reason instead of a generic "no output".
                # On a headless Linux server the common failure is a missing
                # shared library: exit 127 / "error while loading shared
                # libraries" is the tell. Name the library from stderr and give
                # both fixes, since we can't reliably tell from the .so name
                # alone which it is: a DDC cad2data SDK library means reinstall
                # the converter (its .deb set bundles them), a system library
                # such as libssl3 means install it with the OS package manager
                # (the converter download does not ship system dependencies).
                if rc == 127 or "error while loading shared libraries" in low:
                    import re

                    m = re.search(r"lib[\w.+-]*\.so[.\d]*", stderr_msg)
                    lib_txt = f" ({m.group(0)})" if m else ""
                    nice_msg = (
                        f"The DWG converter could not start: a shared library{lib_txt} is missing "
                        "on this server. If it is a system library (for example libssl3), install "
                        "it with your OS package manager, e.g. apt-get install libssl3. If it is a "
                        'converter library, reinstall the converter with the "Install converter" '
                        "button on the /dwg-takeoff page so its cad2data SDK libraries are restored. "
                        f"Details: {stderr_msg}"
                    ).strip()
                # "Error: converter crashed." is the DDC binary's generic
                # catch-all when it can't initialise (incompatible DWG version
                # DDC's parser doesn't yet support, or an internal exception).
                # Surface an actionable alternative: DXF upload works without DDC.
                elif "converter crashed" in low:
                    nice_msg = (
                        "The DWG converter could not process this file. "
                        "Try exporting the drawing as DXF from your CAD "
                        "application (File, Save As, DXF) and upload that "
                        "instead. DXF is handled directly without requiring DDC."
                    )
                else:
                    nice_msg = (f"DDC DwgExporter produced no output (exit {rc}): {stderr_msg}").strip()
                await self.drawing_repo.update_fields(
                    drawing_id,
                    status="error",
                    error_message=nice_msg[:500],
                )
                return
        except subprocess.TimeoutExpired:
            await self.drawing_repo.update_fields(
                drawing_id,
                status="error",
                error_message=f"DWG conversion timed out ({convert_timeout_s}s limit)",
            )
            return
        except Exception as exc:
            await self.drawing_repo.update_fields(
                drawing_id,
                status="error",
                error_message=f"DWG conversion error: {exc}"[:500],
            )
            return

        # Parse DDC Excel → entities (same format as ezdxf output)
        try:
            from app.modules.dwg_takeoff.ddc_dwg_parser import parse_ddc_dwg_excel

            result = await asyncio.to_thread(parse_ddc_dwg_excel, xlsx_path)

            if result["entity_count"] == 0:
                await self.drawing_repo.update_fields(
                    drawing_id,
                    status="error",
                    error_message="No drawable entities found in DWG file",
                )
                return

            # Store entities JSON under the SAME relative key the DXF path
            # uses ({drawing_id}/entities.json inside _get_entities_dir()), so
            # get_entities()/list-versions resolve it via os.path.join on every
            # platform and the row survives a DATA_DIR move or cross-host
            # restore. Previously DWG stored an absolute, env-specific path
            # next to the source file, which only resolved on the same machine.
            entities_key = f"{drawing_id}/entities.json"
            entities_path = os.path.join(_get_entities_dir(), entities_key)
            os.makedirs(os.path.dirname(entities_path), exist_ok=True)
            import json

            with open(entities_path, "w", encoding="utf-8") as f:
                json.dump(result["entities"], f)

            # Create drawing version
            version_number = await self.version_repo.get_next_version_number(drawing_id)
            version = DwgDrawingVersion(
                drawing_id=drawing_id,
                version_number=version_number,
                layers=result["layers"],
                entities_key=entities_key,
                entity_count=result["entity_count"],
                extents=result["extents"],
                units=result.get("units", "unitless"),
                status="ready",
            )
            self.session.add(version)
            await self.drawing_repo.update_fields(
                drawing_id,
                status="ready",
                error_message=None,
            )
            await self.session.flush()

            logger.info(
                "DWG processed via DDC: %s - %d entities, %d layers",
                drawing_id,
                result["entity_count"],
                len(result["layers"]),
            )

        except Exception as exc:
            await self.drawing_repo.update_fields(
                drawing_id,
                status="error",
                error_message=f"DWG parsing error: {exc}"[:500],
            )
            logger.exception("Failed to parse DWG %s: %s", drawing_id, exc)

    async def _handle_dwg_without_ddc(
        self,
        drawing_id: uuid.UUID,
        file_path: str,
        *,
        timeout_s: int,
    ) -> bool:
        """Try ODA → DXF or LibreDWG (SVG + GeoJSON) when DDC DwgExporter is missing.

        Returns True when a backend handled the file (success or a specific
        conversion failure already persisted). Returns False when no Mac/POSIX
        backend is available so the caller can emit the install message.
        """
        from app.modules.dwg_takeoff import mac_dwg

        oda = mac_dwg.find_oda_file_converter()
        if oda is not None:
            try:
                dxf_path = await asyncio.to_thread(
                    mac_dwg.convert_dwg_to_dxf_via_oda,
                    file_path,
                    timeout_s=timeout_s,
                )
                # ODA writes into a temp dir — copy into durable uploads storage.
                upload_dir = _get_upload_dir()
                durable_dxf = os.path.join(upload_dir, f"{drawing_id}.dxf")
                await asyncio.to_thread(shutil.copy2, dxf_path, durable_dxf)
                await self.drawing_repo.update_fields(
                    drawing_id,
                    file_format="dxf",
                    file_path=durable_dxf,
                    error_message=None,
                )
                await self.session.commit()
                await self._process_drawing(drawing_id, durable_dxf)
                # Tag version so the UI can distinguish ODA fidelity from LibreDWG.
                version = await self.version_repo.get_latest_for_drawing(drawing_id)
                if version is not None:
                    md = dict(version.metadata_ or {})
                    md.update(
                        {
                            "dwg_backend": "oda",
                            "source": "oda_file_converter",
                            "accuracy": "dxf",
                        }
                    )
                    await self.version_repo.update_fields(version.id, metadata_=md)
                logger.info("DWG %s converted via ODA File Converter → DXF", drawing_id)
                return True
            except Exception as exc:
                logger.warning("ODA conversion failed for %s: %s", drawing_id, exc)
                # Fall through to LibreDWG if present.

        if (
            mac_dwg.find_libredwg_dwg2svg() is not None
            or mac_dwg.find_libredwg_dwgread() is not None
        ):
            try:
                result = await asyncio.to_thread(
                    mac_dwg.convert_dwg_via_libredwg,
                    file_path,
                    timeout_s=timeout_s,
                )
                await self._persist_parsed_dwg_entities(
                    drawing_id,
                    result,
                    source_label="LibreDWG",
                )
                return True
            except Exception as exc:
                logger.exception("LibreDWG conversion failed for %s", drawing_id)
                await self.drawing_repo.update_fields(
                    drawing_id,
                    status="error",
                    error_message=(
                        f"LibreDWG could not read this DWG accurately: {exc}. "
                        f"Install ODA File Converter from {mac_dwg.oda_download_url()} "
                        "for full sheet/layer fidelity, or export DXF from your CAD app."
                    )[:500],
                )
                return True

        return False

    async def _persist_parsed_dwg_entities(
        self,
        drawing_id: uuid.UUID,
        result: dict[str, Any],
        *,
        source_label: str,
    ) -> None:
        """Persist entities/version/thumbnail from a non-DDC DWG parse."""
        from app.modules.dwg_takeoff import mac_dwg

        if int(result.get("entity_count") or 0) == 0:
            await self.drawing_repo.update_fields(
                drawing_id,
                status="error",
                error_message="No drawable entities found in DWG file",
            )
            return

        entities_key = f"{drawing_id}/entities.json"
        entities_path = os.path.join(_get_entities_dir(), entities_key)
        os.makedirs(os.path.dirname(entities_path), exist_ok=True)
        with open(entities_path, "w", encoding="utf-8") as f:
            json.dump(result["entities"], f)

        thumbnail_key = f"{drawing_id}/thumbnail.svg"
        try:
            svg = mac_dwg.entities_to_svg_thumbnail(result)
            thumb_dir = os.path.join(_dwg_data_base(), "dwg_thumbnails")
            thumb_path = os.path.join(thumb_dir, thumbnail_key)
            os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
            with open(thumb_path, "w", encoding="utf-8") as f:
                f.write(svg)
        except Exception:  # noqa: BLE001 - thumbnail is best-effort
            logger.warning("Could not write SVG thumbnail for %s", drawing_id)
            thumbnail_key_val: str | None = None
        else:
            thumbnail_key_val = thumbnail_key

        version_number = await self.version_repo.get_next_version_number(drawing_id)
        version = DwgDrawingVersion(
            drawing_id=drawing_id,
            version_number=version_number,
            layers=result["layers"],
            entities_key=entities_key,
            entity_count=result["entity_count"],
            extents=result["extents"],
            units=result.get("units", "unitless"),
            status="ready",
            metadata_={"dwg_backend": source_label.lower().replace(" ", "_")},
        )
        self.session.add(version)
        await self.drawing_repo.update_fields(
            drawing_id,
            status="ready",
            error_message=None,
            thumbnail_key=thumbnail_key_val,
        )
        await self.session.commit()
        logger.info(
            "DWG processed via %s: %s - %d entities, %d layers",
            source_label,
            drawing_id,
            result["entity_count"],
            len(result["layers"]),
        )

    # ── Drawing CRUD ────────────────────────────────────────────────────

    async def get_drawing(self, drawing_id: uuid.UUID) -> DwgDrawing:
        """Get drawing by ID. Raises 404 if not found."""
        item = await self.drawing_repo.get_by_id(drawing_id)
        if item is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Drawing not found",
            )
        return item

    @staticmethod
    def conversion_age_seconds(drawing: object) -> float | None:
        """Seconds since a drawing was last touched (updated_at, else created_at).

        Used to detect an orphaned conversion - a drawing left at
        ``processing``/``uploaded`` long past the convert timeout because its
        background task died with a server restart.
        """
        return _seconds_since(getattr(drawing, "updated_at", None)) or _seconds_since(
            getattr(drawing, "created_at", None)
        )

    @staticmethod
    def resolve_view_status(
        *,
        status_value: str | None,
        file_format: str | None,
        has_entities: bool,
        converter_present: bool | None = None,
        age_seconds: float | None = None,
    ) -> str:
        """Resolve a definitive viewer status for a drawing.

        DWG is an open format we open directly. The frontend asks "what
        should the viewer show right now?" and must always get a terminal
        answer so it never spins forever (the fresh-install bug: demo DWG
        rows are seeded ``status="uploaded"`` and, with no DDC DwgExporter
        on disk, nothing ever transitions them).

        Resolution:

        * If parsed entities already exist -> ``ready`` (open it FAST,
          regardless of the stored lifecycle status).
        * A genuine terminal status (``ready`` / ``empty`` / ``error``) is
          passed through untouched.
        * A ``.dxf`` row still sitting at ``uploaded`` parses out of the
          box via ezdxf, so ``processing`` is the honest "give me a moment"
          state (the inline parse normally finishes before the first poll).
        * A ``.dwg`` row at ``uploaded`` with no entities and no available
          converter is reported as ``needs_conversion`` - a clear, friendly,
          actionable state ("Convert with cad2data") instead of a perpetual
          spinner. If the converter IS present the row is genuinely mid-flight,
          so we keep ``processing``.

        ``converter_present`` lets a batch caller (the list endpoint) probe the
        converter once and pass it in, avoiding a per-row filesystem probe.
        """
        if has_entities:
            return "ready"

        normalized = (status_value or "").lower()
        # An orphaned conversion (processing/uploaded, no entities, untouched well
        # past the convert timeout) is dead - report a terminal error so the
        # viewer stops spinning forever instead of passing "processing" through.
        if (
            normalized in ("processing", "uploaded")
            and age_seconds is not None
            and age_seconds > _stale_conversion_cutoff_seconds()
        ):
            return "error"
        if normalized in ("ready", "empty", "error", "processing", "needs_conversion"):
            return normalized

        fmt = (file_format or "").lower().lstrip(".")
        # ``uploaded`` (or any unknown pre-terminal state) with no entities.
        if fmt == "dwg":
            present = (
                converter_present
                if converter_present is not None
                else DwgTakeoffService.get_offline_readiness().get("converter_available", False)
            )
            return "processing" if present else "needs_conversion"
        # DXF parses locally; treat the brief pre-parse window as processing.
        return "processing"

    async def get_drawing_with_view_status(
        self,
        drawing_id: uuid.UUID,
    ) -> tuple[DwgDrawing, DwgDrawingVersion | None, str]:
        """Resolve a drawing, its latest version, and a definitive view status.

        Single read used by the single-drawing GET so the viewer always
        receives a terminal answer (see :meth:`resolve_view_status`). The
        latest version is fetched through :meth:`get_latest_version` so the
        lazy units backfill still runs.
        """
        drawing = await self.get_drawing(drawing_id)
        version = await self.get_latest_version(drawing_id)
        has_entities = version is not None and (version.entity_count or 0) > 0 and version.entities_key is not None
        age_seconds = self.conversion_age_seconds(drawing)
        view_status = self.resolve_view_status(
            status_value=drawing.status,
            file_format=drawing.file_format,
            has_entities=has_entities,
            age_seconds=age_seconds,
        )
        # Self-heal an orphaned conversion: persist the terminal error (with an
        # actionable message) so the DB stops reporting "processing" forever and
        # every later poll/list is fast and correct. Re-fetch the version AFTER
        # the write - update_fields() calls session.expire_all(), which would make
        # the already-loaded version emit an illegal lazy SELECT (MissingGreenlet)
        # when the router serialises it.
        if (
            view_status == "error"
            and (drawing.status or "").lower() in ("processing", "uploaded")
            and not drawing.error_message
        ):
            try:
                await self.drawing_repo.update_fields(
                    drawing_id,
                    status="error",
                    error_message=_STALE_CONVERSION_MESSAGE,
                )
                await self.session.commit()
                await self.session.refresh(drawing)
                version = await self.get_latest_version(drawing_id)
            except Exception:  # noqa: BLE001 - heal is best-effort; never fail the read
                logger.warning(
                    "Could not persist stale-conversion heal for drawing %s",
                    drawing_id,
                    exc_info=True,
                )
                await self.session.rollback()
        return drawing, version, view_status

    async def list_drawings(
        self,
        project_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 50,
        status_filter: str | None = None,
    ) -> tuple[list[DwgDrawing], int]:
        """List drawings for a project with pagination and filters."""
        return await self.drawing_repo.list_for_project(
            project_id,
            offset=offset,
            limit=limit,
            status_filter=status_filter,
        )

    async def update_drawing_scale(
        self,
        drawing_id: uuid.UUID,
        *,
        scale_denominator: float,
        scale_mode: str,
    ) -> DwgDrawing:
        """Persist a drawing's scale denominator + mode.

        The frontend also mirrors this in localStorage for instant feedback,
        but the DB value is the source of truth across devices and users -
        so a takeoff calibrated on a desktop reads correctly when the same
        drawing is opened on a tablet.
        """
        drawing = await self.get_drawing(drawing_id)
        await self.drawing_repo.update_fields(
            drawing_id,
            scale_denominator=scale_denominator,
            scale_mode=scale_mode,
        )
        await self.session.refresh(drawing)
        return drawing

    async def delete_drawing(self, drawing_id: uuid.UUID) -> None:
        """Delete a drawing and all associated files (upload, entities, thumbnails)."""
        drawing = await self.get_drawing(drawing_id)

        # Remove the uploaded drawing file
        if drawing.file_path and os.path.exists(drawing.file_path):
            try:
                os.remove(drawing.file_path)
            except OSError:
                logger.warning("Could not delete file: %s", drawing.file_path)

        # Remove entities and thumbnail files for all versions
        versions = await self.version_repo.list_for_drawing(drawing_id)
        entities_dir = _get_entities_dir()
        thumb_dir = os.path.join(_dwg_data_base(), "dwg_thumbnails")
        for version in versions:
            if version.entities_key:
                ent_path = os.path.join(entities_dir, version.entities_key)
                if os.path.exists(ent_path):
                    try:
                        os.remove(ent_path)
                    except OSError:
                        logger.warning("Could not delete entities file: %s", ent_path)

        # Remove thumbnail file referenced by the drawing
        if drawing.thumbnail_key:
            thumb_path = os.path.join(thumb_dir, drawing.thumbnail_key)
            if os.path.exists(thumb_path):
                try:
                    os.remove(thumb_path)
                except OSError:
                    logger.warning("Could not delete thumbnail file: %s", thumb_path)

        await self.drawing_repo.delete(drawing_id)
        logger.info("Drawing deleted: %s", drawing_id)

    # ── Drawing version & entities ──────────────────────────────────────

    async def get_latest_version(self, drawing_id: uuid.UUID) -> DwgDrawingVersion | None:
        """Get the latest version for a drawing.

        Performs a one-time, fail-soft units backfill on the read path:
        legacy/seeded drawings were stored with ``units == null`` (and
        sometimes ``extents == {}``) which forced a 1.0 scale factor and
        made millimetre drawings read 1000x too large (BUG-D-TKC-002c).
        When the unit is unknown we recover extents from the stored
        entities, infer the unit (a >=1000-unit drawing is almost certainly
        in mm) and persist both onto the version row so the API and BOQ
        push see real-world units thereafter.
        """
        version = await self.version_repo.get_latest_for_drawing(drawing_id)
        if version is not None:
            await self._backfill_units_if_unknown(version)
        return version

    async def _backfill_units_if_unknown(self, version: DwgDrawingVersion) -> None:
        """Lazily infer + persist units/extents when the version has none.

        Fail-soft: any error here is logged and swallowed so a read never
        breaks. Only runs when ``units`` is unknown (null/"unitless"), so a
        drawing whose unit was resolved at parse time is left untouched.
        """
        if version.units not in (None, "unitless"):
            return
        try:
            from app.modules.dwg_takeoff.ddc_dwg_parser import infer_units_from_extents

            extents = version.extents if isinstance(version.extents, dict) else {}
            # Recover a bounding box from the stored entities when the row
            # never persisted one (the flagship demo was seeded that way).
            if not extents or not all(k in extents for k in ("min_x", "min_y", "max_x", "max_y")):
                raw = await self._load_raw_entities(version)
                computed = _extents_from_raw_entities(raw)
                if computed is not None:
                    extents = computed

            inferred = infer_units_from_extents(extents)
            updates: dict[str, object] = {}
            if extents and extents != version.extents:
                updates["extents"] = extents
            if inferred is not None and inferred != version.units:
                updates["units"] = inferred
            if not updates:
                return

            # Persist with a bulk UPDATE that does NOT synchronize/expire the
            # session. ``DwgDrawingVersionRepository.update_fields`` calls
            # ``session.expire_all()``, which would also expire the router's
            # already-loaded ``DwgDrawing`` row; a later attribute access while
            # serializing the response would then attempt a lazy load on the
            # sync path and raise MissingGreenlet, 500-ing the whole read
            # (BUG-D-TKC-002d). We update in place and mirror the new values
            # onto the live object so the response and BOQ push see them.
            from sqlalchemy import update as sa_update

            await self.session.execute(
                sa_update(DwgDrawingVersion)
                .where(DwgDrawingVersion.id == version.id)
                .values(**updates)
                .execution_options(synchronize_session=False)
            )
            await self.session.flush()
            for field, value in updates.items():
                setattr(version, field, value)
            logger.info(
                "Backfilled units=%s extents on drawing version %s (was unitless)",
                version.units,
                version.id,
            )
        except Exception:  # noqa: BLE001 - backfill is advisory, never break the read
            logger.warning(
                "Units backfill failed for drawing version %s",
                version.id,
                exc_info=True,
            )

    async def _load_raw_entities(self, version: DwgDrawingVersion) -> list[dict[str, Any]]:
        """Load the stored (un-normalised) entity records for a version.

        Returns the raw ``{entity_type, geometry_data: {…}}`` list straight
        from disk (no frontend flattening) so extents can be recomputed.
        """
        if version.entities_key is None:
            return []
        # Mirror get_entities: resolve through the multi-root read fallback so a
        # blob written under a prior data-dir resolution is still found (the
        # units/extents backfill must not silently no-op on back-compat roots).
        entities_path = _dwg_existing_path("dwg_entities", version.entities_key)
        if entities_path is None:
            return []
        with open(entities_path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []

    # ── Revision compare (Item 17) ──────────────────────────────────────

    async def list_drawing_versions(self, drawing_id: uuid.UUID) -> list[DwgDrawingVersion]:
        """List all parsed versions for a drawing (newest first).

        Raises 404 if the drawing does not exist so the router can gate
        access on the resolved drawing before exposing the version list.
        """
        await self.get_drawing(drawing_id)
        return await self.version_repo.list_for_drawing(drawing_id)

    async def compare_drawing_versions(
        self,
        drawing_id: uuid.UUID,
        from_version_id: uuid.UUID,
        to_version_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Compare two versions of a drawing and return the diff payload.

        Computes:

        * **Entity diff** - per-layer entity-count changes between the two
          versions' stored layer profiles (entities carry no stable
          cross-parse identity).
        * **Annotation delta** - added / removed / modified annotations
          keyed by ``drawing_version_id``, with a money cost impact for
          any linked-to-BOQ annotation whose measured value changed.

        Both versions must belong to ``drawing_id`` (404 otherwise) so a
        caller cannot diff a version that lives under a foreign drawing.
        """
        drawing = await self.get_drawing(drawing_id)

        from_version = await self.version_repo.get_by_id(from_version_id)
        to_version = await self.version_repo.get_by_id(to_version_id)
        for version in (from_version, to_version):
            if version is None or version.drawing_id != drawing_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Drawing version not found",
                )
        assert from_version is not None  # noqa: S101 - narrowed by the loop above
        assert to_version is not None  # noqa: S101

        entity_rows = _compute_entity_diff(from_version.layers, to_version.layers)
        annotation_rows = await self._compute_annotation_delta(
            drawing.project_id,
            from_version_id,
            to_version_id,
        )
        summary = _summarize_diff(
            entity_rows,
            annotation_rows,
            from_entity_count=from_version.entity_count,
            to_entity_count=to_version.entity_count,
        )

        return {
            "drawing_id": drawing_id,
            "from_version_id": from_version.id,
            "from_version_number": from_version.version_number,
            "to_version_id": to_version.id,
            "to_version_number": to_version.version_number,
            "entity_rows": entity_rows,
            "annotation_rows": annotation_rows,
            "summary": summary,
        }

    async def compare_drawing_pair(
        self,
        project_id: uuid.UUID,
        from_drawing_id: uuid.UUID,
        to_drawing_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Compare two INDEPENDENT drawings in a project and return the diff.

        Where :meth:`compare_drawing_versions` diffs two parsed versions of
        ONE drawing, this diffs the LATEST version of two separately
        uploaded drawings - the user picks (or uploads) a second drawing as
        the comparison target. The diff core (:func:`_compute_entity_diff`
        plus :meth:`_compute_annotation_delta`) is identical; only the two
        sides are resolved from different drawings, so there is no
        same-drawing guard.

        Both drawings must belong to ``project_id`` (a missing or
        foreign-project drawing 404s the same way) so a compare never
        crosses tenants or blends two base currencies. Each drawing must
        have at least one parsed version (404 otherwise).

        Note on annotation matching: annotations are matched by
        ``metadata.compare_key``; two independently uploaded drawings rarely
        share keys, so annotation rows mostly read as added/removed and the
        per-layer entity diff is the primary signal - identical to how the
        PDF two-document compare behaves.

        Returns the same payload shape as :meth:`compare_drawing_versions`,
        additionally carrying ``from_drawing_id`` / ``to_drawing_id`` so the
        UI can label both sides. ``drawing_id`` stays populated (the
        baseline drawing) for back-compat.
        """
        from_drawing = await self.get_drawing(from_drawing_id)
        to_drawing = await self.get_drawing(to_drawing_id)
        for drawing in (from_drawing, to_drawing):
            if drawing.project_id != project_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Drawing not found",
                )

        from_version = await self.get_latest_version(from_drawing_id)
        to_version = await self.get_latest_version(to_drawing_id)
        for version in (from_version, to_version):
            if version is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Drawing has no parsed version to compare",
                )
        assert from_version is not None  # noqa: S101 - narrowed by the loop above
        assert to_version is not None  # noqa: S101

        entity_rows = _compute_entity_diff(from_version.layers, to_version.layers)
        annotation_rows = await self._compute_annotation_delta(
            project_id,
            from_version.id,
            to_version.id,
        )
        summary = _summarize_diff(
            entity_rows,
            annotation_rows,
            from_entity_count=from_version.entity_count,
            to_entity_count=to_version.entity_count,
        )

        return {
            "drawing_id": from_drawing_id,
            "from_drawing_id": from_drawing_id,
            "to_drawing_id": to_drawing_id,
            "from_version_id": from_version.id,
            "from_version_number": from_version.version_number,
            "to_version_id": to_version.id,
            "to_version_number": to_version.version_number,
            "entity_rows": entity_rows,
            "annotation_rows": annotation_rows,
            "summary": summary,
        }

    async def _compute_annotation_delta(
        self,
        project_id: uuid.UUID,
        from_version_id: uuid.UUID,
        to_version_id: uuid.UUID,
    ) -> list[dict[str, Any]]:
        """Diff annotations across two versions, with BOQ cost impact.

        Annotations are matched by ``metadata.compare_key`` when present
        (a stable user/import key carried across re-draws), otherwise by
        their own id within each version. Because a re-uploaded drawing
        gets fresh annotation rows, the realistic match key is the
        ``compare_key`` an importer stamps; absent that, an annotation
        present only in one version is reported as added/removed.

        For an annotation that exists in BOTH versions and is linked to a
        BOQ position, the money impact ``(new - old) * unit_rate`` is
        resolved in the project's base currency via the BOQ service.
        """
        from_annos = await self.annotation_repo.list_for_version(from_version_id)
        to_annos = await self.annotation_repo.list_for_version(to_version_id)

        def _key(ann: "DwgAnnotation") -> str:
            meta = ann.metadata_ or {}
            ck = meta.get("compare_key") if isinstance(meta, dict) else None
            return str(ck).strip() if ck else f"id:{ann.id}"

        from_by_key = {_key(a): a for a in from_annos}
        to_by_key = {_key(a): a for a in to_annos}

        # Lazy per-position currency/rate cache so we never re-resolve the
        # same BOQ position (and its project FX) twice within one compare.
        rate_cache: dict[str, tuple[str | None, str | None]] = {}

        async def _rate_and_currency(position_id: str | None) -> tuple[str | None, str | None]:
            if not position_id:
                return None, None
            if position_id in rate_cache:
                return rate_cache[position_id]
            result = await self._resolve_position_rate(position_id, project_id)
            rate_cache[position_id] = result
            return result

        rows: list[dict[str, Any]] = []

        for key in sorted(set(from_by_key) | set(to_by_key)):
            old_ann = from_by_key.get(key)
            new_ann = to_by_key.get(key)

            if old_ann is not None and new_ann is None:
                rows.append(
                    {
                        "change_type": "removed",
                        "annotation_id": str(old_ann.id),
                        "annotation_type": old_ann.annotation_type,
                        "label": _annotation_label(old_ann),
                        "layer_name": old_ann.layer_name,
                        "old_measurement": _to_float(old_ann.measurement_value),
                        "new_measurement": None,
                        "measurement_unit": old_ann.measurement_unit,
                        "linked_boq_position_id": old_ann.linked_boq_position_id,
                        "cost_impact": None,
                        "cost_currency": None,
                    }
                )
                continue

            if old_ann is None and new_ann is not None:
                rows.append(
                    {
                        "change_type": "added",
                        "annotation_id": str(new_ann.id),
                        "annotation_type": new_ann.annotation_type,
                        "label": _annotation_label(new_ann),
                        "layer_name": new_ann.layer_name,
                        "old_measurement": None,
                        "new_measurement": _to_float(new_ann.measurement_value),
                        "measurement_unit": new_ann.measurement_unit,
                        "linked_boq_position_id": new_ann.linked_boq_position_id,
                        "cost_impact": None,
                        "cost_currency": None,
                    }
                )
                continue

            # Present in both - detect a measurement change and price it.
            assert old_ann is not None and new_ann is not None  # noqa: S101
            old_val = _to_float(old_ann.measurement_value)
            new_val = _to_float(new_ann.measurement_value)
            changed = old_val != new_val
            position_id = new_ann.linked_boq_position_id or old_ann.linked_boq_position_id
            cost_impact: str | None = None
            cost_currency: str | None = None
            if changed and position_id:
                rate, cost_currency = await _rate_and_currency(position_id)
                cost_impact = _calculate_cost_impact(
                    old_value=old_val,
                    new_value=new_val,
                    unit_rate=rate,
                )
            rows.append(
                {
                    "change_type": "modified" if changed else "unchanged",
                    "annotation_id": str(new_ann.id),
                    "annotation_type": new_ann.annotation_type,
                    "label": _annotation_label(new_ann),
                    "layer_name": new_ann.layer_name,
                    "old_measurement": old_val,
                    "new_measurement": new_val,
                    "measurement_unit": new_ann.measurement_unit or old_ann.measurement_unit,
                    "linked_boq_position_id": position_id,
                    "cost_impact": cost_impact,
                    "cost_currency": cost_currency if cost_impact is not None else None,
                }
            )

        return rows

    async def _resolve_position_rate(
        self,
        position_id: str,
        project_id: uuid.UUID,
    ) -> tuple[str | None, str | None]:
        """Resolve ``(unit_rate, base_currency)`` for a BOQ position.

        The position must belong to ``project_id`` (cross-tenant safety:
        a foreign-project position is treated as "no rate" so a compare
        never prices an annotation against another tenant's estimate).
        Best-effort: any lookup failure returns ``(None, None)`` so the
        compare degrades to "no cost shown" rather than a 500.
        """
        try:
            position_uuid = uuid.UUID(str(position_id))
        except (ValueError, TypeError, AttributeError):
            return None, None

        try:
            from app.modules.boq.service import BOQService

            boq_service = BOQService(self.session)
            position = await boq_service.position_repo.get_by_id(position_uuid)
            if position is None:
                return None, None
            boq = await boq_service.get_boq(position.boq_id)
            if str(boq.project_id) != str(project_id):
                # Cross-tenant link - never price against it.
                return None, None
            base_currency = await boq_service._resolve_project_currency(position.boq_id)  # noqa: SLF001
            return str(position.unit_rate), (base_currency or None)
        except HTTPException:
            return None, None
        except Exception:  # noqa: BLE001 - pricing is advisory, never break the compare
            logger.debug("Cost-impact rate lookup failed for position %s", position_id, exc_info=True)
            return None, None

    async def create_variation_from_versions(
        self,
        drawing_id: uuid.UUID,
        from_version_id: uuid.UUID,
        to_version_id: uuid.UUID,
        *,
        title: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Turn a drawing revision delta into a draft VariationRequest.

        The deterministic :meth:`compare_drawing_versions` is the single
        source of truth - this method does NOT recompute the diff, it
        calls compare and shapes its summary into a controlled-change
        record. A *draft* VariationRequest is created (never submitted or
        approved): AI/automation proposes the change, a human confirms it
        in the variations workflow.

        The variation is classified ``scope_change`` and carries the net
        cost impact from the compare in the project's base currency.
        Provenance (the drawing id, the version pair, the changed linked
        annotation ids, the raw net impact) is stamped into
        ``metadata.source = "dwg_revision_compare"`` so the handoff is
        traceable and idempotent-friendly (the version pair is unique).

        Returns ``{variation_request_id, code, estimated_cost_impact,
        currency}``.
        """
        diff = await self.compare_drawing_versions(drawing_id, from_version_id, to_version_id)
        drawing = await self.get_drawing(drawing_id)

        summary = diff.get("summary") or {}
        entity_tally = summary.get("entities") or {}
        annotation_tally = summary.get("annotations") or {}
        net_impact_raw = summary.get("net_cost_impact")
        currency = summary.get("cost_currency") or ""

        changed_annotation_ids = [
            row["annotation_id"] for row in diff.get("annotation_rows", []) if row.get("change_type") == "modified"
        ]

        try:
            estimated_cost_impact = Decimal(str(net_impact_raw)) if net_impact_raw not in (None, "") else Decimal("0")
        except (InvalidOperation, ValueError, TypeError):
            estimated_cost_impact = Decimal("0")

        from_v = diff.get("from_version_number")
        to_v = diff.get("to_version_number")
        resolved_title = title or f"Drawing revision {drawing.name} v{from_v}->v{to_v}"
        description = _build_revision_narrative(
            entity_tally=entity_tally,
            annotation_tally=annotation_tally,
            changed_linked_count=len(
                [
                    row
                    for row in diff.get("annotation_rows", [])
                    if row.get("change_type") == "modified" and row.get("linked_boq_position_id")
                ]
            ),
        )

        # Lazy import (mirrors the BOQService import at _resolve_position_rate)
        # so the dwg_takeoff module load never depends on the variations
        # module being importable at import time.
        from app.modules.variations.schemas import VariationRequestCreate
        from app.modules.variations.service import VariationsService

        vr_create = VariationRequestCreate(
            project_id=drawing.project_id,
            title=resolved_title[:500],
            description=description[:20000],
            classification="scope_change",
            estimated_cost_impact=estimated_cost_impact,
            estimated_schedule_days=0,
            currency=currency[:10],
            status="draft",
            metadata={
                "source": "dwg_revision_compare",
                "drawing_id": str(drawing_id),
                "from_version_id": str(from_version_id),
                "to_version_id": str(to_version_id),
                "changed_annotation_ids": changed_annotation_ids,
                "net_cost_impact": str(estimated_cost_impact),
            },
        )
        variations_service = VariationsService(self.session)
        vr = await variations_service.create_request(vr_create, user_id=user_id)

        return {
            "variation_request_id": vr.id,
            "code": vr.code,
            "estimated_cost_impact": str(estimated_cost_impact),
            "currency": currency,
        }

    async def create_variation_from_drawing_pair(
        self,
        project_id: uuid.UUID,
        from_drawing_id: uuid.UUID,
        to_drawing_id: uuid.UUID,
        *,
        title: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Turn a drawing-vs-drawing delta into a draft VariationRequest.

        Mirrors :meth:`create_variation_from_versions` for the drawing-pair
        path: the deterministic :meth:`compare_drawing_pair` is the single
        source of truth (the diff is not recomputed here), and a *draft*
        VariationRequest is created (never submitted) so a human confirms it
        in the variations workflow. The variation is classified
        ``scope_change`` and carries the net cost impact in the project's
        base currency.

        Provenance is stamped into
        ``metadata.source = "dwg_drawing_pair_compare"`` with both drawing
        ids and the changed linked-annotation ids so the handoff is
        traceable.

        Returns ``{variation_request_id, code, estimated_cost_impact,
        currency}``.
        """
        diff = await self.compare_drawing_pair(project_id, from_drawing_id, to_drawing_id)
        from_drawing = await self.get_drawing(from_drawing_id)
        to_drawing = await self.get_drawing(to_drawing_id)

        summary = diff.get("summary") or {}
        entity_tally = summary.get("entities") or {}
        annotation_tally = summary.get("annotations") or {}
        net_impact_raw = summary.get("net_cost_impact")
        currency = summary.get("cost_currency") or ""

        changed_annotation_ids = [
            row["annotation_id"] for row in diff.get("annotation_rows", []) if row.get("change_type") == "modified"
        ]

        try:
            estimated_cost_impact = Decimal(str(net_impact_raw)) if net_impact_raw not in (None, "") else Decimal("0")
        except (InvalidOperation, ValueError, TypeError):
            estimated_cost_impact = Decimal("0")

        resolved_title = title or f"Drawing compare {from_drawing.name} -> {to_drawing.name}"
        description = _build_revision_narrative(
            entity_tally=entity_tally,
            annotation_tally=annotation_tally,
            changed_linked_count=len(
                [
                    row
                    for row in diff.get("annotation_rows", [])
                    if row.get("change_type") == "modified" and row.get("linked_boq_position_id")
                ]
            ),
        )

        # Lazy import (mirrors create_variation_from_versions) so the
        # dwg_takeoff module load never depends on the variations module
        # being importable at import time.
        from app.modules.variations.schemas import VariationRequestCreate
        from app.modules.variations.service import VariationsService

        vr_create = VariationRequestCreate(
            project_id=project_id,
            title=resolved_title[:500],
            description=description[:20000],
            classification="scope_change",
            estimated_cost_impact=estimated_cost_impact,
            estimated_schedule_days=0,
            currency=currency[:10],
            status="draft",
            metadata={
                "source": "dwg_drawing_pair_compare",
                "from_drawing_id": str(from_drawing_id),
                "to_drawing_id": str(to_drawing_id),
                "changed_annotation_ids": changed_annotation_ids,
                "net_cost_impact": str(estimated_cost_impact),
            },
        )
        variations_service = VariationsService(self.session)
        vr = await variations_service.create_request(vr_create, user_id=user_id)

        return {
            "variation_request_id": vr.id,
            "code": vr.code,
            "estimated_cost_impact": str(estimated_cost_impact),
            "currency": currency,
        }

    async def get_entities(
        self,
        drawing_id: uuid.UUID,
        *,
        visible_layers: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Load parsed entities from storage, optionally filtered by visible layers."""
        version = await self.version_repo.get_latest_for_drawing(drawing_id)
        if version is None or version.entities_key is None:
            return []

        entities_path = _dwg_existing_path("dwg_entities", version.entities_key)
        if entities_path is None:
            return []

        try:
            with open(entities_path, encoding="utf-8") as f:
                entities = json.load(f)
        except FileNotFoundError:
            logger.warning("Entities file missing for drawing %s: %s", drawing_id, entities_path)
            return []
        except json.JSONDecodeError as exc:
            logger.error(
                "Corrupt entities JSON for drawing %s: %s",
                drawing_id,
                exc,
            )
            return []
        except Exception:
            logger.exception("Failed to load entities for drawing %s", drawing_id)
            return []

        # Prefer the version's fit extents when present so LibreDWG outlier
        # coordinates (absorbed into stored JSON before clipping existed) do
        # not force the canvas zoom to ~0%.
        extents = version.extents if isinstance(version.extents, dict) else None
        if extents and all(k in extents for k in ("min_x", "min_y", "max_x", "max_y")):
            try:
                from app.modules.dwg_takeoff import mac_dwg

                clipped = [
                    e for e in entities if mac_dwg.entity_intersects_extents(e, extents)
                ]
                if len(clipped) >= max(50, int(len(entities) * 0.15)):
                    entities = clipped
            except Exception:  # noqa: BLE001 - never fail entity load on clip
                logger.debug("Entity extent clip skipped for %s", drawing_id, exc_info=True)

        # Filter by visible layers if specified. Always keep TEXT/MTEXT layers
        # that exist on disk but are missing from a stale layer catalog (common
        # after LibreDWG re-parses that add labels without rewriting version.layers).
        if visible_layers is not None:
            visible_set = set(visible_layers)
            catalog = {
                str(layer.get("name") or "")
                for layer in (
                    version.layers
                    if isinstance(version.layers, list)
                    else (version.layers or {}).values()  # type: ignore[union-attr]
                    if isinstance(version.layers, dict)
                    else []
                )
                if isinstance(layer, dict)
            }
            file_layers = {str(e.get("layer") or "0") for e in entities}
            for name in file_layers - catalog:
                if name.upper() in {"TEXT", "MTEXT"} or name.upper().startswith("TEXT"):
                    visible_set.add(name)
            entities = [e for e in entities if e.get("layer", "0") in visible_set]

        # Normalize entity format for frontend consumption:
        # Backend stores {entity_type, geometry_data: {…}} but frontend
        # expects flat {type, id, start, end, vertices, …} structure.
        return [_normalize_entity(e, i) for i, e in enumerate(entities)]

    async def get_thumbnail_svg(self, drawing_id: uuid.UUID) -> str | None:
        """Load SVG thumbnail content for a drawing."""
        drawing = await self.get_drawing(drawing_id)
        if not drawing.thumbnail_key:
            return None

        thumb_path = _dwg_existing_path("dwg_thumbnails", drawing.thumbnail_key)
        if thumb_path is None:
            return None

        try:
            with open(thumb_path, encoding="utf-8") as f:
                return f.read()
        except Exception:
            logger.exception("Failed to load thumbnail for drawing %s", drawing_id)
            return None

    async def update_layer_visibility(
        self,
        drawing_id: uuid.UUID,
        layer_updates: dict[str, bool],
    ) -> DwgDrawingVersion | None:
        """Toggle layer visibility in the latest drawing version."""
        version = await self.version_repo.get_latest_for_drawing(drawing_id)
        if version is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No drawing version found",
            )

        # Normalize layers to list format (legacy data may be stored as dict)
        raw = version.layers
        if isinstance(raw, dict):
            layers_list = list(raw.values()) if raw else []
        else:
            layers_list = list(raw) if raw else []

        for layer_info in layers_list:
            name = layer_info.get("name", "")
            if name in layer_updates:
                layer_info["visible"] = layer_updates[name]

        await self.version_repo.update_fields(version.id, layers=layers_list)
        await self.session.refresh(version)
        return version

    # ── Annotation CRUD ─────────────────────────────────────────────────

    async def create_annotation(
        self,
        data: DwgAnnotationCreate,
        user_id: str,
    ) -> DwgAnnotation:
        """Create a new annotation on a drawing."""
        # Verify drawing exists
        await self.get_drawing(data.drawing_id)

        item = DwgAnnotation(
            project_id=data.project_id,
            drawing_id=data.drawing_id,
            drawing_version_id=data.drawing_version_id,
            annotation_type=data.annotation_type,
            geometry=data.geometry,
            text=data.text,
            color=data.color,
            line_width=data.line_width,
            thickness=data.thickness,
            layer_name=data.layer_name,
            measurement_value=data.measurement_value,
            measurement_unit=data.measurement_unit,
            scale_override=data.scale_override,
            linked_boq_position_id=data.linked_boq_position_id,
            linked_task_id=data.linked_task_id,
            linked_punch_item_id=data.linked_punch_item_id,
            created_by=user_id,
            metadata_=data.metadata,
        )
        item = await self.annotation_repo.create(item)
        logger.info(
            "Annotation created: %s type=%s drawing=%s",
            item.id,
            data.annotation_type,
            data.drawing_id,
        )
        return item

    async def get_annotation(self, annotation_id: uuid.UUID) -> DwgAnnotation:
        """Get annotation by ID. Raises 404 if not found."""
        item = await self.annotation_repo.get_by_id(annotation_id)
        if item is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Annotation not found",
            )
        return item

    async def list_annotations(
        self,
        drawing_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 200,
        annotation_type: str | None = None,
    ) -> tuple[list[DwgAnnotation], int]:
        """List annotations for a drawing with pagination and filters."""
        return await self.annotation_repo.list_for_drawing(
            drawing_id,
            offset=offset,
            limit=limit,
            annotation_type=annotation_type,
        )

    async def update_annotation(
        self,
        annotation_id: uuid.UUID,
        data: DwgAnnotationUpdate,
    ) -> DwgAnnotation:
        """Update annotation fields."""
        item = await self.get_annotation(annotation_id)

        fields = data.model_dump(exclude_unset=True)
        if "metadata" in fields:
            fields["metadata_"] = fields.pop("metadata")

        if not fields:
            return item

        await self.annotation_repo.update_fields(annotation_id, **fields)
        await self.session.refresh(item)

        logger.info("Annotation updated: %s (fields=%s)", annotation_id, list(fields.keys()))
        return item

    async def delete_annotation(self, annotation_id: uuid.UUID) -> None:
        """Delete an annotation."""
        await self.get_annotation(annotation_id)  # Raises 404 if not found
        await self.annotation_repo.delete(annotation_id)
        logger.info("Annotation deleted: %s", annotation_id)

    async def link_annotation_to_boq(
        self,
        annotation_id: uuid.UUID,
        position_id: str,
        *,
        push_quantity: bool = False,
    ) -> DwgAnnotation:
        """Link an annotation to a BOQ position.

        Estimation-cluster wave (2026-05-28) - opt-in ``push_quantity``.
        When true, the annotation's measured value is copied into the
        target BOQ position's ``quantity`` and the position total is
        recomputed. An annotation with no usable value is a no-op.
        """
        item = await self.get_annotation(annotation_id)

        # Cross-tenant safety: the target BOQ position must live in the SAME
        # project as the annotation. ``position_id`` arrives from the request
        # body and the router only authorises the annotation's own project, so
        # without this gate a caller could link to - and, with push_quantity,
        # overwrite the quantity of - a foreign tenant's BOQ position.
        await self._assert_position_in_project(position_id, item.project_id)

        await self.annotation_repo.update_fields(annotation_id, linked_boq_position_id=position_id)
        await self.session.refresh(item)

        logger.info("Annotation %s linked to BOQ position %s", annotation_id, position_id)

        if push_quantity:
            await self._push_quantity_to_position(position_id, item)
        return item

    async def _assert_position_in_project(
        self,
        position_id: str,
        project_id: uuid.UUID,
    ) -> None:
        """Raise 404 unless ``position_id`` belongs to a BOQ in ``project_id``.

        Mirrors the read-side guard in :meth:`_resolve_position_rate`: a
        foreign-project (or missing) position is reported as "not found" so the
        endpoint never confirms the existence of, links to, or writes into
        another tenant's BOQ position.
        """
        try:
            position_uuid = uuid.UUID(str(position_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise HTTPException(status_code=404, detail="BOQ position not found") from exc

        from app.modules.boq.service import BOQService

        boq_service = BOQService(self.session)
        position = await boq_service.position_repo.get_by_id(position_uuid)
        if position is None:
            raise HTTPException(status_code=404, detail="BOQ position not found")
        try:
            boq = await boq_service.get_boq(position.boq_id)
        except HTTPException as exc:
            raise HTTPException(status_code=404, detail="BOQ position not found") from exc
        if boq is None or str(boq.project_id) != str(project_id):
            raise HTTPException(status_code=404, detail="BOQ position not found")

    async def _push_quantity_to_position(self, position_id: str, annotation: DwgAnnotation) -> None:
        """Copy an annotation's value into a BOQ position's quantity.

        Reuses the takeoff module's :func:`_pick_takeoff_value` value
        picker and the BOQ module's canonical total-recompute path. The
        ``DwgAnnotation`` ORM only carries a scalar ``measurement_value``
        (no separate volume/count columns), so we adapt it to the shape
        the picker expects. A ``None`` picked value is a no-op - we never
        zero an existing BOQ quantity from an annotation with no number.
        """
        from types import SimpleNamespace

        from app.modules.takeoff.service import _pick_takeoff_value

        adapter = SimpleNamespace(
            type=annotation.annotation_type,
            measurement_value=annotation.measurement_value,
            volume=None,
            count_value=None,
            id=annotation.id,
        )
        value = _pick_takeoff_value(adapter)
        if value is None:
            logger.info(
                "push_quantity: annotation %s has no usable value - leaving BOQ position %s untouched",
                annotation.id,
                position_id,
            )
            return

        from app.modules.boq.service import BOQService

        try:
            position_uuid = uuid.UUID(str(position_id))
        except (ValueError, AttributeError):
            logger.warning("push_quantity: BOQ position id %r is not a UUID - skipping", position_id)
            return

        boq_service = BOQService(self.session)
        position = await boq_service.position_repo.get_by_id(position_uuid)
        if position is None:
            logger.warning("push_quantity: BOQ position %s not found - skipping", position_id)
            return

        await boq_service.position_repo.update_fields(position.id, quantity=str(value))
        await self.session.refresh(position)
        await boq_service._recompute_position_total(position)  # noqa: SLF001 - reuse canonical recompute path
        logger.info("push_quantity: BOQ position %s quantity set to %s", position_id, value)

    # ── Pins (task/punchlist) ───────────────────────────────────────────

    async def get_pins(self, drawing_id: uuid.UUID) -> list[DwgAnnotation]:
        """Get annotations linked to tasks or punchlist items for a drawing."""
        return await self.annotation_repo.list_pins_for_drawing(drawing_id)

    # ── Entity Groups (RFC 11) ──────────────────────────────────────────

    async def create_entity_group(
        self,
        data: DwgEntityGroupCreate,
        user_id: str,
    ) -> DwgEntityGroup:
        """Create a saved group of DWG entity ids on a drawing."""
        await self.get_drawing(data.drawing_id)

        item = DwgEntityGroup(
            drawing_id=data.drawing_id,
            name=data.name,
            entity_ids=list(data.entity_ids),
            metadata_=data.metadata,
            created_by=user_id,
        )
        item = await self.group_repo.create(item)
        logger.info(
            "Entity group created: %s drawing=%s n=%d",
            item.id,
            data.drawing_id,
            len(data.entity_ids),
        )
        return item

    async def get_entity_group(self, group_id: uuid.UUID) -> DwgEntityGroup:
        """Get entity group by ID. Raises 404 if not found."""
        item = await self.group_repo.get_by_id(group_id)
        if item is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Entity group not found",
            )
        return item

    async def list_entity_groups(
        self,
        drawing_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 200,
    ) -> tuple[list[DwgEntityGroup], int]:
        """List saved entity groups for a drawing."""
        return await self.group_repo.list_for_drawing(
            drawing_id,
            offset=offset,
            limit=limit,
        )

    async def delete_entity_group(self, group_id: uuid.UUID) -> None:
        """Delete an entity group."""
        await self.get_entity_group(group_id)
        await self.group_repo.delete(group_id)
        logger.info("Entity group deleted: %s", group_id)

    # ── Offline readiness (R3 #9) ───────────────────────────────────────

    @staticmethod
    def get_offline_readiness() -> dict[str, Any]:
        """Probe local DWG converter availability.

        Ready when any of these are present: DDC ``DwgExporter``, ODA File
        Converter, or LibreDWG ``dwg2SVG`` / ``dwgread``. DXF files already
        work without any of them. Returns a dict matching
        :class:`DwgOfflineReadinessResponse`.
        """
        try:
            from app.modules.boq.cad_import import find_converter

            converter = find_converter("dwg")
        except ImportError:
            converter = None

        if converter is not None:
            return {
                "ready": True,
                "converter_available": True,
                "version": getattr(converter, "name", None),
                "message": "DWG conversion runs locally via DDC DwgExporter.",
            }

        try:
            from app.modules.dwg_takeoff import mac_dwg

            oda = mac_dwg.find_oda_file_converter()
            if oda is not None:
                return {
                    "ready": True,
                    "converter_available": True,
                    "version": oda.name,
                    "message": "DWG conversion runs locally via ODA File Converter.",
                }
            libre = mac_dwg.find_libredwg_dwg2svg() or mac_dwg.find_libredwg_dwgread()
            if libre is not None:
                return {
                    "ready": True,
                    "converter_available": True,
                    "version": libre.name,
                    "message": (
                        "DWG opens via LibreDWG as a preview (blocks/sheets may be "
                        "incomplete). Install ODA File Converter from "
                        f"{mac_dwg.oda_download_url()} or upload a DXF for accurate "
                        "floor plans and layer names."
                    ),
                }
        except Exception:  # noqa: BLE001 - probe must never raise
            logger.debug("macOS/POSIX DWG backend probe failed", exc_info=True)

        return {
            "ready": False,
            "converter_available": False,
            "version": None,
            "message": (
                "Install a DWG reader to enable offline .dwg conversion. "
                "DXF files already work without it."
            ),
        }


async def _run_dwg_conversion_in_background(
    drawing_id: uuid.UUID,
    file_path: str,
) -> None:
    """Detached DDC conversion task with its own DB session.

    Decouples the slow / occasionally-hanging DDC DwgExporter
    subprocess from the HTTP upload request. The request returns
    immediately with status=uploaded and the conversion progresses
    in the background, persisting status transitions (uploaded →
    processing → ready/error) on a fresh AsyncSession.

    Without this isolation, a single DDC crash or timeout pinned a
    uvicorn worker for up to 120 s and the next 5+ DWG uploads
    queued behind it eventually 500-d on the client side. The
    upload row is committed before this task is spawned so the
    fresh session here can find the row.
    """
    async with async_session_factory() as session:
        try:
            svc = DwgTakeoffService(session)
            await svc._handle_dwg(drawing_id, file_path)
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception(
                "Background DDC conversion failed for drawing %s",
                drawing_id,
            )

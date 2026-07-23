# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Offline raster candidate detection for PDF takeoff (issue #194).

This is the raster twin of :mod:`app.modules.takeoff.recognize`. The vector
recognizer reads a page's drawing layer (``page.get_drawings()``); on a SCANNED
plan that layer is empty, so it correctly returns nothing. This module instead
looks at the rendered raster image of the page with OpenCV and proposes the same
candidate shape:

* large light regions sealed by dark walls -> ``area`` candidates (rooms),
* long straight wall edges -> ``distance`` (length) candidates,
* (count detection is intentionally omitted on scans, see below).

The detection runs in IMAGE PIXEL space but every candidate is returned in PDF
POINT space, the same coordinate space the canvas stores measurements in, so the
shapes drop straight onto the viewer with no further transform. The mapping is a
simple per-axis scale from the rendered pixmap size to the page size in points.

Raster detection is inherently less certain than reading clean vector geometry,
so confidences here are deliberately lower than the vector path (rooms ~0.45 to
0.60, walls ~0.40 to 0.50). Every candidate carries an honest ``reason`` ending
in "(verify)" so the user confirms, edits or rejects it (CLAUDE.md rule 7:
AI-augmented, human-confirmed).

Count detection is skipped on purpose: repeated symbols (doors, fixtures) on a
low-contrast scan cluster unreliably and tend to produce noise, and the brief
for this module is to return a handful of good rooms rather than many shaky
boxes. The vector recognizer still handles counts when a drawing layer exists.

The module is pure (no DB, no FastAPI). ``cv2`` and ``numpy`` are imported at
module top on purpose: the *caller* imports this module lazily and catches
``ImportError``, so a default install without the ``cv`` extra never reaches
here. Every risky OpenCV call is wrapped so a degenerate image yields ``[]``
rather than raising.
"""

from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
import tempfile
from collections import defaultdict, deque
from typing import Any

import cv2
import numpy as np

# Room words commonly printed on architectural floor plans (OCR seed list).
_ROOM_TOKEN_RE = re.compile(
    r"(ROOM|CHAMBER|KITCHEN|DINING|LIVING|BATH|HALL|PORCH|PANTRY|SERVANT|"
    r"CLOSET|ALCOVE|STORES|COAT|LINEN|ROOF|BEDROOM|BED|PARKING|STAIRS?|OTS)",
    re.IGNORECASE,
)
_CAPTION_RE = re.compile(
    r"(relationship|apparent|extending|design|plan of|vista|pleasing)",
    re.IGNORECASE,
)

# ── tuning constants (settled empirically on the real scanned test plan) ─────
#
# All pixel thresholds are expressed relative to the rendered image so the
# module behaves the same whether the caller rendered at 100 or 200 DPI.

# Dilate dark ink slightly before sealing so thin scanned wall strokes form a
# continuous barrier, then CLOSE modest gaps (door leaves / scan breaks).
# OPEN is intentionally avoided: on floor plans it erodes partition walls and
# merges neighbouring rooms into one polygon.
_WALL_DILATE_ITER = 1
_WALL_CLOSE_KERNEL_PX = 7
_WALL_CLOSE_ITER = 1
# Axis-aligned Hough segments thicker than ink, used to bridge door openings
# without flooding whole rooms.
_WALL_HOUGH_THICKNESS_PX = 4
_WALL_HOUGH_ANGLE_TOL_DEG = 14.0
# Shrink the room mask slightly before contouring so the polygon hugs the
# inner wall face rather than the middle of the thickened wall stroke.
_ROOM_ERODE_PX = 2

# A room region must cover at least this fraction of the page to be kept. Below
# this it is almost always a text gap, a label box or scan speckle.
_ROOM_MIN_PAGE_FRAC = 0.003
# Named rooms may be smaller (baths / alcoves) after wall snapping.
_ROOM_MIN_PAGE_FRAC_NAMED = 0.0012
# Cap below a whole-page envelope. Open parking / podium decks are large; the
# old 12% cap discarded the real GFA plate and left only stall fragments.
_ROOM_MAX_PAGE_FRAC = 0.35
# Named OCR rooms (parking decks, open-plan) may fill more of the sheet.
_ROOM_MAX_PAGE_FRAC_NAMED = 0.55
# Connected-component accept ceiling (aligned with named max).
_ROOM_COMPONENT_MAX_FRAC = 0.55
# Connected components larger than this are candidates for watershed splitting
# through residual door openings — but only up to _ROOM_SPLIT_MAX_FRAC so
# large open decks keep one curved contour.
_ROOM_SPLIT_PAGE_FRAC = 0.040
_ROOM_SPLIT_MAX_FRAC = 0.12
# Distance-transform peak fraction used when splitting a large room blob.
# Higher = fewer seeds = less fragmentation through furniture / stair lines.
_ROOM_WATERSHED_PEAK = 0.30
# Douglas-Peucker simplification, as a fraction of the contour perimeter.
# Tight enough to track arches / wall jogs without following every ink speck.
_ROOM_APPROX_EPS_FRAC = 0.004
# Even tighter when the contour is clearly curved (many turns).
_ROOM_APPROX_EPS_CURVED = 0.0025
# A simplified room polygon with <= this many corners and a high bbox fill
# ("extent") is treated as a clean rectangle and scored a little higher.
_ROOM_RECT_MAX_VERTS = 12
_ROOM_RECT_MIN_EXTENT = 0.55
# Contour-to-minAreaRect fill ratio above which we snap to a clean rectangle.
_ROOM_RECT_MIN_SOLIDITY = 0.65
# Only force an axis-aligned box when the fill is this rectangular (otherwise
# arches / L-shapes / slanted walls keep their true contour).
_ROOM_AABB_EXTENT = 0.96
# Max vertices kept on a room polygon (canvas stays responsive on dense curves).
_ROOM_POLY_MAX_VERTS = 72
# Drop near-zero / bow-tie polygons that would show as 0.00 on the canvas.
_MIN_ROOM_AREA_PT2 = 4.0
# IoU above which two room candidates are treated as the same space.
_ROOM_IOU_DEDUP = 0.32
# Extra wall dilate (px) applied only to the free-space used for seeded BFS so
# door gaps close and named rooms stop bleeding into neighbours.
_SEED_WALL_DILATE_PX = 5
# When at least this many named rooms exist, drop unnamed geometry noise.
_MIN_NAMED_TO_DROP_UNNAMED = 4
# Max distance suggestions kept after building-footprint filtering.
_MAX_WALLS = 6

# Canny hysteresis thresholds for the wall-edge image fed to Hough.
_CANNY_LO = 50
_CANNY_HI = 150
# A wall segment must be at least this fraction of the page diagonal to count.
# Filters hatching, dimension ticks and short label underlines.
_WALL_MIN_LEN_FRAC = 0.10
# Hough accumulator vote threshold and the largest gap (px) bridged within one
# line. minLineLength is derived from _WALL_MIN_LEN_FRAC at call time.
_HOUGH_VOTES = 80
_HOUGH_MAX_GAP_PX = 10
# Two wall segments are treated as the same line (deduplicated) when their
# endpoints fall in the same coarse grid cell of this size in px.
_WALL_DEDUP_CELL_PX = 14
# Never return more than this many candidates total (matches recognize.py).
_MAX_CANDIDATES = 40

Point = tuple[float, float]


# ── geometry helpers (pixel space) ───────────────────────────────────────────


def _shoelace_area(pts: list[Point]) -> float:
    """Polygon area (pixel-squared), boundary auto-closed."""
    n = len(pts)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def _seg_length(p1: Point, p2: Point) -> float:
    return math.hypot(p2[0] - p1[0], p2[1] - p1[1])


# ── pixel -> point mapping ───────────────────────────────────────────────────


def _make_px_to_pt(
    image_width_px: int,
    image_height_px: int,
    page_width_pt: float,
    page_height_pt: float,
):
    """Return a function mapping an (x, y) image pixel to a PDF point.

    The rendered pixmap and the PDF page describe the same rectangle at two
    resolutions, so the map is a plain per-axis scale: a pixel at fraction f of
    the image width sits at fraction f of the page width.
    """
    sx = (page_width_pt / image_width_px) if image_width_px else 0.0
    sy = (page_height_pt / image_height_px) if image_height_px else 0.0

    def to_pt(x_px: float, y_px: float) -> Point:
        return (x_px * sx, y_px * sy)

    return to_pt


# ── value computation (PDF point geometry / calibration scale) ───────────────


def _area_value(area_pt2: float, scale: float) -> float | None:
    """Area in unit^2 from area in point^2; None without a calibration scale."""
    if scale and scale > 0:
        return area_pt2 / (scale * scale)
    return None


def _length_value(length_pt: float, scale: float) -> float | None:
    """Length in unit from length in points; None without a calibration scale."""
    if scale and scale > 0:
        return length_pt / scale
    return None


# ── image preparation ────────────────────────────────────────────────────────


def _to_gray(image_bgr: Any) -> Any | None:
    """Grayscale view of an HxWx3 BGR array, or None if the input is unusable."""
    try:
        arr = np.asarray(image_bgr)
        if arr.ndim == 3 and arr.shape[2] >= 3:
            return cv2.cvtColor(arr[:, :, :3], cv2.COLOR_BGR2GRAY)
        if arr.ndim == 2:
            return arr.astype(np.uint8, copy=False)
    except (cv2.error, ValueError, TypeError):
        return None
    return None


def _wall_mask(gray: Any) -> Any | None:
    """Binary mask where dark walls are foreground, with door gaps sealed.

    Otsu picks the global ink/paper split; adaptive threshold is OR-ed in so
    thin modern-CAD walls (light gray on white) are not dropped. Ink is dilated
    slightly, then reinforced with near-axis-aligned Hough segments so typical
    door openings close into continuous wall loops without OPEN (which merges
    rooms on floor plans).
    """
    try:
        blur = cv2.GaussianBlur(gray, (3, 3), 0)
        _, otsu = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        adaptive = cv2.adaptiveThreshold(
            blur,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            31,
            8,
        )
        ink = cv2.bitwise_or(otsu, adaptive)
        dilate_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        wall = cv2.dilate(ink, dilate_k, iterations=_WALL_DILATE_ITER)
        h, w = gray.shape[:2]
        min_side = min(h, w)
        edges = cv2.Canny(gray, _CANNY_LO, _CANNY_HI)
        lines = cv2.HoughLinesP(
            edges,
            1,
            math.pi / 180,
            threshold=max(40, min_side // 30),
            minLineLength=max(20, min_side // 40),
            maxLineGap=_HOUGH_MAX_GAP_PX,
        )
        if lines is not None:
            for line in lines:
                row = line[0] if hasattr(line[0], "__len__") else line
                x1, y1, x2, y2 = (int(v) for v in row)
                ang = abs(math.degrees(math.atan2(y2 - y1, x2 - x1))) % 180.0
                ortho = min(ang, abs(90.0 - ang), abs(180.0 - ang))
                if ortho <= _WALL_HOUGH_ANGLE_TOL_DEG:
                    cv2.line(wall, (x1, y1), (x2, y2), 255, _WALL_HOUGH_THICKNESS_PX)
        close_k = cv2.getStructuringElement(
            cv2.MORPH_RECT, (_WALL_CLOSE_KERNEL_PX, _WALL_CLOSE_KERNEL_PX)
        )
        return cv2.morphologyEx(wall, cv2.MORPH_CLOSE, close_k, iterations=_WALL_CLOSE_ITER)
    except cv2.error:
        return None


def _mask_exterior_free(free: Any) -> Any:
    """Zero out paper that touches the page border (outside the building).

    Pads a free ring around the page so every exterior pocket connects, then
    floods once from the corner — much cheaper than seeding every border pixel.
    """
    padded = cv2.copyMakeBorder(free, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=255)
    ph, pw = padded.shape[:2]
    ff_mask = np.zeros((ph + 2, pw + 2), np.uint8)
    cv2.floodFill(padded, ff_mask, (0, 0), 0)
    return padded[1:-1, 1:-1]


def _watershed_split_component(
    wall: Any,
    free_mask: Any,
    *,
    page_area: float,
    peak: float = _ROOM_WATERSHED_PEAK,
) -> list[Any]:
    """Split one free-space blob through door gaps via distance watershed."""
    if page_area <= 0 or int(cv2.countNonZero(free_mask)) < 64:
        return [free_mask]
    try:
        dist = cv2.distanceTransform(free_mask, cv2.DIST_L2, 5)
        if float(dist.max()) < 3.0:
            return [free_mask]
        _, sure_fg = cv2.threshold(dist, peak * float(dist.max()), 255, 0)
        sure_fg = cv2.erode(np.uint8(sure_fg), np.ones((3, 3), np.uint8), iterations=1)
        sure_fg = cv2.bitwise_and(sure_fg, free_mask)
        num, markers0 = cv2.connectedComponents(sure_fg)
        if num <= 2:
            return [free_mask]
        unknown = cv2.subtract(free_mask, sure_fg)
        markers = markers0 + 1
        markers[wall == 255] = 1
        markers[free_mask == 0] = 1
        markers[unknown == 255] = 0
        color = cv2.cvtColor(free_mask, cv2.COLOR_GRAY2BGR)
        cv2.watershed(color, markers)
    except cv2.error:
        return [free_mask]

    parts: list[Any] = []
    for i in range(2, int(markers.max()) + 1):
        part = ((markers == i) & (free_mask > 0)).astype(np.uint8) * 255
        frac = int(cv2.countNonZero(part)) / page_area
        if _ROOM_MIN_PAGE_FRAC <= frac <= _ROOM_COMPONENT_MAX_FRAC:
            parts.append(part)
    return parts if parts else [free_mask]


def _bbox_iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    """Intersection-over-union of two axis-aligned boxes ``(x0,y0,x1,y1)``."""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0)
    area_b = max(0.0, bx1 - bx0) * max(0.0, by1 - by0)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


# ── detectors ────────────────────────────────────────────────────────────────


def _normalize_room_name(raw: str) -> str | None:
    """Turn OCR fragments into a clean room title, or None if not a room label."""
    if not raw or _CAPTION_RE.search(raw):
        return None
    cleaned = re.sub(r"[^A-Za-z\s'-]", " ", raw)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned or not _ROOM_TOKEN_RE.search(cleaned):
        return None
    # Modern plans often print "C. Bath" / "C Bath" for common bathroom.
    cleaned = re.sub(r"\bC\b\s+(?=[Bb]ath)", "Common ", cleaned)
    # Ordered longest-first so SERVANTS / BEDROOM match before shorter prefixes.
    known = [
        "SERVANTS",
        "SERVANT",
        "BEDROOM",
        "PARKING",
        "STAIRS",
        "STAIR",
        "LIVING",
        "DINING",
        "KITCHEN",
        "CHAMBER",
        "PANTRY",
        "CLOSET",
        "ALCOVE",
        "STORES",
        "COATS",
        "LINEN",
        "PORCH",
        "BATH",
        "HALL",
        "ROOF",
        "COAT",
        "OTS",
        "COMMON",
        "BED",
        "ROOM",
    ]
    kept: list[str] = []
    for part in cleaned.split():
        up = re.sub(r"[^A-Z]", "", part.upper())
        if not up:
            continue
        match = None
        for k in known:
            if up == k or up.startswith(k) or (len(up) >= 4 and k.startswith(up)):
                match = k
                break
        if match is None:
            continue
        if match in {"SERVANT", "SERVANTS"}:
            kept.append("Servant's")
        elif match == "COAT":
            kept.append("Coats")
        elif match in {"BEDROOM", "BED"}:
            kept.append("Bed")
        elif match in {"STAIRS", "STAIR"}:
            kept.append("Stairs")
        elif match == "OTS":
            kept.append("OTS")
        elif match == "PARKING":
            kept.append("Parking")
        elif match == "COMMON":
            kept.append("Common")
        else:
            kept.append(match.title())
    if not kept or kept == ["Room"]:
        return None
    # Collapse "Servant's Room Room"
    while kept.count("Room") > 1:
        kept.remove("Room")
    # Reject OCR glues like "Dining Kitchen Room" — keep the first primary only.
    primaries = {
        "Living",
        "Dining",
        "Kitchen",
        "Bed",
        "Chamber",
        "Bath",
        "Hall",
        "Porch",
        "Parking",
        "Stairs",
        "OTS",
        "Alcove",
        "Pantry",
        "Closet",
        "Common",
        "Servant's",
        "Coats",
        "Linen",
        "Stores",
        "Roof",
    }
    primary_hits = [k for k in kept if k in primaries]
    if len(primary_hits) > 1 and "Common" not in primary_hits:
        first = primary_hits[0]
        kept = [first] + [k for k in kept if k == "Room" or k not in primaries]
    if "Bed" in kept:
        return "Bed Room"
    if "Common" in kept and "Bath" in kept:
        return "Common Bath"
    if kept == ["Parking"] or kept[0] == "Parking":
        return "Parking"
    if kept == ["Stairs"] or kept[0] == "Stairs":
        return "Stairs"
    if kept == ["OTS"] or kept[0] == "OTS":
        return "OTS"
    primary = kept[0]
    if primary in {"Living", "Dining", "Servant's"} and "Room" not in kept:
        kept.append("Room")
    if primary == "Servant's":
        return "Servant's Room"
    return " ".join(kept)


def _parse_tsv_words(
    tsv_path: str, *, scale_up: float, min_conf: float
) -> list[tuple[str, int, int, int, int, int, int, int, int]]:
    """Parse a Tesseract TSV into ``(text,left,top,w,h,block,par,line,word)``."""
    words: list[tuple[str, int, int, int, int, int, int, int, int]] = []
    try:
        with open(tsv_path, encoding="utf-8", errors="replace") as fh:
            next(fh, None)
            for line in fh:
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 12:
                    continue
                try:
                    conf = float(parts[10])
                    text = parts[11].strip()
                    left, top, ww, hh = (int(parts[6]), int(parts[7]), int(parts[8]), int(parts[9]))
                    block, par, ln, wn = (int(parts[2]), int(parts[3]), int(parts[4]), int(parts[5]))
                except (TypeError, ValueError):
                    continue
                if conf < min_conf or not text:
                    continue
                left = int(left / scale_up)
                top = int(top / scale_up)
                ww = max(1, int(ww / scale_up))
                hh = max(1, int(hh / scale_up))
                words.append((text, left, top, ww, hh, block, par, ln, wn))
    except OSError:
        return []
    return words


def _phrases_from_words(
    words: list[tuple[str, int, int, int, int, int, int, int, int]],
    *,
    page_h: int,
) -> list[tuple[str, int, int]]:
    """Group TSV words into room-name seeds (multiple Chambers kept)."""
    lines: dict[tuple[int, int, int], list[tuple[int, str, int, int, int, int]]] = defaultdict(list)
    for text, left, top, ww, hh, block, par, ln, wn in words:
        lines[(block, par, ln)].append((wn, text, left, top, ww, hh))

    found: list[tuple[str, int, int]] = []
    for items in lines.values():
        items.sort()
        i = 0
        while i < len(items):
            if not re.search(r"[A-Za-z]", items[i][1]):
                i += 1
                continue
            chunk = [items[i]]
            j = i + 1
            while j < len(items) and j < i + 3 and re.search(r"[A-Za-z]", items[j][1]):
                gap = items[j][2] - (chunk[-1][2] + chunk[-1][4])
                if gap > 72:
                    break
                chunk.append(items[j])
                j += 1
            phrase = " ".join(t for _, t, _, _, _, _ in chunk)
            name = _normalize_room_name(phrase)
            if name:
                x0 = min(c[2] for c in chunk)
                y0 = min(c[3] for c in chunk)
                x1 = max(c[2] + c[4] for c in chunk)
                y1 = max(c[3] + c[5] for c in chunk)
                cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
                # Parking / stairs often sit in the bottom band of the sheet.
                band = 0.93 if name in {"Parking", "Stairs"} else 0.88
                if cy < int(page_h * band):
                    found.append((name, cx, cy))
            i = j if j > i else i + 1
    return found


def _ocr_crop_room_labels(gray: Any) -> list[tuple[str, int, int]]:
    """Single-word OCR on text-like ink blobs — recovers CHAMBER etc. full-page OCR misses."""
    h0, w0 = gray.shape[:2]
    try:
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        enh0 = clahe.apply(gray)
        # Work at 1.5× so small CHAMBER titles form cleaner connected components.
        scale_c = 1.5
        enh = cv2.resize(enh0, None, fx=scale_c, fy=scale_c, interpolation=cv2.INTER_CUBIC)
        h, w = enh.shape[:2]
        _, bw = cv2.threshold(enh, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        ink = 255 - bw if float(bw.mean()) > 127 else bw
        count, _labels, stats, _ = cv2.connectedComponentsWithStats(ink, 8)
    except cv2.error:
        return []

    crops: list[tuple[int, int, int, int, Any]] = []
    for i in range(1, count):
        x, y, bw_, bh_, area = (int(stats[i, j]) for j in range(5))
        if area < 60 or area > 14000:
            continue
        if bh_ < 10 or bh_ > 70 or bw_ < 36 or bw_ > 360:
            continue
        ar = bw_ / (bh_ + 1e-6)
        if not (1.2 <= ar <= 14.0):
            continue
        if y >= int(h * 0.84):
            continue
        pad = 4
        crop = enh[max(0, y - pad) : min(h, y + bh_ + pad), max(0, x - pad) : min(w, x + bw_ + pad)]
        if crop.size == 0:
            continue
        crop = cv2.resize(crop, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)
        # Map box origin back to original gray coordinates.
        ox, oy = int(x / scale_c), int(y / scale_c)
        obw, obh = max(1, int(bw_ / scale_c)), max(1, int(bh_ / scale_c))
        crops.append((ox, oy, obw, obh, crop))

    if not crops:
        return []

    tmp_dir = tempfile.mkdtemp(prefix="takeoff_ocr_crop_")
    found: list[tuple[str, int, int]] = []
    try:
        for i, (x, y, bw_, bh_, crop) in enumerate(crops):
            img_path = os.path.join(tmp_dir, f"c{i}.png")
            base = os.path.join(tmp_dir, f"c{i}")
            if not cv2.imwrite(img_path, crop):
                continue
            subprocess.run(
                [
                    "tesseract",
                    img_path,
                    base,
                    "--psm",
                    "8",
                    "-c",
                    "tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'-",
                    "tsv",
                ],
                capture_output=True,
                check=False,
            )
            tsv = base + ".tsv"
            if not os.path.isfile(tsv):
                continue
            for text, _l, _t, _ww, _hh, *_rest in _parse_tsv_words(tsv, scale_up=1.0, min_conf=35):
                # Accept common OCR fragments for room titles.
                raw = text
                if re.search(r"^CHAM", text, re.I):
                    raw = "CHAMBER"
                elif re.fullmatch(r"OTS", text, re.I):
                    raw = "OTS"
                elif re.search(r"^STAIR", text, re.I):
                    raw = "STAIRS"
                elif re.search(r"^PARK", text, re.I):
                    raw = "PARKING"
                name = _normalize_room_name(raw)
                if not name:
                    continue
                found.append((name, x + bw_ // 2, y + bh_ // 2))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return found


def _template_match_repeat_labels(
    gray: Any, seeds: list[tuple[str, int, int]]
) -> list[tuple[str, int, int]]:
    """Find repeated titles (e.g. three CHAMBER labels) via template match.

    Only Chamber is templated — short words like Bath / Closet false-match on
    dimension ticks and hatch lines and invent dozens of ghost rooms.
    """
    h, w = gray.shape[:2]
    extras: list[tuple[str, int, int]] = []
    # One seed per base name used as the template source.
    seen_base: set[str] = set()
    for name, cx, cy in seeds:
        base = re.sub(r"\s+\d+$", "", name)
        if base != "Chamber" or base in seen_base:
            continue
        seen_base.add(base)
        # Crop a small patch around the known label.
        x0, x1 = max(0, cx - 55), min(w, cx + 65)
        y0, y1 = max(0, cy - 14), min(h, cy + 18)
        tmpl = gray[y0:y1, x0:x1]
        if tmpl.size < 80 or tmpl.shape[0] < 8 or tmpl.shape[1] < 20:
            continue
        search = gray[: int(h * 0.62)]
        try:
            res = cv2.matchTemplate(search, tmpl, cv2.TM_CCOEFF_NORMED)
        except cv2.error:
            continue
        threshold = 0.72
        loc = np.where(res >= threshold)
        matches = list(zip(loc[1].tolist(), loc[0].tolist()))
        if not matches:
            continue
        # Cluster nearby peaks; require vertical separation (not one scanline).
        matches.sort(key=lambda p: (p[1], p[0]))
        clusters: list[list[int]] = []
        for x, y in matches:
            if (
                not clusters
                or abs(x - clusters[-1][0]) > 48
                or abs(y - clusters[-1][1]) > 28
            ):
                clusters.append([x, y])
            else:
                clusters[-1][0] = (clusters[-1][0] + x) // 2
                clusters[-1][1] = (clusters[-1][1] + y) // 2
        th, tw = tmpl.shape[:2]
        for x, y in clusters[:8]:
            extras.append((base, x + tw // 2, y + th // 2))
    return extras


def _disambiguate_duplicate_names(
    seeds: list[tuple[str, int, int]],
) -> list[tuple[str, int, int]]:
    """Turn repeated Chamber seeds into Chamber 1 / Chamber 2 (left-to-right)."""
    from collections import Counter

    counts = Counter(n for n, _, _ in seeds)
    if not any(c > 1 for c in counts.values()):
        return seeds
    # Stable order: top-to-bottom, then left-to-right within a name group.
    ordered = sorted(seeds, key=lambda s: (s[0], s[2], s[1]))
    seen: dict[str, int] = {}
    out: list[tuple[str, int, int]] = []
    for name, cx, cy in ordered:
        if counts[name] > 1:
            seen[name] = seen.get(name, 0) + 1
            out.append((f"{name} {seen[name]}", cx, cy))
        else:
            out.append((name, cx, cy))
    return out


def _ocr_room_labels(gray: Any) -> list[tuple[str, int, int]]:
    """Return ``(room_name, cx, cy)`` seeds in image pixel space via Tesseract.

    Combines multi-PSM full-page OCR with per-blob single-word OCR so hard
    labels (CHAMBER) are not missed. Multiple rooms sharing a name are kept
    (Chamber 1/2/3). Returns ``[]`` when OCR is unavailable.
    """
    if gray is None or getattr(gray, "size", 0) == 0:
        return []
    if not shutil.which("tesseract"):
        return []
    h, w = gray.shape[:2]
    try:
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        enh = clahe.apply(gray)
        scale_up = 2.0
        enh_u = cv2.resize(enh, None, fx=scale_up, fy=scale_up, interpolation=cv2.INTER_CUBIC)
    except cv2.error:
        return []

    found: list[tuple[str, int, int]] = []
    tmp_dir = tempfile.mkdtemp(prefix="takeoff_ocr_")
    try:
        img_path = os.path.join(tmp_dir, "page.png")
        if not cv2.imwrite(img_path, enh_u):
            return []
        # PSM 11 (sparse text) is the reliable floor-plan mode. Extra PSMs
        # invent ghost rooms from dimensions / hatch on modern vector PDFs.
        words_primary: list[tuple[str, int, int, int, int, int, int, int, int]] = []
        base_path = os.path.join(tmp_dir, "out_11")
        proc = subprocess.run(
            ["tesseract", img_path, base_path, "--psm", "11", "tsv"],
            capture_output=True,
            check=False,
        )
        tsv_path = base_path + ".tsv"
        if proc.returncode in (0, 1) and os.path.isfile(tsv_path):
            words_primary = _parse_tsv_words(tsv_path, scale_up=scale_up, min_conf=18)
        found.extend(_phrases_from_words(words_primary, page_h=h))
    except OSError:
        pass
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # Crop OCR + Chamber template recover repeated vintage titles PSM 11 misses.
    found.extend(_ocr_crop_room_labels(gray))
    found.extend(_template_match_repeat_labels(gray, found))

    # Proximity dedupe only — keep multiple Chambers at different locations.
    # For unique names that also appear in the page caption, keep the uppermost.
    unique_names = {n for n, _, _ in found}
    caption_y = int(h * 0.78)
    cleaned: list[tuple[str, int, int]] = []
    # Sort so upper seeds win when collapsing caption duplicates of unique names.
    for name, cx, cy in sorted(found, key=lambda s: (s[0], s[2], s[1])):
        if not (0 <= cx < w and 0 <= cy < h):
            continue
        # Drop caption-band duplicates of names already found higher up.
        if cy >= caption_y and any(n == name and y < caption_y for n, _, y in cleaned):
            continue
        near = max(36.0, min(h, w) * 0.045)
        if any(math.hypot(cx - x, cy - y) < near for _, x, y in cleaned):
            # Same spot: prefer a more specific name (Living Room over Room).
            for i, (n, x, y) in enumerate(cleaned):
                if math.hypot(cx - x, cy - y) < near:
                    if len(name) > len(n):
                        cleaned[i] = (name, cx, cy)
                    break
            continue
        cleaned.append((name, cx, cy))

    def _spaced(items: list[tuple[str, int, int]], min_dist: float) -> list[tuple[str, int, int]]:
        ordered = sorted(items, key=lambda s: (s[2], s[1]))
        out: list[tuple[str, int, int]] = []
        for name, cx, cy in ordered:
            if any(math.hypot(cx - x, cy - y) < min_dist for _, x, y in out):
                continue
            # Collapse vertical ghosts on the same wall column.
            if any(abs(cx - x) < 28 and abs(cy - y) < min_dist * 1.8 for _, x, y in out):
                continue
            out.append((name, cx, cy))
        return out

    # Group by base name; apply plate-aware placement rules.
    by_name: dict[str, list[tuple[str, int, int]]] = defaultdict(list)
    for item in cleaned:
        base = re.sub(r"\s+\d+$", "", item[0])
        by_name[base].append(item)
    final: list[tuple[str, int, int]] = []
    mid_y = int(h * 0.52)
    lower_band = int(h * 0.84)
    # Vintage book scans stack two floor plates (chambers above, living/dining
    # below). Modern single-plate PDFs also have labels top and bottom — do not
    # treat those as stacked or Living/Dining get forced into the wrong band.
    bases_present = {re.sub(r"\s+\d+$", "", n) for n, _, _ in cleaned}
    stacked_plates = "Chamber" in bases_present and bool(
        bases_present & {"Living Room", "Dining Room"}
    )
    space = max(70.0, min(h, w) * 0.055)
    # Bath + Common Bath share one quota (ghost C/Bath hits are common).
    bath_pool: list[tuple[str, int, int]] = []
    for bname in ("Common Bath", "Bath"):
        bath_pool.extend(by_name.pop(bname, []))
    if bath_pool:
        # Prefer Common Bath wording; drop plain Bath when Common Bath exists.
        has_common = any(n.startswith("Common") for n, _, _ in bath_pool)
        if has_common:
            bath_pool = [s for s in bath_pool if s[0].startswith("Common")]
        bath_pool.sort(key=lambda s: (0 if s[0].startswith("Common") else 1, s[2], s[1]))
        # Single-plate modern plans almost always have one bath label.
        bath_cap = 2 if stacked_plates else 1
        bath_kept = _spaced(bath_pool, max(space, min(h, w) * 0.12))[:bath_cap]
        final.extend(bath_kept)

    for base, items in by_name.items():
        # Keep every well-spaced seed for repeated room types.
        if base in {"Chamber", "Closet", "Hall", "Porch", "Alcove", "Bed Room"}:
            kept = _spaced(items, space)
            if base == "Bed Room":
                kept = kept[:4]
            elif base == "Chamber":
                kept = kept[:6]
            else:
                kept = kept[:4]
            final.extend(kept)
            continue
        # Living / Dining on stacked floor plates sit on the lower drawing.
        if stacked_plates and base in {"Living Room", "Dining Room"}:
            band = [it for it in items if mid_y <= it[2] < lower_band]
            pick_from = band or [it for it in items if it[2] < lower_band] or items
            final.append(sorted(pick_from, key=lambda s: s[2])[-1])  # lowest in band
            continue
        # Other unique names: uppermost (plan label over caption).
        final.append(sorted(items, key=lambda s: s[2])[0])

    # CAD title-block / legend column — never seed rooms from the right strip
    # (was producing stacked Area boxes over schedules and "Roof" legends).
    title_x = int(w * 0.78)
    final = [(n, x, y) for n, x, y in final if x < title_x]

    return _disambiguate_duplicate_names(final)


def _point_in_poly(x: float, y: float, poly: list[Point]) -> bool:
    """Ray-cast point-in-polygon (image pixel space)."""
    n = len(poly)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi):
            inside = not inside
        j = i
    return inside


def _sealed_free_for_seeds(wall: Any, free: Any) -> Any:
    """Thicken walls so door openings seal before seeded room growth."""
    try:
        k = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (_SEED_WALL_DILATE_PX * 2 + 1, _SEED_WALL_DILATE_PX * 2 + 1)
        )
        thick = cv2.dilate(wall, k, iterations=1)
        sealed = cv2.bitwise_and(free, cv2.bitwise_not(thick))
        # Keep a little free around seeds if dilation erased a narrow room.
        if int(cv2.countNonZero(sealed)) < 0.35 * int(cv2.countNonZero(free) or 1):
            return free
        return sealed
    except cv2.error:
        return free


def _find_room_seed_pixel(
    free: Any,
    owner: Any,
    cx: int,
    cy: int,
    *,
    min_comp_area: int,
) -> tuple[int, int] | None:
    """Nearest free pixel that sits in a room-sized component (not a text gap)."""
    h, w = free.shape[:2]
    try:
        count, labels, stats, _ = cv2.connectedComponentsWithStats(free, 8)
    except cv2.error:
        return None
    if count <= 1:
        return None
    # Precompute which labels are large enough to be rooms.
    big = {
        i
        for i in range(1, count)
        if int(stats[i, cv2.CC_STAT_AREA]) >= min_comp_area
    }
    if not big:
        return None
    for rad in range(0, 100, 1):
        for dy in range(-rad, rad + 1):
            for dx in range(-rad, rad + 1):
                # Only check the ring for rad>0 (avoid O(r^2) full disk each time).
                if rad > 0 and abs(dx) != rad and abs(dy) != rad:
                    continue
                x, y = cx + dx, cy + dy
                if not (0 <= x < w and 0 <= y < h):
                    continue
                if not free[y, x] or owner[y, x] != 0:
                    continue
                lab = int(labels[y, x])
                if lab in big:
                    return (x, y)
    return None


def _geodesic_rooms_from_seeds(
    free: Any,
    seeds: list[tuple[str, int, int]],
) -> list[tuple[str, Any]]:
    """Multi-source BFS through free space — splits open doorways at midpoints."""
    h, w = free.shape[:2]
    page_area = float(h * w) or 1.0
    min_comp = max(64, int(page_area * _ROOM_MIN_PAGE_FRAC * 0.85))
    owner = np.zeros((h, w), np.int32)
    q: deque[tuple[int, int, int]] = deque()
    names: dict[int, str] = {}
    for idx, (name, cx, cy) in enumerate(seeds, start=1):
        found = _find_room_seed_pixel(free, owner, cx, cy, min_comp_area=min_comp)
        if found is None:
            continue
        names[idx] = name
        owner[found[1], found[0]] = idx
        q.append((found[0], found[1], idx))

    while q:
        x, y, idx = q.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h and free[ny, nx] and owner[ny, nx] == 0:
                owner[ny, nx] = idx
                q.append((nx, ny, idx))

    out: list[tuple[str, Any]] = []
    for idx, name in names.items():
        mask = (owner == idx).astype(np.uint8) * 255
        if int(cv2.countNonZero(mask)) < 32:
            continue
        out.append((name, mask))
    return out


def _structure_wall_barrier(wall: Any, free: Any) -> Any:
    """Wall mask for ray casting — keeps long/thick strokes, drops text blobs.

    Room titles sit as dark ink inside rooms; if they stay in the barrier, rays
    stop at the letters and the polygon collapses to a text box. Text pixels are
    made walkable; only structural walls and page exterior block rays.
    """
    h, w = wall.shape[:2]
    page = float(h * w) or 1.0
    try:
        count, labels, stats, _ = cv2.connectedComponentsWithStats(wall, 8)
    except cv2.error:
        return wall > 0

    keep = np.zeros((h, w), np.uint8)
    min_area = max(120, int(page * 0.0002))
    min_len = max(36, int(min(h, w) * 0.045))
    for i in range(1, count):
        area = int(stats[i, cv2.CC_STAT_AREA])
        bw = int(stats[i, cv2.CC_STAT_WIDTH])
        bh = int(stats[i, cv2.CC_STAT_HEIGHT])
        long_side = max(bw, bh)
        short_side = min(bw, bh)
        # Real walls: large / long. Drop compact text-sized blobs.
        if long_side >= min_len or (area >= min_area and long_side >= 2.5 * short_side):
            keep[labels == i] = 255
    try:
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        keep = cv2.dilate(keep, k, iterations=1)
    except cv2.error:
        pass
    # Exterior only (not wall ink): paper outside the building footprint.
    # ``free`` is interior paper; everything that is not free and not kept wall
    # still must not block if it was text we dropped — so exterior is the
    # border-flooded outside of the raw paper mask.
    try:
        paper = cv2.bitwise_not(wall)
        interior_paper = _mask_exterior_free(paper)
        # Paper that the border flood erased = outside the building plate(s).
        exterior = (paper > 0) & (interior_paper == 0)
    except cv2.error:
        exterior = np.zeros((h, w), dtype=bool)
    return (keep > 0) | exterior


def _axis_aligned_rect_from_seed(
    wall: Any,
    free: Any,
    cx: int,
    cy: int,
    other_seeds: list[tuple[int, int]],
) -> tuple[int, int, int, int] | None:
    """Cast axis-aligned rays from a seed to walls / Voronoi frontiers.

    Returns ``(x0, y0, x1, y1)`` with perfectly horizontal/vertical edges so
    room polygons never look tilted. Rays stop on structural walls, outside the
    building, or when another room label is closer (open door / arch case).
    """
    h, w = wall.shape[:2]
    if not (0 <= cx < w and 0 <= cy < h):
        return None
    # Clear a disk around the label so rays escape letter ink / furniture ticks.
    clear_r = max(10, int(min(h, w) * 0.012))
    barrier = np.array(_structure_wall_barrier(wall, free), dtype=bool)
    yy, xx = np.ogrid[-clear_r : clear_r + 1, -clear_r : clear_r + 1]
    disk = xx * xx + yy * yy <= clear_r * clear_r
    y0c, y1c = max(0, cy - clear_r), min(h, cy + clear_r + 1)
    x0c, x1c = max(0, cx - clear_r), min(w, cx + clear_r + 1)
    dy0, dx0 = y0c - (cy - clear_r), x0c - (cx - clear_r)
    patch = disk[dy0 : dy0 + (y1c - y0c), dx0 : dx0 + (x1c - x0c)]
    barrier[y0c:y1c, x0c:x1c][patch] = False

    def _blocked(x: int, y: int) -> bool:
        if x < 0 or y < 0 or x >= w or y >= h:
            return True
        if barrier[y, x]:
            return True
        d_me = (x - cx) * (x - cx) + (y - cy) * (y - cy)
        for sx, sy in other_seeds:
            d_ot = (x - sx) * (x - sx) + (y - sy) * (y - sy)
            # Entering another room's half-plane through an open door.
            if d_ot + 16 < d_me:
                return True
        return False

    def _cast(dx: int, dy: int) -> tuple[int, int]:
        x, y = cx, cy
        last = (cx, cy)
        for _ in range(max(h, w)):
            nx, ny = x + dx, y + dy
            if _blocked(nx, ny):
                return last
            x, y = nx, ny
            last = (x, y)
        return last

    # Nudge origin off ink into the room interior.
    if _blocked(cx, cy):
        found = None
        for rad in range(1, 50):
            for dy in range(-rad, rad + 1):
                for dx in range(-rad, rad + 1):
                    if rad > 0 and abs(dx) != rad and abs(dy) != rad:
                        continue
                    x, y = cx + dx, cy + dy
                    if 0 <= x < w and 0 <= y < h and not _blocked(x, y):
                        found = (x, y)
                        break
                if found:
                    break
            if found:
                break
        if found is None:
            return None
        cx, cy = found

    left_x, _ = _cast(-1, 0)
    right_x, _ = _cast(1, 0)
    _, top_y = _cast(0, -1)
    _, bot_y = _cast(0, 1)
    x0, x1 = min(left_x, right_x), max(left_x, right_x)
    y0, y1 = min(top_y, bot_y), max(top_y, bot_y)
    if x1 - x0 < 12 or y1 - y0 < 12:
        return None
    return (x0, y0, x1, y1)


def _rect_to_mask(rect: tuple[int, int, int, int], h: int, w: int) -> Any:
    x0, y0, x1, y1 = rect
    mask = np.zeros((h, w), np.uint8)
    cv2.rectangle(mask, (x0, y0), (x1, y1), 255, thickness=-1)
    return mask


def _axis_aligned_poly(rect: tuple[int, int, int, int]) -> list[Point]:
    """Four corners of an axis-aligned rectangle (straight H/V edges only)."""
    x0, y0, x1, y1 = rect
    return [
        (float(x0), float(y0)),
        (float(x1), float(y0)),
        (float(x1), float(y1)),
        (float(x0), float(y1)),
    ]


def _expand_rect_to_structure_walls(
    wall: Any,
    free: Any,
    rect: tuple[int, int, int, int],
    *,
    forbidden: Any,
    max_expand: int,
) -> tuple[int, int, int, int]:
    """Grow an axis-aligned rect until each edge meets structural wall ink.

    Will not expand into ``forbidden`` pixels (other rooms' geodesic cells).
    """
    h, w = wall.shape[:2]
    x0, y0, x1, y1 = rect
    try:
        count, labels, stats, _ = cv2.connectedComponentsWithStats(wall, 8)
        keep = np.zeros((h, w), np.uint8)
        page = float(h * w) or 1.0
        min_area = max(120, int(page * 0.0002))
        min_len = max(36, int(min(h, w) * 0.045))
        for i in range(1, count):
            area = int(stats[i, cv2.CC_STAT_AREA])
            bw = int(stats[i, cv2.CC_STAT_WIDTH])
            bh = int(stats[i, cv2.CC_STAT_HEIGHT])
            if max(bw, bh) >= min_len or (
                area >= min_area and max(bw, bh) >= 2.5 * min(bw, bh)
            ):
                keep[labels == i] = 255
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        struct = cv2.dilate(keep, k, iterations=1) > 0
    except cv2.error:
        struct = wall > 0

    def _edge_hits_wall(x_a: int, y_a: int, x_b: int, y_b: int) -> bool:
        x_a, x_b = max(0, min(x_a, x_b)), min(w - 1, max(x_a, x_b))
        y_a, y_b = max(0, min(y_a, y_b)), min(h - 1, max(y_a, y_b))
        if x_a == x_b:
            col = struct[y_a : y_b + 1, x_a]
            return bool(col.size) and float(col.mean()) >= 0.12
        row = struct[y_a, x_a : x_b + 1]
        return bool(row.size) and float(row.mean()) >= 0.12

    def _strip_ok(x_a: int, y_a: int, x_b: int, y_b: int) -> bool:
        """New strip must stay in free space and outside other rooms."""
        x_a, x_b = max(0, min(x_a, x_b)), min(w - 1, max(x_a, x_b))
        y_a, y_b = max(0, min(y_a, y_b)), min(h - 1, max(y_a, y_b))
        region_f = free[y_a : y_b + 1, x_a : x_b + 1]
        region_b = forbidden[y_a : y_b + 1, x_a : x_b + 1]
        if region_f.size == 0:
            return False
        if float((region_b > 0).mean()) > 0.08:
            return False
        # Allow crossing text (not free) but not other rooms; prefer free majority.
        return float((region_f > 0).mean()) >= 0.35 or float((region_b > 0).mean()) == 0.0

    for _ in range(max_expand):
        grew = False
        if x0 > 0 and not _edge_hits_wall(x0, y0, x0, y1) and _strip_ok(x0 - 1, y0, x0 - 1, y1):
            x0 -= 1
            grew = True
        if x1 < w - 1 and not _edge_hits_wall(x1, y0, x1, y1) and _strip_ok(x1 + 1, y0, x1 + 1, y1):
            x1 += 1
            grew = True
        if y0 > 0 and not _edge_hits_wall(x0, y0, x1, y0) and _strip_ok(x0, y0 - 1, x1, y0 - 1):
            y0 -= 1
            grew = True
        if y1 < h - 1 and not _edge_hits_wall(x0, y1, x1, y1) and _strip_ok(x0, y1 + 1, x1, y1 + 1):
            y1 += 1
            grew = True
        if not grew:
            break
    return (x0, y0, x1, y1)


def _named_rooms_as_rects(
    wall: Any,
    free: Any,
    seeds: list[tuple[str, int, int]],
) -> list[tuple[str, list[Point], Any]]:
    """Build one axis-aligned room rectangle per OCR label.

    1. Geodesic Voronoi ownership (splits open-plan rooms at door midpoints)
    2. Axis-aligned bbox of each cell
    3. Expand to structural walls (ignores text ink) so boxes hug wall lines
    """
    h, w = wall.shape[:2]
    seed_free = _sealed_free_for_seeds(wall, free)
    geo = _geodesic_rooms_from_seeds(seed_free, seeds)
    max_expand = max(28, int(min(h, w) * 0.08))
    # Precompute union of all cells for forbidden masks.
    all_masks = {name: mask for name, mask in geo}
    named_rects: list[tuple[str, tuple[int, int, int, int]]] = []
    for name, mask in geo:
        ys, xs = np.where(mask > 0)
        if len(xs) == 0:
            continue
        rect = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))
        forbidden = np.zeros((h, w), np.uint8)
        for other, omask in all_masks.items():
            if other != name:
                forbidden = cv2.bitwise_or(forbidden, omask)
        rect = _expand_rect_to_structure_walls(
            wall, free, rect, forbidden=forbidden, max_expand=max_expand
        )
        named_rects.append((name, rect))

    # Split shared edges so neighbouring rooms don't overlap after expand.
    for _ in range(3):
        changed = False
        for i in range(len(named_rects)):
            for j in range(i + 1, len(named_rects)):
                n1, (ax0, ay0, ax1, ay1) = named_rects[i]
                n2, (bx0, by0, bx1, by1) = named_rects[j]
                ix0, iy0 = max(ax0, bx0), max(ay0, by0)
                ix1, iy1 = min(ax1, bx1), min(ay1, by1)
                if ix1 - ix0 < 4 or iy1 - iy0 < 4:
                    continue
                # Prefer splitting on the thinner overlap axis.
                if ix1 - ix0 <= iy1 - iy0:
                    mid = (ix0 + ix1) // 2
                    # Keep left room's right edge / right room's left edge at mid.
                    if (ax0 + ax1) / 2 <= (bx0 + bx1) / 2:
                        named_rects[i] = (n1, (ax0, ay0, mid, ay1))
                        named_rects[j] = (n2, (mid, by0, bx1, by1))
                    else:
                        named_rects[i] = (n1, (mid, ay0, ax1, ay1))
                        named_rects[j] = (n2, (bx0, by0, mid, by1))
                else:
                    mid = (iy0 + iy1) // 2
                    if (ay0 + ay1) / 2 <= (by0 + by1) / 2:
                        named_rects[i] = (n1, (ax0, ay0, ax1, mid))
                        named_rects[j] = (n2, (bx0, mid, bx1, by1))
                    else:
                        named_rects[i] = (n1, (ax0, mid, ax1, ay1))
                        named_rects[j] = (n2, (bx0, by0, bx1, mid))
                changed = True
        if not changed:
            break

    out: list[tuple[str, list[Point], Any]] = []
    for name, rect in named_rects:
        x0, y0, x1, y1 = rect
        if x1 - x0 < 8 or y1 - y0 < 8:
            continue
        geo_mask = all_masks.get(name)
        if geo_mask is not None and int(cv2.countNonZero(geo_mask)) >= 32:
            # Use the geodesic cell itself so arches / curved walls stay in the
            # polygon. Clipping to the AABB first squared off every curve.
            mask = geo_mask.copy()
        else:
            mask = cv2.bitwise_and(free, _rect_to_mask(rect, h, w))
        poly = _mask_polygon(mask, force_rect=False)
        if poly is None or len(poly) < 3:
            poly = _axis_aligned_poly(rect)
            mask = _rect_to_mask(rect, h, w)
        out.append((name, poly, mask))
    return out


def _cand_from_mask(
    mask: Any,
    to_pt,
    scale: float,
    page_area: float,
    *,
    label: str | None,
    confidence: float,
    reason: str,
    poly_px: list[Point] | None = None,
) -> dict[str, Any] | None:
    area_px = int(cv2.countNonZero(mask))
    frac = area_px / page_area if page_area else 0.0
    min_frac = _ROOM_MIN_PAGE_FRAC_NAMED if label else _ROOM_MIN_PAGE_FRAC
    max_frac = _ROOM_MAX_PAGE_FRAC_NAMED if label else _ROOM_MAX_PAGE_FRAC
    if frac < min_frac or frac > max_frac:
        return None
    # Named rooms: prefer a supplied polygon; else contour (not forced AABB on curves).
    if poly_px is None:
        poly_px = _mask_polygon(mask, force_rect=bool(label))
    if poly_px is None or len(poly_px) < 3:
        return None
    # Reject near-full-page envelopes (bbox). Sparse fill can still pass the
    # frac cap while painting one huge overlapping box over every zone.
    xs_bb = [p[0] for p in poly_px]
    ys_bb = [p[1] for p in poly_px]
    bb_frac = ((max(xs_bb) - min(xs_bb)) * (max(ys_bb) - min(ys_bb))) / page_area
    if bb_frac > 0.50:
        return None
    # Axis-align only clean 4-point rectangles — never flatten arches to a box.
    if label and len(poly_px) == 4:
        xs = [p[0] for p in poly_px]
        ys = [p[1] for p in poly_px]
        # Only snap when the four points already form an axis-aligned box.
        if (
            abs(xs[0] - xs[3]) < 1.5
            and abs(xs[1] - xs[2]) < 1.5
            and abs(ys[0] - ys[1]) < 1.5
            and abs(ys[2] - ys[3]) < 1.5
        ):
            poly_px = _axis_aligned_poly((int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))))
    pts_pt = [to_pt(px, py) for px, py in poly_px]
    # Accurate fill area from the mask (shoelace undercounts curved edges).
    origin = to_pt(0.0, 0.0)
    ax = abs(to_pt(1.0, 0.0)[0] - origin[0])
    ay = abs(to_pt(0.0, 1.0)[1] - origin[1])
    area_pt2 = float(area_px) * ax * ay if ax > 0 and ay > 0 else _shoelace_area(pts_pt)
    if area_pt2 < _MIN_ROOM_AREA_PT2:
        return None
    value = _area_value(area_pt2, scale)
    if scale and scale > 0 and (value is None or value <= 0):
        return None
    return {
        "type": "area",
        "points": [{"x": p[0], "y": p[1]} for p in pts_pt],
        "value": value,
        "dimension": "area",
        "count": None,
        "confidence": confidence,
        "reason": reason,
        "label": label,
        "_bbox": (
            min(p[0] for p in pts_pt),
            min(p[1] for p in pts_pt),
            max(p[0] for p in pts_pt),
            max(p[1] for p in pts_pt),
        ),
        "_poly_px": poly_px,
    }


def _detect_rooms(gray: Any, to_pt, scale: float) -> list[dict[str, Any]]:
    """Sealed light regions between walls -> area candidates (rooms).

    Prefer OCR room-name seeds + geodesic Voronoi fill (accurate named rooms).
    Fall back to morphology / watershed when OCR finds nothing.
    """
    wall = _wall_mask(gray)
    if wall is None:
        return []
    h, w = wall.shape[:2]
    page_area = float(h * w)
    if page_area <= 0:
        return []
    try:
        free = _mask_exterior_free(cv2.bitwise_not(wall))
    except cv2.error:
        return []

    out: list[dict[str, Any]] = []
    ocr_seeds = _ocr_room_labels(gray)
    claimed = np.zeros((h, w), np.uint8)
    title_x = int(w * 0.78)

    if len(ocr_seeds) >= 2:
        for name, poly_px, mask in _named_rooms_as_rects(wall, free, ocr_seeds):
            cand = _cand_from_mask(
                mask,
                to_pt,
                scale,
                page_area,
                label=name,
                confidence=0.82,
                reason=f"Room “{name}” snapped to walls (verify)",
                poly_px=poly_px,
            )
            if cand is None:
                continue
            out.append(cand)
            claimed = cv2.bitwise_or(claimed, mask)

    named_count = sum(1 for c in out if c.get("label"))
    # With solid named coverage, skip unnamed geometry (was Area 5/6/7 noise).
    allow_unnamed = named_count < _MIN_NAMED_TO_DROP_UNNAMED

    # Geometry fallback for leftover pockets (and when OCR is empty).
    try:
        remain = cv2.bitwise_and(free, cv2.bitwise_not(claimed))
        count, labels, stats, _ = cv2.connectedComponentsWithStats(remain, 8)
    except cv2.error:
        count, labels, stats = 0, None, None

    if count and labels is not None and stats is not None:
        order = sorted(range(1, count), key=lambda i: -int(stats[i, cv2.CC_STAT_AREA]))
        for idx in order:
            area_px = int(stats[idx, cv2.CC_STAT_AREA])
            frac = area_px / page_area
            if frac < _ROOM_MIN_PAGE_FRAC or frac > _ROOM_COMPONENT_MAX_FRAC:
                continue
            x = int(stats[idx, cv2.CC_STAT_LEFT])
            y = int(stats[idx, cv2.CC_STAT_TOP])
            bw = int(stats[idx, cv2.CC_STAT_WIDTH])
            bh = int(stats[idx, cv2.CC_STAT_HEIGHT])
            if x <= 2 and y <= 2 and x + bw >= w - 2 and y + bh >= h - 2:
                continue
            # Legend / title-block column — skip small cells stacked there.
            if (x + bw * 0.5) >= title_x and frac < 0.08:
                continue
            # Thin horizontal bands (dimension strings), not floor zones.
            if bh < h * 0.045 and bw > 3.5 * bh and frac < 0.04:
                continue
            component = ((labels == idx).astype(np.uint8) * 255)
            # Mid-size only: large open parking / podium decks must stay one
            # curved contour — watershed chops them into stall-sized fragments.
            parts = (
                _watershed_split_component(wall, component, page_area=page_area)
                if _ROOM_SPLIT_PAGE_FRAC <= frac < _ROOM_SPLIT_MAX_FRAC
                else [component]
            )
            for mask in parts:
                # Skip pockets already covered by a named room.
                if claimed is not None and int(cv2.countNonZero(cv2.bitwise_and(mask, claimed))) > 0.35 * int(
                    cv2.countNonZero(mask) or 1
                ):
                    continue
                # Attach a leftover OCR label whose seed lands inside this pocket.
                label = None
                poly_px = _mask_polygon(mask)
                if poly_px:
                    for name, cx, cy in ocr_seeds:
                        if _point_in_poly(cx, cy, poly_px) and not any(
                            c.get("label") == name for c in out
                        ):
                            label = name
                            break
                if label is None and not allow_unnamed:
                    continue
                cand = _cand_from_mask(
                    mask,
                    to_pt,
                    scale,
                    page_area,
                    label=label,
                    confidence=0.68 if label else 0.52,
                    reason=(
                        f"Room “{label}” from drawing label (verify)"
                        if label
                        else "Room region detected from the scanned drawing (verify)"
                    ),
                )
                if cand is None:
                    continue
                replaced = False
                for i, prev in enumerate(out):
                    iou = _bbox_iou(cand["_bbox"], prev["_bbox"])
                    # Nested fragment inside a larger room → keep the larger /
                    # named one only (avoids stacked Area N boxes).
                    ax0, ay0, ax1, ay1 = cand["_bbox"]
                    bx0, by0, bx1, by1 = prev["_bbox"]
                    inter_w = max(0.0, min(ax1, bx1) - max(ax0, bx0))
                    inter_h = max(0.0, min(ay1, by1) - max(ay0, by0))
                    inter = inter_w * inter_h
                    aa = max(1e-9, (ax1 - ax0) * (ay1 - ay0))
                    ba = max(1e-9, (bx1 - bx0) * (by1 - by0))
                    nest = inter / min(aa, ba)
                    if iou >= _ROOM_IOU_DEDUP or nest >= 0.42:
                        prefer = False
                        if cand.get("label") and not prev.get("label"):
                            prefer = True
                        elif cand["confidence"] > prev["confidence"]:
                            prefer = True
                        elif aa > ba * 1.15 and not prev.get("label"):
                            prefer = True
                        if prefer:
                            out[i] = cand
                        replaced = True
                        break
                if not replaced:
                    out.append(cand)

    out = _merge_adjacent_room_rects(out, scale)
    for cand in out:
        cand.pop("_bbox", None)
        cand.pop("_poly_px", None)
    return out


def _merge_adjacent_room_rects(
    cands: list[dict[str, Any]], scale: float
) -> list[dict[str, Any]]:
    """Reassemble rooms that watershed split into two axis-aligned halves."""
    if len(cands) < 2:
        return cands

    def _is_rect(c: dict[str, Any]) -> bool:
        return len(c.get("points") or []) == 4

    def _bbox(c: dict[str, Any]) -> tuple[float, float, float, float]:
        return c["_bbox"]

    changed = True
    while changed:
        changed = False
        n = len(cands)
        for i in range(n):
            if not _is_rect(cands[i]):
                continue
            ax0, ay0, ax1, ay1 = _bbox(cands[i])
            aw, ah = ax1 - ax0, ay1 - ay0
            for j in range(i + 1, n):
                if not _is_rect(cands[j]):
                    continue
                bx0, by0, bx1, by1 = _bbox(cands[j])
                bw, bh = bx1 - bx0, by1 - by0
                # Vertical stack (shared horizontal edge)
                x_overlap = min(ax1, bx1) - max(ax0, bx0)
                y_gap = min(abs(ay1 - by0), abs(by1 - ay0))
                stacked = (
                    x_overlap >= 0.7 * min(aw, bw)
                    and y_gap <= max(4.0, 0.08 * min(ah, bh))
                    and abs(aw - bw) <= 0.25 * max(aw, bw)
                )
                # Horizontal stack (shared vertical edge)
                y_overlap = min(ay1, by1) - max(ay0, by0)
                x_gap = min(abs(ax1 - bx0), abs(bx1 - ax0))
                sided = (
                    y_overlap >= 0.7 * min(ah, bh)
                    and x_gap <= max(4.0, 0.08 * min(aw, bw))
                    and abs(ah - bh) <= 0.25 * max(ah, bh)
                )
                if not (stacked or sided):
                    continue
                # Never glue two differently named rooms (Living vs Dining).
                li, lj = cands[i].get("label"), cands[j].get("label")
                if li and lj and li != lj:
                    continue
                x0, y0 = min(ax0, bx0), min(ay0, by0)
                x1, y1 = max(ax1, bx1), max(ay1, by1)
                pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
                area_pt2 = _shoelace_area(pts)
                value = _area_value(area_pt2, scale)
                if scale and scale > 0 and (value is None or value <= 0):
                    continue
                label = li or lj
                merged = {
                    "type": "area",
                    "points": [{"x": p[0], "y": p[1]} for p in pts],
                    "value": value,
                    "dimension": "area",
                    "count": None,
                    "confidence": max(cands[i]["confidence"], cands[j]["confidence"], 0.55),
                    "reason": (
                        f"Room “{label}” from drawing label (verify)"
                        if label
                        else "Rectangular room region detected from the scanned drawing (verify)"
                    ),
                    "label": label,
                    "_bbox": (x0, y0, x1, y1),
                }
                cands = [c for k, c in enumerate(cands) if k not in (i, j)] + [merged]
                changed = True
                break
            if changed:
                break
    return cands


def _mask_polygon(mask: Any, *, force_rect: bool = False) -> list[Point] | None:
    """Simplified outer-contour polygon (in px) for a binary room mask.

    Near-rectangular fills may snap to a clean box. Arches, curves and
    irregular bays keep a dense contour so area polygons follow the walls.
    ``force_rect`` only forces an AABB when the fill is already almost
    rectangular — curved named rooms still keep their true outline.
    """
    try:
        work = mask
        if _ROOM_ERODE_PX > 0:
            k = cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE, (_ROOM_ERODE_PX * 2 + 1, _ROOM_ERODE_PX * 2 + 1)
            )
            eroded = cv2.erode(work, k, iterations=1)
            if int(cv2.countNonZero(eroded)) >= 32:
                work = eroded
        contours, _ = cv2.findContours(work, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if not contours:
            return None
        contour = max(contours, key=cv2.contourArea)
        area = float(cv2.contourArea(contour))
        if area < 16:
            return None
        peri = cv2.arcLength(contour, True)
        approx_loose = cv2.approxPolyDP(contour, _ROOM_APPROX_EPS_FRAC * peri, True)
        if len(approx_loose) < 3:
            return None
        x, y, bw, bh = cv2.boundingRect(contour)
        bbox_area = float(max(1, bw * bh))
        extent = area / bbox_area
        # Curved / irregular: many corners, loose bbox fill, or long perimeter.
        peri_ratio = (peri * peri) / max(area, 1.0)
        is_curved = len(approx_loose) >= 6 or extent < 0.85 or peri_ratio > 22.0
        eps = _ROOM_APPROX_EPS_CURVED if is_curved else _ROOM_APPROX_EPS_FRAC
        approx = cv2.approxPolyDP(contour, eps * peri, True)
        if len(approx) < 3:
            approx = approx_loose
        # Axis-aligned box only when the region is already a clean rectangle.
        if (
            (force_rect or extent >= _ROOM_AABB_EXTENT)
            and not is_curved
            and bw >= 12
            and bh >= 12
        ):
            return [
                (float(x), float(y)),
                (float(x + bw), float(y)),
                (float(x + bw), float(y + bh)),
                (float(x), float(y + bh)),
            ]
        rect = cv2.minAreaRect(contour)
        box = cv2.boxPoints(rect)
        rect_area = max(1.0, float(cv2.contourArea(box)))
        solidity = area / rect_area
        # Snap tidy / near-rect rooms to a rectangle — not curved bays.
        if (
            not is_curved
            and (extent >= _ROOM_RECT_MIN_EXTENT or solidity >= _ROOM_RECT_MIN_SOLIDITY)
            and len(approx) <= _ROOM_RECT_MAX_VERTS + 6
        ):
            return [(float(p[0]), float(p[1])) for p in box]
        # Prefer the convex hull when the room is mostly convex (doors nibble
        # corners but the usable takeoff area is still the rectangular bay).
        hull = cv2.convexHull(contour)
        hull_area = float(cv2.contourArea(hull)) or 1.0
        if (not is_curved) and area / hull_area >= 0.85:
            peri_h = cv2.arcLength(hull, True)
            approx_h = cv2.approxPolyDP(hull, max(_ROOM_APPROX_EPS_FRAC, 0.012) * peri_h, True)
            if len(approx_h) >= 3:
                return [(float(p[0][0]), float(p[0][1])) for p in approx_h]
        poly = [(float(p[0][0]), float(p[0][1])) for p in approx]
        if len(poly) > _ROOM_POLY_MAX_VERTS:
            # Re-simplify to the vertex budget while keeping the outer shape.
            step = max(1, len(poly) // _ROOM_POLY_MAX_VERTS)
            poly = poly[::step]
            if poly[0] != poly[-1] and len(poly) >= 3:
                pass
        return poly if len(poly) >= 3 else None
    except cv2.error:
        return None


def _detect_walls(gray: Any, to_pt, scale: float) -> list[dict[str, Any]]:
    """Long straight wall edges -> distance (length) candidates.

    Canny extracts wall edges and the probabilistic Hough transform fits line
    segments to them. Only segments longer than a fraction of the page diagonal
    are kept (short ones are hatching or annotation), near-duplicate segments
    are collapsed by endpoint grid, and the longest few are surfaced so the
    panel is not flooded. Segments whose midpoints sit outside the building
    footprint (title/caption/margins) are dropped.
    """
    h, w = gray.shape[:2]
    diag_px = math.hypot(w, h)
    min_len_px = max(1.0, _WALL_MIN_LEN_FRAC * diag_px)
    wall = _wall_mask(gray)
    footprint = None
    if wall is not None:
        try:
            free = _mask_exterior_free(cv2.bitwise_not(wall))
            ys, xs = np.where(free > 0)
            if len(xs) > 0:
                pad = max(8, int(min(h, w) * 0.02))
                x0 = max(0, int(xs.min()) - pad)
                y0 = max(0, int(ys.min()) - pad)
                x1 = min(w - 1, int(xs.max()) + pad)
                y1 = min(h - 1, int(ys.max()) + pad)
                footprint = (x0, y0, x1, y1)
        except cv2.error:
            footprint = None
    try:
        edges = cv2.Canny(gray, _CANNY_LO, _CANNY_HI)
        lines = cv2.HoughLinesP(
            edges,
            1,
            math.pi / 180,
            threshold=_HOUGH_VOTES,
            minLineLength=int(min_len_px),
            maxLineGap=_HOUGH_MAX_GAP_PX,
        )
    except cv2.error:
        return []
    if lines is None:
        return []

    segments: list[tuple[float, Point, Point]] = []
    for line in lines:
        # HoughLinesP rows are normally shaped (1, 4); some OpenCV/numpy
        # builds return a flat (4,) row instead, which makes line[0] a
        # scalar. Take the four coordinates regardless of that nesting.
        row = line[0] if hasattr(line[0], "__len__") else line
        x1, y1, x2, y2 = (float(v) for v in row)
        a, b = (x1, y1), (x2, y2)
        length_px = _seg_length(a, b)
        if length_px < min_len_px:
            continue
        if footprint is not None:
            mx, my = (a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5
            fx0, fy0, fx1, fy1 = footprint
            if not (fx0 <= mx <= fx1 and fy0 <= my <= fy1):
                continue
        segments.append((length_px, a, b))
    segments.sort(key=lambda s: -s[0])
    if not segments:
        return []

    span = segments[0][0] if segments else 1.0
    out: list[dict[str, Any]] = []
    seen: set[tuple[int, int, int, int]] = set()
    cell = _WALL_DEDUP_CELL_PX
    for length_px, a, b in segments:
        # Order-independent key so A->B and B->A collapse to one wall.
        ka = (round(a[0] / cell), round(a[1] / cell))
        kb = (round(b[0] / cell), round(b[1] / cell))
        key = (*min(ka, kb), *max(ka, kb))
        if key in seen:
            continue
        seen.add(key)
        a_pt, b_pt = to_pt(*a), to_pt(*b)
        # Longer edges relative to the longest are likelier to be real walls.
        confidence = round(min(0.50, 0.40 + 0.10 * (length_px / span)), 2)
        out.append(
            {
                "type": "distance",
                "points": [{"x": a_pt[0], "y": a_pt[1]}, {"x": b_pt[0], "y": b_pt[1]}],
                "value": _length_value(_seg_length(a_pt, b_pt), scale),
                "dimension": "length",
                "count": None,
                "confidence": confidence,
                "reason": "Wall line detected from the scan (verify)",
            }
        )
        if len(out) >= _MAX_WALLS:
            break
    return out


# ── public entry point ───────────────────────────────────────────────────────


def recognize_raster(
    image_bgr: Any,
    page_width_pt: float,
    page_height_pt: float,
    scale_pixels_per_unit: float | None,
    *,
    max_candidates: int = _MAX_CANDIDATES,
) -> list[dict[str, Any]]:
    """Detect rooms and walls in a rendered scanned page and rank candidates.

    Args:
        image_bgr: The rendered page as an ``HxWx3`` BGR ``np.ndarray`` (OpenCV
            convention). A single-channel grayscale array is also accepted.
        page_width_pt: PDF page width in points (used for the px -> pt map).
        page_height_pt: PDF page height in points.
        scale_pixels_per_unit: Viewer calibration in PDF points per real-world
            unit. When ``0`` / ``None`` every ``value`` is returned as ``None``
            (geometry only) so the user can calibrate, then accept.
        max_candidates: Hard cap on returned candidates.

    Returns:
        Candidate dicts in PDF point space, identical in shape to the vector
        recognizer's output, sorted by ``confidence`` descending and capped at
        ``max_candidates``. Returns ``[]`` on any unusable input rather than
        raising.
    """
    gray = _to_gray(image_bgr)
    if gray is None or gray.size == 0:
        return []
    h, w = gray.shape[:2]
    if h == 0 or w == 0 or page_width_pt <= 0 or page_height_pt <= 0:
        return []

    scale = float(scale_pixels_per_unit or 0.0)
    to_pt = _make_px_to_pt(w, h, page_width_pt, page_height_pt)

    rooms = _detect_rooms(gray, to_pt, scale)
    named_rooms = sum(1 for c in rooms if c.get("type") == "area" and c.get("label"))
    # Named room coverage is the takeoff signal — wall-length suggestions clutter
    # the overlay and fight room labels on dense modern plans.
    walls = _detect_walls(gray, to_pt, scale)
    if named_rooms >= 3:
        walls = walls[:2]
    candidates = rooms + walls
    candidates.sort(key=lambda c: c.get("confidence", 0.0), reverse=True)
    return candidates[:max_candidates]

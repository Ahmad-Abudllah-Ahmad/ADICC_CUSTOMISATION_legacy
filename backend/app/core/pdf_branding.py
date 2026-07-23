# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Shared company branding for every reportlab-generated PDF (issue #284).

Every PDF generator in the platform used to hard-code the literal
``"OpenConstructionERP"`` brand string, the ``#1a1a2e`` accent and the
author / creator document metadata. A workspace that white-labels the app
(see :mod:`app.core.app_branding` - the persisted logo / company name set by
the admin) therefore still printed the default brand on every exported
estimate, diary and invoice, which defeated the customisation (issue #284
follow-up to #272).

This module is the one place that turns the persisted branding into PDF
output, so wiring a generator is a 3-8 line swap rather than a copy of the
header / footer / metadata logic into each module:

* :func:`branded_header_footer` - an ``onPage(canvas, doc)`` callback that
  draws the workspace brand (the uploaded logo rasterised from its base64
  data URL, else the company name, else the default text) in the page header
  and a ``Generated ...`` line plus a page number in the footer. Geometry is
  read from the live ``doc`` (pagesize / margins) so it preserves whatever
  layout the calling generator already uses.
* :func:`branded_cover_brand` - the brand string for a cover-page title
  (logo cover art is out of scope for this MVP; the cover shows the name).
* :func:`branded_doc_metadata` - the ``author`` / ``creator`` / ``subject`` /
  ``producer`` / ``keywords`` to stamp on the ``DocTemplate`` so the file's
  document properties also carry the workspace brand.

Everything degrades gracefully and NEVER raises (mirrors the never-break
contract of :mod:`app.core.pdf_stamp`): a logo that fails to decode falls
back to the company name, an empty company name falls back to the default
brand, and any failure reading the persisted branding falls back to the
default too. A failed brand draw must never break a PDF export.

Deferred follow-up (out of scope for this MVP, by design): a configurable
template engine - per-workspace margins / fonts / colours / header layout /
footer text - and rendering the logo as cover-page art. Today the accent
colour and geometry stay the platform defaults; only the brand identity
(logo / name) and document metadata follow the workspace.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

#: The brand shown when no workspace branding is set (or it cannot be read).
DEFAULT_BRAND = "OpenConstructionERP"

#: Footer text colour and header brand colour - the platform default accent.
#: Kept module-level (not configurable in this MVP) so every PDF stays
#: visually consistent; a future template engine may make these per-workspace.
_FOOTER_COLOR = "#999999"
_HEADER_COLOR = "#1a1a2e"

#: Header logo box (points). The logo is scaled to fit inside this box while
#: keeping its aspect ratio; a wordmark therefore stays legible and a square
#: mark never overflows the header band.
_LOGO_MAX_W = 130.0
_LOGO_MAX_H = 22.0


def _read_branding() -> dict[str, Any]:
    """Return the persisted workspace branding, or defaults, never raising.

    Imported lazily so this module stays import-safe (and unit-testable
    without the app package) and so any failure reading the branding - a
    missing dependency, a corrupt file, anything - degrades to the default
    brand instead of breaking a PDF export.
    """
    try:
        from app.core.app_branding import read_branding

        data = read_branding()
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001 - degrade, never break PDF output
        logger.debug("Could not read workspace branding; using default", exc_info=True)
        return {}


def _company_name(branding: dict[str, Any] | None = None) -> str:
    """Return the trimmed company name, or the default brand when unset."""
    data = branding if branding is not None else _read_branding()
    name = data.get("company_name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return DEFAULT_BRAND


def branded_cover_brand() -> str:
    """Return the brand string for a cover-page title.

    The uploaded logo is not rendered as cover art in this MVP (deferred to a
    future template engine); the cover shows the workspace company name, or
    the default brand when none is set. Never raises.
    """
    return _company_name()


def branded_doc_metadata() -> dict[str, str]:
    """Return reportlab ``DocTemplate`` metadata derived from the brand.

    Brand-aware so a white-labelled workspace never leaks the platform name into
    a file's document properties (issue #284 follow-up):

    * a workspace with its own company name attributes every field to that name;
    * a logo-only workspace (custom logo, no name) stays brand-neutral rather
      than printing the platform default in the metadata;
    * an un-customised workspace keeps the platform credit so default exports
      stay attributable.

    Never raises - a branding read failure yields the default-brand metadata.
    """
    branding = _read_branding()
    name = _company_name(branding)
    if branding.get("mode") in ("logo", "text") and name != DEFAULT_BRAND:
        return {
            "author": name,
            "creator": name,
            "subject": f"Generated by {name}",
            "producer": name,
            "keywords": name,
        }
    if branding.get("mode") == "logo":
        # Logo-only white-label with no company name: describe by function, do
        # not fall back to the platform brand in the metadata.
        neutral = "Construction cost management"
        return {
            "author": neutral,
            "creator": neutral,
            "subject": f"Generated by a {neutral.lower()} platform",
            "producer": neutral,
            "keywords": "",
        }
    return {
        "author": DEFAULT_BRAND,
        "creator": DEFAULT_BRAND,
        "subject": f"Generated by {DEFAULT_BRAND}",
        "producer": f"{DEFAULT_BRAND} / reportlab - datadrivenconstruction.io",
        "keywords": f"{DEFAULT_BRAND},DataDrivenConstruction",
    }


def _draw_logo(
    canvas: Any,
    branding: dict[str, Any],
    *,
    top_y: float,
    x: float | None = None,
    right_x: float | None = None,
) -> bool:
    """Try to draw the workspace logo in the header. Return True on success.

    Rasterises the ``logo_data_url`` (a base64 ``data:image/...`` URL) via
    reportlab's ``ImageReader`` and draws it scaled to fit the header logo
    box, top-aligned at ``top_y`` and left-aligned at ``x``. Any decode /
    draw failure returns ``False`` so the caller falls back to the text brand;
    it never raises.
    """
    logo = branding.get("logo_data_url")
    if not (isinstance(logo, str) and logo.startswith("data:image/") and "base64," in logo):
        return False
    try:
        import base64
        from io import BytesIO

        from reportlab.lib.utils import ImageReader

        b64 = logo.split("base64,", 1)[1]
        raw = base64.b64decode(b64, validate=False)
        if not raw:
            return False
        reader = ImageReader(BytesIO(raw))
        iw, ih = reader.getSize()
        if not iw or not ih:
            return False
        # Scale to fit the logo box while preserving aspect ratio.
        scale = min(_LOGO_MAX_W / float(iw), _LOGO_MAX_H / float(ih), 1.0)
        draw_w = float(iw) * scale
        draw_h = float(ih) * scale
        # Left-aligned at ``x`` by default, or right-aligned so the logo's right
        # edge sits at ``right_x`` when that is supplied instead.
        draw_x = (right_x - draw_w) if right_x is not None else (x if x is not None else 0.0)
        canvas.drawImage(
            reader,
            draw_x,
            top_y - draw_h,
            width=draw_w,
            height=draw_h,
            preserveAspectRatio=True,
            mask="auto",
        )
        return True
    except Exception:  # noqa: BLE001 - fall back to the text brand, never raise
        logger.debug("Could not rasterise workspace logo for PDF header", exc_info=True)
        return False


def branded_header_footer(canvas: Any, doc: Any) -> None:
    """``onPage(canvas, doc)`` callback drawing the brand header and footer.

    Reads the persisted branding once per call and draws:

    * a header band with the workspace logo (rasterised from its base64 data
      URL) or, failing that, the company name / default brand as text, plus a
      thin rule under it;
    * a footer with ``<brand>  |  Generated: <date>`` on the left and
      ``Page X`` / ``Page X of Y`` (when the doc tracks ``page_count``) on the
      right.

    Geometry is taken from the live ``doc`` (``pagesize`` and the four
    margins), so the brand lands consistently regardless of which generator's
    layout is in use. Never raises - a failure to draw the brand must not
    break the PDF, so the whole body is guarded.
    """
    try:
        from reportlab.lib import colors

        from app.core.pdf_fonts import BODY_FONT, BOLD_FONT

        branding = _read_branding()

        page_w, page_h = _page_size(doc)
        left = float(getattr(doc, "leftMargin", 56.0) or 56.0)
        right_margin = float(getattr(doc, "rightMargin", 56.0) or 56.0)
        right_x = page_w - right_margin

        canvas.saveState()

        # -- Header: logo or brand text, with a thin rule under it. --
        header_baseline = page_h - 15.0 * MM
        drew_logo = _draw_logo(canvas, branding, x=left, top_y=page_h - 8.0 * MM)
        if not drew_logo:
            canvas.setFont(BOLD_FONT, 9)
            canvas.setFillColor(colors.HexColor(_HEADER_COLOR))
            canvas.drawString(left, header_baseline, _company_name(branding)[:80])
        canvas.setStrokeColor(colors.HexColor("#cccccc"))
        canvas.setLineWidth(0.5)
        line_y = page_h - 17.0 * MM
        canvas.line(left, line_y, right_x, line_y)

        # -- Footer: brand + generated date (left), page number (right). --
        canvas.setFont(BODY_FONT, 7)
        canvas.setFillColor(colors.HexColor(_FOOTER_COLOR))
        generated = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        canvas.drawString(
            left,
            10.0 * MM,
            f"{_company_name(branding)}  |  Generated: {generated}"[:160],
        )
        if getattr(doc, "page_count", 0) > 0:
            page_text = f"Page {doc.page} of {doc.page_count}"
        else:
            page_text = f"Page {getattr(doc, 'page', 1)}"
        canvas.drawRightString(right_x, 10.0 * MM, page_text)

        canvas.restoreState()
    except Exception:  # noqa: BLE001 - brand draw must never break a PDF export
        logger.debug("branded_header_footer draw failed; page left unbranded", exc_info=True)
        # Best-effort: balance the graphics state if we managed to save it.
        try:
            canvas.restoreState()
        except Exception:  # noqa: BLE001
            pass


# One millimetre in points - reportlab's unit, inlined so this module needs no
# import-time reportlab dependency (the lazy imports above keep it import-safe).
MM = 72.0 / 25.4


def _page_size(doc: Any) -> tuple[float, float]:
    """Return the (width, height) of the doc's page in points, A4 as fallback."""
    size = getattr(doc, "pagesize", None)
    try:
        if size is not None:
            return float(size[0]), float(size[1])
    except (TypeError, ValueError, IndexError):
        pass
    # A4 in points.
    return 595.2755905511812, 841.8897637795277


def branded_header_logo(canvas: Any, doc: Any, *, align: str = "right") -> bool:
    """Draw ONLY the uploaded workspace logo in a top corner of the header.

    For generators that already render their own header text (e.g. the project
    and document name) and only need the white-label logo to appear when one is
    configured. Draws nothing and returns ``False`` when no logo is set, so a
    name-only or default workspace is unaffected. Right-aligned by default so it
    clears a left-aligned header title; pass ``align="left"`` otherwise.
    Geometry is read from the live ``doc``. Never raises - a failed logo draw
    must not break the PDF export.
    """
    try:
        branding = _read_branding()
        if not branding.get("logo_data_url"):
            return False
        page_w, page_h = _page_size(doc)
        top_y = page_h - 8.0 * MM
        if align == "left":
            left = float(getattr(doc, "leftMargin", 56.0) or 56.0)
            return _draw_logo(canvas, branding, x=left, top_y=top_y)
        right_margin = float(getattr(doc, "rightMargin", 56.0) or 56.0)
        return _draw_logo(canvas, branding, right_x=page_w - right_margin, top_y=top_y)
    except Exception:  # noqa: BLE001 - a header logo must never break a PDF export
        logger.debug("branded_header_logo skipped (draw failed)", exc_info=True)
        return False


__all__ = [
    "DEFAULT_BRAND",
    "branded_cover_brand",
    "branded_doc_metadata",
    "branded_header_footer",
    "branded_header_logo",
]

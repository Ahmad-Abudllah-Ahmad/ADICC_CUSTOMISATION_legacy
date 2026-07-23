# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Unicode font registration for every reportlab-generated PDF.

OpenEstimate principle #2 is *i18n EVERYWHERE*. reportlab's built-in Type-1
fonts (Helvetica / Times / Courier) are Latin-1 only, so any PDF that renders
Cyrillic (ru, bg, uk, sr), Greek, or the many accented Latin scripts with the
default font shows empty boxes ("tofu") instead of text. A construction ERP
that ships 27 locales but prints unreadable invoices and contracts in half of
them is broken.

This module bundles **DejaVu Sans** (regular + bold) and registers it with
reportlab once per process. DejaVu covers Latin, Latin-Extended, Cyrillic and
Greek - i.e. every locale this product ships *except* the complex scripts
(Arabic, Hebrew, the CJK languages, Thai, Devanagari), which need much larger
Noto fonts and proper bidi/shaping; those remain a documented follow-up. For
the covered scripts the fix is complete: glyphs render, not boxes.

Usage in a generator::

    from app.core.pdf_fonts import BODY_FONT, BOLD_FONT, register_pdf_fonts

    register_pdf_fonts()            # idempotent; call once at the top
    canvas.setFont(BODY_FONT, 10)   # instead of "Helvetica"
    canvas.setFont(BOLD_FONT, 12)   # instead of "Helvetica-Bold"

``register_pdf_fonts()`` is safe to call from many generators and many times;
it registers at most once and never raises if the bundled TTFs are missing
(it falls back to Helvetica and logs a warning, so PDF generation degrades
rather than crashing).
"""

from __future__ import annotations

import logging
from pathlib import Path
from threading import Lock

logger = logging.getLogger(__name__)

_FONT_DIR = Path(__file__).resolve().parent / "fonts"

#: Registered font names. When registration succeeds these are the DejaVu
#: faces; if the bundled TTFs are somehow unavailable they fall back to the
#: reportlab built-ins so callers never crash (only lose non-Latin glyphs).
BODY_FONT = "DejaVuSans"
BOLD_FONT = "DejaVuSans-Bold"

_FALLBACK_BODY = "Helvetica"
_FALLBACK_BOLD = "Helvetica-Bold"

# Map the reportlab built-in names every legacy generator hard-codes to the
# Unicode faces, so wiring an existing generator is a one-line swap via
# pdf_font("Helvetica") rather than touching every setFont call by hand.
_HELVETICA_MAP = {
    "Helvetica": BODY_FONT,
    "Helvetica-Bold": BOLD_FONT,
    "Helvetica-Oblique": BODY_FONT,
    "Helvetica-BoldOblique": BOLD_FONT,
}

_lock = Lock()
_registered: bool | None = None  # None = not attempted, True/False = outcome


def register_pdf_fonts() -> bool:
    """Register the bundled DejaVu faces with reportlab. Idempotent.

    Returns ``True`` when the Unicode faces are available (either just
    registered or registered earlier in this process), ``False`` when the
    bundled TTFs could not be loaded and callers should expect the
    Helvetica fallback. Never raises.
    """
    global _registered, BODY_FONT, BOLD_FONT
    if _registered is not None:
        return _registered

    with _lock:
        if _registered is not None:
            return _registered

        try:
            from reportlab.lib.fonts import addMapping
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont

            regular = _FONT_DIR / "DejaVuSans.ttf"
            bold = _FONT_DIR / "DejaVuSans-Bold.ttf"
            if not regular.is_file() or not bold.is_file():
                raise FileNotFoundError(f"bundled DejaVu TTFs missing in {_FONT_DIR}")

            # The _registered gate guarantees this body runs at most once per
            # process, so a plain registerFont is enough (no need to probe the
            # registry first).
            pdfmetrics.registerFont(TTFont("DejaVuSans", str(regular)))
            pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", str(bold)))

            # Let Paragraph markup (<b>, <i>) resolve to the right face. We only
            # bundle regular + bold, so italic maps onto the upright faces.
            pdfmetrics.registerFontFamily(
                "DejaVuSans",
                normal="DejaVuSans",
                bold="DejaVuSans-Bold",
                italic="DejaVuSans",
                boldItalic="DejaVuSans-Bold",
            )
            addMapping("DejaVuSans", 0, 0, "DejaVuSans")
            addMapping("DejaVuSans", 1, 0, "DejaVuSans-Bold")
            addMapping("DejaVuSans", 0, 1, "DejaVuSans")
            addMapping("DejaVuSans", 1, 1, "DejaVuSans-Bold")

            _registered = True
            logger.debug("PDF fonts: registered DejaVu Sans (regular + bold)")
        except Exception as exc:  # noqa: BLE001 - degrade, never break PDF output
            BODY_FONT = _FALLBACK_BODY
            BOLD_FONT = _FALLBACK_BOLD
            _registered = False
            logger.warning(
                "PDF fonts: could not register DejaVu (%s); falling back to Helvetica - non-Latin text may not render",
                exc,
            )
        return _registered


def pdf_font(name: str, *, bold: bool = False) -> str:
    """Resolve a font name to its Unicode-capable equivalent.

    Accepts a reportlab built-in name (``"Helvetica"`` / ``"Helvetica-Bold"``)
    and returns the registered DejaVu face, or honours an explicit ``bold``
    flag. Registers fonts on first use so callers need not remember to.

    When DejaVu registration failed (bundled TTFs missing) it returns the
    matching reportlab built-in instead, so the caller always gets a name
    reportlab can actually resolve.
    """
    ok = register_pdf_fonts()
    if not ok:
        want_bold = bold or name in ("Helvetica-Bold", "Helvetica-BoldOblique")
        return _FALLBACK_BOLD if want_bold else _FALLBACK_BODY
    if name in _HELVETICA_MAP:
        return _HELVETICA_MAP[name]
    if bold:
        return BOLD_FONT
    return name or BODY_FONT


# Register eagerly, at import time. Generators capture the face names with
# ``from app.core.pdf_fonts import BODY_FONT, BOLD_FONT``, which snapshots the
# string values at the moment of import. If registration only ran later (inside
# a generator), the Helvetica fallback - implemented by reassigning these module
# globals on failure - would never reach the names those modules already bound,
# so an install with the bundled TTFs missing would hand reportlab the
# unregistered "DejaVuSans" and raise instead of degrading gracefully. Running
# it here finalises BODY_FONT / BOLD_FONT before any importer can read them, and
# the _registered gate keeps every later call a no-op.
register_pdf_fonts()


__all__ = ["BODY_FONT", "BOLD_FONT", "pdf_font", "register_pdf_fonts"]

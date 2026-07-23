# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
"""Construction-aware spelling correction for the Cost Explorer text search.

An estimator in a hurry mistypes the word they know: ``concreet`` for concrete,
``plasterbord`` for plasterboard, ``screeed`` for screed. A plain lexical search
then dead-ends on zero results even though the price book is full of the work
they meant. This module turns a mistyped query into a *suggested* corrected
query so the UI can offer a dismissable "did you mean" chip, and never silently
rewrites what the user asked for.

The correction is deliberately conservative and scoped so it never touches a
value that only looks like a word:

* A token that carries a digit, slash or any other non-letter is left untouched,
  so a concrete grade (``C30/37``), a steel grade (``B500B``, ``S355``) or a rate
  code (``20.01.001``) is never "corrected".
* Only a curated domain misspelling (:data:`_MISSPELLINGS`) is corrected. There
  is no fuzzy edit-distance guessing, so a valid but out-of-lexicon word (for
  example ``pointing``) is never mangled into a look-alike (``painting``).

Pure and stdlib-only (``re`` + ``unicodedata``), so it imports and unit-tests on
any interpreter, independent of the FastAPI dependency graph. The seed lexicon
is English; per-locale lexicons can be layered on later behind the same API.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence

# Shortest token worth examining. Below this a "correction" is as likely to
# mangle an abbreviation or a unit (``mm``, ``no``, ``m2``) as to help.
_MIN_LEN = 4

# Leading / trailing punctuation stripped off a raw whitespace-split token before
# it is examined, so ``concreet,`` or ``(concreet)`` is still recognised.
_EDGE_PUNCT = "\"'`.,;:!?()[]{}<>/\\|-_"

# Curated domain misspelling -> correct spelling for the words estimators mistype
# most, grouped by trade. Keys are folded (lowercase, accent-free) typos; values
# are the correct domain word. Seed only - deliberately English and terminal (a
# value is never itself a key), so one pass fully corrects. Per-locale lexicons
# can be layered on later behind the same API. Valid alternate spellings that are
# NOT typos (``aluminum``, ``labor``, ``galvanized``) are intentionally absent so
# they are never "corrected" to another region's spelling.
_MISSPELLINGS: dict[str, str] = {
    # Concrete / cement / mortar / screed / grout
    "concreet": "concrete",
    "concreete": "concrete",
    "concrte": "concrete",
    "conrete": "concrete",
    "cocrete": "concrete",
    "concrette": "concrete",
    "cementt": "cement",
    "cemnet": "cement",
    "sement": "cement",
    "morter": "mortar",
    "mortor": "mortar",
    "screeed": "screed",
    "screedd": "screed",
    "skreed": "screed",
    "growt": "grout",
    "graut": "grout",
    # Plaster / plasterboard / render
    "plasterbord": "plasterboard",
    "plasterboad": "plasterboard",
    "plasterbaord": "plasterboard",
    "platerboard": "plasterboard",
    "plasterr": "plaster",
    "plastr": "plaster",
    "renderr": "render",
    "rendr": "render",
    # Reinforcement / rebar / steel
    "reinforcment": "reinforcement",
    "reinforcemnt": "reinforcement",
    "reenforcement": "reinforcement",
    "reinforcemet": "reinforcement",
    "reinforcemen": "reinforcement",
    "rebarr": "rebar",
    "stell": "steel",
    "steeel": "steel",
    # Formwork / shuttering / scaffolding
    "formwrk": "formwork",
    "formwrok": "formwork",
    "fomwork": "formwork",
    "shutterring": "shuttering",
    "shutering": "shuttering",
    "shuttring": "shuttering",
    "scafold": "scaffold",
    "scaffld": "scaffold",
    "scafolding": "scaffolding",
    "scaffholding": "scaffolding",
    "scaffoding": "scaffolding",
    # Brick / block / masonry
    "brik": "brick",
    "birck": "brick",
    "blok": "block",
    "blcok": "block",
    "brikwork": "brickwork",
    "blokwork": "blockwork",
    "masonary": "masonry",
    "masonery": "masonry",
    "mansonry": "masonry",
    # Insulation / waterproofing / membrane
    "insualtion": "insulation",
    "insulaton": "insulation",
    "insulatoin": "insulation",
    "insualation": "insulation",
    "waterprofing": "waterproofing",
    "waterproffing": "waterproofing",
    "watrproofing": "waterproofing",
    "waterproofng": "waterproofing",
    "membrne": "membrane",
    "membrain": "membrane",
    "membrance": "membrane",
    # Excavation / earthwork
    "excavaton": "excavation",
    "excevation": "excavation",
    "exavation": "excavation",
    "excavtion": "excavation",
    # Asphalt / aggregate / gravel
    "ashphalt": "asphalt",
    "asphlat": "asphalt",
    "asfalt": "asphalt",
    "agregate": "aggregate",
    "aggregat": "aggregate",
    "aggreate": "aggregate",
    "agrigate": "aggregate",
    "gravle": "gravel",
    # Timber / plywood / paint / primer
    "timbr": "timber",
    "timmber": "timber",
    "plywd": "plywood",
    "plywod": "plywood",
    "plywoood": "plywood",
    "paitn": "paint",
    "panit": "paint",
    "pianting": "painting",
    "primmer": "primer",
    # Tiling / ceramic / glazing / cladding / flashing
    "tilng": "tiling",
    "tilinng": "tiling",
    "ceramc": "ceramic",
    "cermaic": "ceramic",
    "glazng": "glazing",
    "glaizing": "glazing",
    "claddng": "cladding",
    "claddin": "cladding",
    "cladin": "cladding",
    "flashng": "flashing",
    "flasing": "flashing",
    # Drainage / piping / ducts / conduit
    "draiage": "drainage",
    "drainge": "drainage",
    "dranage": "drainage",
    "pipeing": "piping",
    "ductwrk": "ductwork",
    "ducwork": "ductwork",
    "condut": "conduit",
    "condiut": "conduit",
    # Flooring / ceiling / partition / foundation / column / lintel
    "floorng": "flooring",
    "floooring": "flooring",
    "floring": "flooring",
    "ceilng": "ceiling",
    "cieling": "ceiling",
    "parition": "partition",
    "partiton": "partition",
    "foundaton": "foundation",
    "foudation": "foundation",
    "foundatoin": "foundation",
    "colmn": "column",
    "coloumn": "column",
    "lintle": "lintel",
    # Sealant / adhesive / bitumen / gypsum
    "sealent": "sealant",
    "seelant": "sealant",
    "sealnt": "sealant",
    "adhesiv": "adhesive",
    "adhessive": "adhesive",
    "adhesve": "adhesive",
    "bituman": "bitumen",
    "bitumin": "bitumen",
    "bitumn": "bitumen",
    "gypsom": "gypsum",
    "gipsum": "gypsum",
    "gypsm": "gypsum",
    # Aluminium / galvanised
    "alumnium": "aluminium",
    "aluminuim": "aluminium",
    "alumninium": "aluminium",
    "aluminim": "aluminium",
    "galvinised": "galvanised",
    "galvenised": "galvanised",
    "galvanissed": "galvanised",
    # Demolition / landscaping / paving / fencing
    "demoliton": "demolition",
    "demolision": "demolition",
    "demolation": "demolition",
    "landscapng": "landscaping",
    "landscaing": "landscaping",
    "pavng": "paving",
    "paveing": "paving",
    "fencng": "fencing",
    "fenceing": "fencing",
}


def _fold(text: str) -> str:
    """Lowercase and strip accents/diacritics for lexicon comparison.

    Decomposes accented Latin letters and drops the combining marks (``Béton``
    folds to ``beton``), trims surrounding whitespace and lowercases. Non-Latin
    scripts carry no combining marks here and survive unchanged.

    Args:
        text: The raw token or string to normalise.

    Returns:
        The folded string (may be empty).
    """
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.strip().lower()


def correct_token(token: str) -> str | None:
    """Return the corrected domain spelling of one token, or ``None``.

    A token is corrected only when its folded, punctuation-trimmed form is a
    known domain misspelling. A token that carries a digit, slash or any other
    non-letter (a grade such as ``C30/37`` or ``B500B``, or a rate code such as
    ``20.01.001``) is never corrected, and neither is a token already spelled
    correctly.

    Args:
        token: A single search token (as split on whitespace by the caller).

    Returns:
        The corrected word (lowercase) when a domain misspelling is recognised,
        otherwise ``None``.
    """
    core = _fold(token).strip(_EDGE_PUNCT)
    if len(core) < _MIN_LEN:
        return None
    if not core.isalpha():
        # Carries a digit / slash / other symbol: a grade or code, never a word.
        return None
    corrected = _MISSPELLINGS.get(core)
    if corrected and corrected != core:
        return corrected
    return None


def suggest_from_tokens(tokens: Sequence[str]) -> str | None:
    """Suggest a corrected query from already-split tokens, or ``None``.

    Each token is passed through :func:`correct_token`; corrected tokens are
    replaced by their domain spelling while every other token (including grades
    and codes) is kept verbatim, preserving its position and case. Returns the
    rejoined query only when at least one token was corrected, so a well-formed
    query yields no suggestion.

    Args:
        tokens: The search tokens, in order.

    Returns:
        The corrected query string, or ``None`` when nothing was corrected.
    """
    changed = False
    out: list[str] = []
    for token in tokens:
        corrected = correct_token(token)
        if corrected is not None:
            out.append(corrected)
            changed = True
        else:
            out.append(token)
    return " ".join(out) if changed else None


def suggest_query(query: str) -> str | None:
    """Suggest a corrected query for a free-text search, or ``None``.

    Convenience wrapper over :func:`suggest_from_tokens` that splits the query on
    whitespace first. A blank or whitespace-only query yields no suggestion.

    Args:
        query: The raw free-text query.

    Returns:
        The corrected query string, or ``None`` when nothing was corrected.
    """
    if not query or not query.strip():
        return None
    tokens = [tok for tok in re.split(r"\s+", query.strip()) if tok]
    return suggest_from_tokens(tokens)

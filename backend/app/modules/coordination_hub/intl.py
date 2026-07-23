# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""International, database-free helpers for the Coordination Hub.

Everything in this file is a pure function: no session, no I/O, no module
state that a request can mutate. That keeps the coordination arithmetic
easy to reason about, easy to unit-test without a database, and safe to
reuse from the service layer, an export, or a future report.

Why this file exists
    A BIM model can be authored in any language. The discipline label on
    a clash therefore arrives as "Structural", "Tragwerk", "Estructura",
    "Struttura" or "конструкции" depending on who exported it. An
    English-only lookup silently drops every non-English label into the
    catch-all bucket and loses the signal. :func:`normalise_trade` folds
    case and accents and maps the common labels in English, German,
    French, Spanish, Italian and Russian onto the six canonical trades
    the dashboard uses.

    The same care applies to money and to the small aggregates the
    dashboard shows. Money is kept as :class:`~decimal.Decimal` for exact
    arithmetic and is NEVER summed across two different currency codes.
    Rates guard against division by zero. Counts guard against an empty
    input. Nothing here can raise a 500, produce a ``NaN`` / ``inf``, or
    return a silently wrong number: a bad input is either a clean
    :class:`ValueError` or a well-defined zero.

Vocabulary
    The six canonical trades come from
    :data:`app.modules.coordination_hub.schemas.CANONICAL_TRADES`
    (``arch``, ``struct``, ``mep``, ``landscape``, ``civil``, ``other``).
    Mechanical, electrical and plumbing all fold into ``mep`` because the
    coordination dashboard groups building services as one column; the
    sibling cost module keeps them apart for its rework-hours table. The
    two modules stay decoupled (no import between them) but share the same
    folding approach so behaviour is consistent.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation

from app.modules.coordination_hub.schemas import CANONICAL_TRADES

# ── Discipline label normalisation (multilingual) ───────────────────────────


def _fold(value: str) -> str:
    """Lower-case and strip accents so "Tragwerk" and "tragwerk" hit one key.

    Accents are removed via NFKD decomposition, dropping the combining
    marks; non-Latin scripts (for example Cyrillic) are left intact and
    simply lower-cased. Surrounding whitespace is trimmed and internal
    runs of whitespace collapse to a single space so "genie  civil" and
    "genie civil" match.
    """
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(without_marks.split()).lower()


#: Free-text discipline aliases in six languages, each mapping onto one of
#: the six canonical trades. BIM exports label disciplines in the project's
#: own language, so an English-only table quietly lost every German,
#: French, Spanish, Italian or Russian label. Keys are folded to accent-free
#: lower case at import time (see :func:`_fold`) so "Sanitär" and "sanitar"
#: both resolve. Mechanical, electrical and plumbing all roll up to ``mep``.
_RAW_TRADE_ALIASES: dict[str, str] = {
    # ── Architecture ───────────────────────────────────────────────
    # English
    "arch": "arch",
    "architect": "arch",
    "architects": "arch",
    "architectural": "arch",
    "architecture": "arch",
    # German
    "architektur": "arch",
    # Spanish
    "arquitectura": "arch",
    "arquitectonico": "arch",
    # Italian
    "architettura": "arch",
    "architettonico": "arch",
    # Russian
    "arhitektura": "arch",  # transliterated exports
    "архитектура": "arch",
    "ар": "arch",
    # ── Structure ──────────────────────────────────────────────────
    # English
    "struct": "struct",
    "structure": "struct",
    "structural": "struct",
    "structures": "struct",
    # German
    "tragwerk": "struct",
    "tragwerksplanung": "struct",
    "statik": "struct",
    # French
    "charpente": "struct",
    # Spanish
    "estructura": "struct",
    "estructural": "struct",
    "estructuras": "struct",
    # Italian
    "struttura": "struct",
    "strutturale": "struct",
    "strutture": "struct",
    # Russian
    "konstrukcii": "struct",
    "конструкции": "struct",
    "конструкция": "struct",
    "кж": "struct",
    "км": "struct",
    # ── Building services (MEP) ────────────────────────────────────
    # English
    "mep": "mep",
    "mechanical": "mep",
    "mech": "mep",
    "hvac": "mep",
    "electrical": "mep",
    "elec": "mep",
    "elect": "mep",
    "plumbing": "mep",
    "plumb": "mep",
    "pl": "mep",
    "fire": "mep",
    "sprinkler": "mep",
    "services": "mep",
    "building services": "mep",
    # German
    "elektro": "mep",
    "elektrik": "mep",
    "sanitaer": "mep",
    "sanitär": "mep",
    "lueftung": "mep",
    "lüftung": "mep",
    "hlk": "mep",
    "hlks": "mep",
    "heizung": "mep",
    "klima": "mep",
    "tga": "mep",
    # French
    "electricite": "mep",
    "électricité": "mep",
    "plomberie": "mep",
    "cvc": "mep",
    "mecanique": "mep",
    "mécanique": "mep",
    "chauffage": "mep",
    "ventilation": "mep",
    "fluides": "mep",
    # Spanish
    "electricidad": "mep",
    "fontaneria": "mep",
    "fontanería": "mep",
    "mecanica": "mep",
    "mecánica": "mep",
    "climatizacion": "mep",
    "climatización": "mep",
    "instalaciones": "mep",
    # Italian
    "elettrico": "mep",
    "impianti": "mep",
    "idraulica": "mep",
    "meccanica": "mep",
    "climatizzazione": "mep",
    # Russian
    "elektrika": "mep",
    "электрика": "mep",
    "сантехника": "mep",
    "вентиляция": "mep",
    "отопление": "mep",
    "ов": "mep",
    "вк": "mep",
    "эом": "mep",
    # ── Landscape ──────────────────────────────────────────────────
    # English
    "landscape": "landscape",
    "landscaping": "landscape",
    "planting": "landscape",
    # German
    "landschaft": "landscape",
    "freianlagen": "landscape",
    "garten": "landscape",
    # French
    "paysage": "landscape",
    "amenagement paysager": "landscape",
    # Spanish
    "paisaje": "landscape",
    "paisajismo": "landscape",
    "jardineria": "landscape",
    "jardinería": "landscape",
    # Italian
    "paesaggio": "landscape",
    "giardino": "landscape",
    # Russian
    "landshaft": "landscape",
    "ландшафт": "landscape",
    "озеленение": "landscape",
    # ── Civil / infrastructure ─────────────────────────────────────
    # English
    "civil": "civil",
    "site": "civil",
    "sitework": "civil",
    "siteworks": "civil",
    "infrastructure": "civil",
    "earthworks": "civil",
    "groundworks": "civil",
    "road": "civil",
    "roads": "civil",
    "drainage": "civil",
    # German
    "tiefbau": "civil",
    "erdbau": "civil",
    "strassenbau": "civil",
    "straßenbau": "civil",
    # French
    "genie civil": "civil",
    "génie civil": "civil",
    "vrd": "civil",
    "terrassement": "civil",
    # Spanish
    "obra civil": "civil",
    "urbanizacion": "civil",
    "urbanización": "civil",
    "movimiento de tierras": "civil",
    # Italian
    "opere civili": "civil",
    "genio civile": "civil",
    "movimento terra": "civil",
    # Russian
    "genplan": "civil",
    "генплан": "civil",
    "дороги": "civil",
    "инфраструктура": "civil",
    # ── Explicit catch-all ─────────────────────────────────────────
    "other": "other",
    "unknown": "other",
    "misc": "other",
    "general": "other",
}


#: The alias table actually consulted, keyed the same way an incoming label
#: is folded, so lookups match regardless of case or accents.
TRADE_ALIASES: dict[str, str] = {_fold(key): value for key, value in _RAW_TRADE_ALIASES.items()}


def normalise_trade(value: str | None) -> str:
    """Collapse a free-text discipline label to one of the canonical trades.

    Recognises the common variants the BIM importers produce in English,
    German, French, Spanish, Italian and Russian (``"Structural"``,
    ``"Tragwerk"``, ``"Estructura"``, ``"Struttura"``, ``"конструкции"``,
    ...) by folding case and accents and mapping through
    :data:`TRADE_ALIASES`. A label that is already a canonical trade is
    returned unchanged. Anything unrecognised, empty or ``None`` lands on
    ``"other"`` so a clash is never silently dropped from the matrix.

    Args:
        value: The raw discipline label, in any language, or ``None``.

    Returns:
        One of :data:`~app.modules.coordination_hub.schemas.CANONICAL_TRADES`.
    """
    if not value:
        return "other"
    folded = _fold(value)
    if not folded:
        return "other"
    if folded in CANONICAL_TRADES:
        return folded
    return TRADE_ALIASES.get(folded, "other")


#: One-line, plain-language description of each canonical trade, so a label
#: in the UI or an export can carry a tooltip a site engineer understands.
_TRADE_DESCRIPTIONS: dict[str, str] = {
    "arch": "Architecture: layout, finishes and the building envelope.",
    "struct": "Structure: the load-bearing frame, slabs and foundations.",
    "mep": "Building services (MEP): mechanical, electrical and plumbing, including HVAC, fire and heating.",
    "landscape": "Landscape: external planting, gardens and soft site areas.",
    "civil": "Civil and infrastructure: earthworks, roads, drainage and site utilities.",
    "other": "Other: a discipline that did not match a known trade.",
}


def describe_trade(trade: str | None) -> str:
    """Return a one-line plain-language description of a canonical trade.

    The input is normalised first, so a raw label in any language still
    resolves to a helpful sentence. An unrecognised trade falls back to
    the ``"other"`` description rather than an empty string.
    """
    key = normalise_trade(trade)
    return _TRADE_DESCRIPTIONS.get(key, _TRADE_DESCRIPTIONS["other"])


# ── Clash status vocabulary (language-neutral codes -> plain labels) ─────────

#: Clash lifecycle status codes, mirroring
#: ``app.modules.clash.models.CLASH_STATUSES``. Kept here as a literal (not
#: imported) so these pure helpers stay database-free and importable without
#: pulling in the clash ORM. If the clash module ever adds a status, add its
#: plain label here too.
OPEN_STATUS_CODES: tuple[str, ...] = ("new", "active", "reviewed")
RESOLVED_STATUS_CODES: tuple[str, ...] = ("approved", "resolved")
IGNORED_STATUS_CODES: tuple[str, ...] = ("ignored",)

#: Plain-language label for every known clash status code. The codes stay
#: language-neutral on the wire; the UI localises them and this table is the
#: honest English fallback for exports and log lines.
_STATUS_LABELS: dict[str, str] = {
    "new": "New, not yet reviewed",
    "active": "Open and being worked on",
    "reviewed": "Reviewed, awaiting resolution",
    "approved": "Approved as resolved",
    "resolved": "Resolved",
    "ignored": "Ignored, will not be fixed",
}


def status_label(status_code: str | None) -> str:
    """Plain-language label for a clash status code.

    An unknown or empty code returns ``"Unknown status"`` rather than
    raising, so a status added by a newer clash module never breaks the
    dashboard.
    """
    if not status_code:
        return "Unknown status"
    return _STATUS_LABELS.get(status_code.strip().lower(), "Unknown status")


def is_open_status(status_code: str | None) -> bool:
    """True when the status code counts as an OPEN (unresolved) clash."""
    if not status_code:
        return False
    return status_code.strip().lower() in OPEN_STATUS_CODES


def is_resolved_status(status_code: str | None) -> bool:
    """True when the status code counts as a RESOLVED clash."""
    if not status_code:
        return False
    return status_code.strip().lower() in RESOLVED_STATUS_CODES


def explain_clash_status(status_code: str | None) -> str:
    """One-line explanation of what a clash status means for coordination.

    Frames the status in terms a coordinator cares about: is this clash
    still on the open queue, cleared, or set aside.
    """
    code = (status_code or "").strip().lower()
    if is_open_status(code):
        return f"'{code}' is an OPEN clash: it still needs a coordination decision."
    if is_resolved_status(code):
        return f"'{code}' is a RESOLVED clash: it has been cleared and is off the open queue."
    if code in IGNORED_STATUS_CODES:
        return f"'{code}' is an IGNORED clash: a deliberate decision not to fix it."
    return "Unknown status: it does not map to open, resolved or ignored."


# ── Counting aggregates (empty-safe) ─────────────────────────────────────────


def counts_by_status(status_codes: Iterable[str | None]) -> dict[str, int]:
    """Count clashes per status code.

    Empty or ``None`` codes are folded into a single ``"unknown"`` bucket
    so the total always equals the number of inputs; the caller never has
    to reconcile a dropped row. An empty input returns an empty dict, not
    an error.
    """
    out: dict[str, int] = {}
    for code in status_codes:
        key = code.strip().lower() if code and code.strip() else "unknown"
        out[key] = out.get(key, 0) + 1
    return out


def counts_by_discipline(labels: Iterable[str | None]) -> dict[str, int]:
    """Count clashes per canonical trade.

    Each raw label is normalised via :func:`normalise_trade` first, so a
    mix of languages collapses onto the six canonical trades. Unrecognised
    labels land on ``"other"`` (never dropped). An empty input returns an
    empty dict.
    """
    out: dict[str, int] = {}
    for label in labels:
        key = normalise_trade(label)
        out[key] = out.get(key, 0) + 1
    return out


def discipline_pair_counts(
    pairs: Iterable[tuple[str | None, str | None]],
) -> dict[tuple[str, str], int]:
    """Aggregate clash counts per canonical discipline pair, symmetrically.

    Each side of a pair is normalised, then the pair is sorted so
    ``(struct, arch)`` and ``(arch, struct)`` collapse to one key
    ``(arch, struct)``. A clash within one discipline (``arch`` vs
    ``arch``) is kept as ``(arch, arch)``. An empty input returns an empty
    dict.
    """
    out: dict[tuple[str, str], int] = {}
    for a, b in pairs:
        left = normalise_trade(a)
        right = normalise_trade(b)
        if left > right:
            left, right = right, left
        key = (left, right)
        out[key] = out.get(key, 0) + 1
    return out


def explain_matrix_cell(row: str | None, col: str | None, count: int) -> str:
    """One-line description of a discipline-pair matrix cell.

    Turns a bare grid cell into a sentence a reader understands: which two
    trades clash and how many open collisions sit between them.
    """
    left = normalise_trade(row)
    right = normalise_trade(col)
    if count < 0:
        raise ValueError(f"count must be zero or positive (got {count})")
    clash_word = "clash" if count == 1 else "clashes"
    if left == right:
        return f"{count} {clash_word} within {left} (same-discipline collisions)."
    return f"{count} {clash_word} between {left} and {right}."


# ── Open-vs-resolved rate (zero-guarded) ─────────────────────────────────────


def resolution_rate(open_count: int, resolved_count: int) -> float:
    """Share of clashes that are resolved: resolved / (open + resolved).

    Returns a value in ``[0.0, 1.0]``. When there are no clashes at all
    the rate is ``0.0`` (a clean, well-defined answer, never a division by
    zero or a ``NaN``). Negative inputs are a caller mistake and raise a
    :class:`ValueError` rather than producing a nonsense rate.

    Args:
        open_count: Number of clashes still open (unresolved).
        resolved_count: Number of clashes resolved.

    Returns:
        The resolved share as a float in ``[0.0, 1.0]``.

    Raises:
        ValueError: If either count is negative.
    """
    if open_count < 0 or resolved_count < 0:
        raise ValueError(f"counts must be zero or positive (open={open_count}, resolved={resolved_count})")
    total = open_count + resolved_count
    if total == 0:
        return 0.0
    return resolved_count / total


def explain_resolution_rate(open_count: int, resolved_count: int) -> str:
    """One-line plain-language read-out of the resolution rate.

    States the resolved share as a rounded percentage and names the counts
    behind it, so the number is self-explaining. An all-empty queue is
    described as such rather than "0 percent resolved", which would read as
    a problem where there is none.
    """
    rate = resolution_rate(open_count, resolved_count)
    total = open_count + resolved_count
    if total == 0:
        return "No clashes recorded yet, so there is no resolution rate to report."
    pct = round(rate * 100)
    return f"{pct}% of clashes are resolved ({resolved_count} resolved of {total} total, {open_count} still open)."


# ── Money aggregation (Decimal-exact, currency-safe) ─────────────────────────


def _coerce_decimal(value: object) -> Decimal:
    """Coerce a value to a finite :class:`Decimal`, or raise ``ValueError``.

    A non-finite input (``NaN`` / ``inf``) is rejected explicitly so it can
    never poison a running total. Anything unparseable is a clean
    ``ValueError`` rather than a silent zero, because a wrong money figure
    is worse than a loud failure.
    """
    if isinstance(value, Decimal):
        dec = value
    else:
        try:
            dec = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError(f"not a valid money amount: {value!r}") from exc
    if not dec.is_finite():
        raise ValueError(f"money amount must be finite (got {value!r})")
    return dec


def sum_amounts(amounts: Iterable[object]) -> Decimal:
    """Sum a series of amounts assumed to share ONE currency, exactly.

    Uses :class:`Decimal` throughout so there is no float drift. An empty
    input sums to ``Decimal("0")``. This helper does not know about
    currency codes; only call it on amounts you already know share one
    currency (use :func:`sum_by_currency` when they might not).

    Raises:
        ValueError: If any amount is non-finite or unparseable.
    """
    total = Decimal("0")
    for amount in amounts:
        total += _coerce_decimal(amount)
    return total


def sum_by_currency(items: Iterable[tuple[object, str | None]]) -> dict[str, Decimal]:
    """Total amounts grouped by currency code, never mixing currencies.

    Each item is an ``(amount, currency_code)`` pair. Summing money across
    two different currencies is meaningless (10 EUR + 10 USD is not 20 of
    anything), so the totals are kept per currency. A missing or empty
    currency code groups under ``""`` so those amounts are not silently
    added to a real currency's total. An empty input returns an empty
    dict.

    Returns:
        ``{currency_code: total}`` with exact :class:`Decimal` totals.

    Raises:
        ValueError: If any amount is non-finite or unparseable.
    """
    out: dict[str, Decimal] = {}
    for amount, currency in items:
        code = (currency or "").strip().upper()
        out[code] = out.get(code, Decimal("0")) + _coerce_decimal(amount)
    return out


def total_in_currency(items: Iterable[tuple[object, str | None]], *, currency: str) -> Decimal:
    """Exact total of the items that carry ``currency``; others are ignored.

    A currency-safe way to get a single headline number: it sums only the
    amounts whose code matches ``currency`` (case-insensitively) and leaves
    every other currency out of the figure rather than blending them. When
    nothing matches the total is ``Decimal("0")``.

    Args:
        items: ``(amount, currency_code)`` pairs.
        currency: The currency code to total. Empty string is rejected so
            the caller cannot accidentally total the "unknown currency"
            bucket as if it were real money.

    Raises:
        ValueError: If ``currency`` is empty, or any matching amount is
            non-finite or unparseable.
    """
    target = (currency or "").strip().upper()
    if not target:
        raise ValueError("currency must be a non-empty code, e.g. 'EUR'")
    by_code = sum_by_currency(items)
    return by_code.get(target, Decimal("0"))


def explain_exposure(total: object, currency: str | None) -> str:
    """One-line plain-language read-out of an aggregate cost exposure.

    "Exposure" here is the summed open cost impact of the coordination
    issues: an estimate of the money at risk if the open clashes are not
    resolved. Names the currency so the figure is never a bare, ambiguous
    number.
    """
    dec = _coerce_decimal(total)
    code = (currency or "").strip().upper()
    unit = code if code else "(no currency set)"
    return (
        f"Open coordination exposure is about {format(dec, 'f')} {unit}: "
        "the estimated money at risk while these clashes stay open."
    )

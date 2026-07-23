# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure change-request clarifier.

Turns a rough free-text change note ("client wants the lobby cladding swapped
to stone, no idea on cost yet") into a structured, well-formed change-request
draft: a classification, the questions still worth asking before the change is
fit to circulate, a likely governing contract clause, and a recommended review
route. This is the deterministic core a co-pilot calls before any model or
human ever sees the draft - it adds no facts, it only reads what the author
wrote and names what is missing.

The logic is intentionally heuristic and rule-driven: keyword maps for
classification, regular expressions for the cost / schedule / clause signals,
and a small clause book keyed by contract standard. There is no model and no
network here, so the same note always yields the same draft and the engine
unit-tests on the local Python 3.11 runner like the cycle-time and SLA engines.

No database, no ORM, no ``app.*`` imports - standard library only. The thin
service / co-pilot layer feeds the note in and persists or presents the draft.

Scope note: signal detection is keyword / pattern based, so it reads a topic
being mentioned, not its polarity. A note that says "no cost yet" still trips
the cost signal because the word "cost" is present; the clarifier deliberately
errs toward "the author is talking about cost" rather than parsing negation.
Confirming the actual figures stays with the author and the commercial review.

International note: the cost signal is currency-agnostic. It fires on generic
value words, on a broad set of international currency names / ISO codes and
symbols, or on a money-shaped figure with either Anglo (``1,200.00``) or
European (``1.200,00``) grouping, so a note written anywhere in the world is
read the same way rather than only one priced in euros, dollars or pounds.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --- Classification --------------------------------------------------------

#: Stable classification tokens for a change note. ``scope_change`` is the
#: default when nothing more specific is detected.
SCOPE_CHANGE = "scope_change"
DESIGN_CHANGE = "design_change"
SITE_CONDITION = "site_condition"
CLIENT_REQUEST = "client_request"
ERROR_OMISSION = "error_omission"

#: Ordered keyword map for classification. The first class whose keywords
#: appear in the note wins, so the more specific causes (an error / omission, a
#: differing site condition) are checked before the broad "client asked for it"
#: and "scope grew" buckets. Each keyword is matched whole-word and
#: case-insensitively.
CLASSIFICATION_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    (
        ERROR_OMISSION,
        (
            "error",
            "omission",
            "omitted",
            "missing",
            "mistake",
            "discrepancy",
            "conflict",
            "clash",
            "incorrect",
            "wrong",
            "defect",
            "rework",
            "coordination error",
        ),
    ),
    (
        SITE_CONDITION,
        (
            "site condition",
            "ground condition",
            "ground conditions",
            "unforeseen",
            "unforeseeable",
            "differing site",
            "rock",
            "groundwater",
            "contamination",
            "contaminated",
            "obstruction",
            "buried",
            "excavation revealed",
            "as-found",
        ),
    ),
    (
        DESIGN_CHANGE,
        (
            "design change",
            "redesign",
            "design development",
            "specification change",
            "spec change",
            "revised drawing",
            "revised drawings",
            "drawing revision",
            "detail change",
            "engineering change",
            "re-detail",
        ),
    ),
    (
        CLIENT_REQUEST,
        (
            "client request",
            "client wants",
            "client asked",
            "client requested",
            "employer request",
            "owner request",
            "owner wants",
            "betterment",
            "upgrade requested",
            "requested by the client",
        ),
    ),
    (
        SCOPE_CHANGE,
        (
            "scope change",
            "additional work",
            "extra work",
            "added scope",
            "out of scope",
            "new requirement",
            "increase in scope",
            "scope creep",
            "extension of works",
        ),
    ),
]

# --- Signal detection ------------------------------------------------------

#: Generic cost / value vocabulary that signals the author is talking about
#: money regardless of the country or currency they work in.
_VALUE_WORDS = (
    "cost",
    "price",
    "priced",
    "amount",
    "quote",
    "quotation",
    "budget",
    "valuation",
    "sum",
    "fee",
    "rate",
)

#: International currency names and ISO codes that count as a cost / value signal
#: on their own. Kept broad so a change note written anywhere in the world trips
#: the cost signal, not only one priced in euros, dollars or pounds. A few tokens
#: that read as ordinary non-money words in construction English are deliberately
#: left out (for example the ISO code for the Canadian dollar collides with the
#: everyday abbreviation for computer-aided design, and the plain-English names of
#: some currencies are common verbs / nouns): those are still recognised by their
#: currency symbol or by a money-shaped figure, just not by an ambiguous word.
_CURRENCY_WORDS = (
    # Majors, by ISO code and common name.
    "eur",
    "euro",
    "euros",
    "usd",
    "dollar",
    "dollars",
    "gbp",
    "pound",
    "pounds",
    "sterling",
    # Other widely used codes and names, chosen for low collision risk with
    # everyday construction wording.
    "chf",
    "franc",
    "francs",
    "zar",
    "aud",
    "jpy",
    "yen",
    "cny",
    "yuan",
    "renminbi",
    "rmb",
    "inr",
    "rupee",
    "rupees",
    "aed",
    "dirham",
    "dirhams",
    "sar",
    "riyal",
    "riyals",
    "ngn",
    "naira",
    "kes",
    "shilling",
    "shillings",
    "krw",
    "pln",
    "zloty",
    "sek",
    "nok",
    "dkk",
    "krona",
    "kronor",
    "krone",
    "peso",
    "pesos",
)

#: Every word that, on its own, signals the author is discussing cost or value.
_COST_SIGNAL_WORDS = _VALUE_WORDS + _CURRENCY_WORDS

#: Whole-word cost vocabulary (generic value words plus international currency
#: names / codes).
_COST_WORD_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in _COST_SIGNAL_WORDS) + r")\b",
    re.IGNORECASE,
)

#: Currency symbols that count as a money signal when attached to a figure.
#: Built from code points so this source file stays pure ASCII. Covers the
#: dollar sign plus the main non-Latin currency symbols, so a figure written in
#: any of them is read as money worldwide, not only in the three Western majors.
#: A symbol on its own (with no figure) is deliberately not treated as a signal.
_CURRENCY_SYMBOLS = (
    "$"
    + chr(0x20AC)  # euro
    + chr(0x00A3)  # pound sterling
    + chr(0x00A5)  # yen / yuan
    + chr(0x20B9)  # Indian rupee
    + chr(0x20A9)  # won
    + chr(0x20BA)  # lira
    + chr(0x20BD)  # ruble
    + chr(0x20A6)  # naira
    + chr(0x20B1)  # peso
)

#: A currency symbol immediately followed by a number, e.g. ``$1,200``. A
#: symbol on its own (no figure) is deliberately not treated as a money signal.
_CURRENCY_SYMBOL_RE = re.compile("[" + re.escape(_CURRENCY_SYMBOLS) + r"]\s?\d")

#: A bare money-shaped figure: a grouped or decimal number optionally followed
#: by a magnitude word (``k`` / ``m``). Kept conservative so a plain duration
#: like "10 days" is not misread as money.
_MONEY_FIGURE_RE = re.compile(
    r"\b\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?\b"  # grouped: 1,200 / 4.500,00
    r"|\b\d+(?:[.,]\d+)?\s?(?:k|m)\b"  # 50k / 1.2m
    r"|\b\d+(?:[.,]\d{2})\b",  # 1200.00 / 12,50
    re.IGNORECASE,
)

#: Schedule / time vocabulary. ``eot`` (extension of time) and ``programme``
#: are first-class signals alongside the obvious duration words.
_SCHEDULE_WORDS = (
    "day",
    "days",
    "week",
    "weeks",
    "month",
    "months",
    "delay",
    "delays",
    "delayed",
    "programme",
    "schedule",
    "timeline",
    "duration",
    "completion date",
    "milestone",
    "critical path",
    "float",
    "eot",
    "extension of time",
    "time impact",
    "prolongation",
)

_SCHEDULE_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in _SCHEDULE_WORDS) + r")\b",
    re.IGNORECASE,
)

#: A contract-clause reference: ``clause 13.3`` / ``cl. 60.1`` / ``section 5``
#: or a named standard followed by a number such as ``FIDIC 13.3`` /
#: ``NEC4 60.1`` / ``JCT 2.27``.
_CLAUSE_RE = re.compile(
    r"\b(?:clause|cl\.?|section|sub-?clause)\s*\d+(?:\.\d+)*"
    r"|\b(?:fidic|nec4|nec3|nec|jct)\s*(?:cl\.?\s*|clause\s*)?\d+(?:\.\d+)*",
    re.IGNORECASE,
)

#: A responsible / accountable party signal: an explicit role word, or the
#: phrasing teams use to assign the ball ("responsible:", "owned by",
#: "assigned to", "action on").
_PARTY_WORDS = (
    "contractor",
    "subcontractor",
    "sub-contractor",
    "client",
    "employer",
    "owner",
    "engineer",
    "architect",
    "consultant",
    "designer",
    "project manager",
    "quantity surveyor",
    "supplier",
    "responsible party",
)

_PARTY_WORD_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in _PARTY_WORDS) + r")\b",
    re.IGNORECASE,
)

#: Explicit assignment phrasing, e.g. "responsible: ACME", "owned by design
#: team", "assigned to the engineer", "action on contractor".
_PARTY_ASSIGN_RE = re.compile(
    r"\b(?:responsible|owned\s+by|assigned\s+to|action\s+on|accountable|ball\s+in\s+court)\b",
    re.IGNORECASE,
)

#: A note shorter than this many words is considered too thin to circulate and
#: earns a "describe it more fully" gap.
_SHORT_NOTE_WORDS = 15

#: Gap severities.
SEVERITY_REQUIRED = "required"
SEVERITY_RECOMMENDED = "recommended"

#: Route tokens (snake_case, vendor-neutral).
ROUTE_TECHNICAL_THEN_COMMERCIAL = "technical_review_then_commercial"
ROUTE_COMMERCIAL_APPROVAL = "commercial_approval"
ROUTE_STANDARD_CHANGE_REVIEW = "standard_change_review"

#: The key pieces that a well-formed change request carries. Completeness is the
#: fraction of these present.
_KEY_PIECES = ("cost", "schedule", "clause", "responsible_party")


@dataclass(frozen=True)
class ClarificationGap:
    """One thing the author still needs to supply before the change is fit to
    circulate.

    ``severity`` is ``"required"`` (the request should not advance without it)
    or ``"recommended"`` (it should be captured but does not block).
    """

    field: str
    question: str
    severity: str


@dataclass(frozen=True)
class ClauseSuggestion:
    """A likely governing contract provision for the change.

    ``standard`` is the contract form (for example ``FIDIC`` / ``NEC4`` /
    ``JCT``), ``clause_ref`` the provision (``13.3``), and ``rationale`` a short
    plain-language reason it applies. Suggestions are advisory: the author
    confirms the real governing clause.
    """

    standard: str
    clause_ref: str
    rationale: str


@dataclass(frozen=True)
class ClarifiedRequest:
    """A structured first draft of a change request built from a rough note."""

    title: str
    normalized_summary: str
    detected_classification: str
    missing: list[ClarificationGap]
    clause_suggestions: list[ClauseSuggestion]
    suggested_route: str
    completeness: float


@dataclass(frozen=True)
class _Signals:
    """Which key pieces the note already carries."""

    cost: bool
    schedule: bool
    clause: bool
    responsible_party: bool
    word_count: int


def _normalize_summary(note: str) -> str:
    """Collapse all runs of whitespace in *note* to single spaces and trim."""
    return re.sub(r"\s+", " ", note).strip()


def _extract_title(note: str) -> str:
    """First non-empty line, trimmed to ~80 chars; fallback when the note is
    empty.
    """
    for raw_line in note.splitlines():
        line = raw_line.strip()
        if line:
            if len(line) > 80:
                line = line[:80].rstrip()
            return line
    return "Untitled change"


def _classify(summary: str) -> str:
    """Detect the classification from the keyword map; default scope change."""
    lowered = summary.lower()
    for classification, keywords in CLASSIFICATION_KEYWORDS:
        for keyword in keywords:
            pattern = r"\b" + re.escape(keyword) + r"\b"
            if re.search(pattern, lowered):
                return classification
    return SCOPE_CHANGE


def _detect_signals(summary: str) -> _Signals:
    """Detect the cost / schedule / clause / responsible-party signals."""
    cost = bool(
        _COST_WORD_RE.search(summary) or _CURRENCY_SYMBOL_RE.search(summary) or _MONEY_FIGURE_RE.search(summary)
    )
    schedule = bool(_SCHEDULE_RE.search(summary))
    clause = bool(_CLAUSE_RE.search(summary))
    responsible_party = bool(_PARTY_WORD_RE.search(summary) or _PARTY_ASSIGN_RE.search(summary))
    word_count = len(summary.split())
    return _Signals(
        cost=cost,
        schedule=schedule,
        clause=clause,
        responsible_party=responsible_party,
        word_count=word_count,
    )


def _build_gaps(signals: _Signals) -> list[ClarificationGap]:
    """Name every missing key piece as a gap, in a stable order."""
    gaps: list[ClarificationGap] = []
    if not signals.cost:
        gaps.append(
            ClarificationGap(
                field="cost_impact",
                question="What is the estimated cost or value impact of this change?",
                severity=SEVERITY_REQUIRED,
            )
        )
    if not signals.schedule:
        gaps.append(
            ClarificationGap(
                field="schedule_impact",
                question="Does this affect the programme - any delay, time impact, or extension of time?",
                severity=SEVERITY_RECOMMENDED,
            )
        )
    if not signals.clause:
        gaps.append(
            ClarificationGap(
                field="contract_clause",
                question="Which contract clause governs this change?",
                severity=SEVERITY_RECOMMENDED,
            )
        )
    if not signals.responsible_party:
        gaps.append(
            ClarificationGap(
                field="responsible_party",
                question="Who is the responsible party - who carries this change and bears the impact?",
                severity=SEVERITY_REQUIRED,
            )
        )
    if signals.word_count < _SHORT_NOTE_WORDS:
        gaps.append(
            ClarificationGap(
                field="description",
                question="Describe the change more fully - what, where, and why is it needed?",
                severity=SEVERITY_RECOMMENDED,
            )
        )
    return gaps


#: Clause book keyed by upper-cased contract standard. Each entry is the base
#: (always-suggested) provision and an optional time-related provision that is
#: only offered when the note carries a schedule signal.
_CLAUSE_BOOK: dict[str, tuple[ClauseSuggestion, ClauseSuggestion | None]] = {
    "FIDIC": (
        ClauseSuggestion("FIDIC", "13.3", "Variation procedure - Engineer instruction and quotation"),
        ClauseSuggestion("FIDIC", "20.1", "Notice of claim time-bar"),
    ),
    "NEC4": (
        ClauseSuggestion("NEC4", "60.1", "Compensation event"),
        ClauseSuggestion("NEC4", "61.3", "Notification time-bar"),
    ),
    "JCT": (
        ClauseSuggestion("JCT", "5.1", "Variation definition"),
        ClauseSuggestion("JCT", "2.27", "Notice of delay"),
    ),
}


def _suggest_clauses(contract_standard: str, has_schedule_signal: bool) -> list[ClauseSuggestion]:
    """Likely governing clauses for *contract_standard*.

    The base provision is always offered; the time-bar / delay provision is
    offered only when a schedule signal is present. An unknown or empty
    standard yields a single generic prompt to record the governing clause.
    """
    key = contract_standard.strip().upper()
    entry = _CLAUSE_BOOK.get(key)
    if entry is None:
        return [
            ClauseSuggestion(
                "",
                "",
                "Record the governing contract clause for this change under your contract form.",
            )
        ]
    base, time_clause = entry
    suggestions = [base]
    if has_schedule_signal and time_clause is not None:
        suggestions.append(time_clause)
    return suggestions


def _suggest_route(classification: str, has_cost_signal: bool) -> str:
    """Recommend a review route from the classification and cost signal.

    An error / omission or a change with no cost stated goes for technical
    review before any commercial step; a change that already carries a cost
    figure goes straight to commercial approval; everything else takes the
    standard change review.
    """
    if classification == ERROR_OMISSION or not has_cost_signal:
        return ROUTE_TECHNICAL_THEN_COMMERCIAL
    if has_cost_signal:
        return ROUTE_COMMERCIAL_APPROVAL
    return ROUTE_STANDARD_CHANGE_REVIEW


def _completeness(signals: _Signals) -> float:
    """Fraction of the key pieces present, rounded to 2 dp."""
    present = sum(
        (
            signals.cost,
            signals.schedule,
            signals.clause,
            signals.responsible_party,
        )
    )
    return round(present / len(_KEY_PIECES), 2)


def analyze_change_note(note: str, *, contract_standard: str = "") -> ClarifiedRequest:
    """Build a structured change-request draft from a rough free-text *note*.

    Deterministic and side-effect free: it classifies the note, flags the key
    pieces still missing, suggests likely governing contract clauses for the
    given *contract_standard*, recommends a review route, and scores how
    complete the note already is. It never invents cost, schedule, or
    attribution facts - it only reads what the author wrote.
    """
    summary = _normalize_summary(note)
    title = _extract_title(note)
    classification = _classify(summary)
    signals = _detect_signals(summary)
    return ClarifiedRequest(
        title=title,
        normalized_summary=summary,
        detected_classification=classification,
        missing=_build_gaps(signals),
        clause_suggestions=_suggest_clauses(contract_standard, signals.schedule),
        suggested_route=_suggest_route(classification, signals.cost),
        completeness=_completeness(signals),
    )


__all__ = [
    "CLASSIFICATION_KEYWORDS",
    "CLIENT_REQUEST",
    "DESIGN_CHANGE",
    "ERROR_OMISSION",
    "ROUTE_COMMERCIAL_APPROVAL",
    "ROUTE_STANDARD_CHANGE_REVIEW",
    "ROUTE_TECHNICAL_THEN_COMMERCIAL",
    "SCOPE_CHANGE",
    "SEVERITY_RECOMMENDED",
    "SEVERITY_REQUIRED",
    "SITE_CONDITION",
    "ClarificationGap",
    "ClarifiedRequest",
    "ClauseSuggestion",
    "analyze_change_note",
]

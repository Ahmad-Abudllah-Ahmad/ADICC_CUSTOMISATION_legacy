# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""International, explainable text matcher for cost-database lookup.

This module is the pure, database-free core of cost matching. It compares a
free-text BoQ item or CAD element description against candidate cost-database
entries and returns a confidence score plus a plain-language explanation of
why that score was reached.

Why it exists
-------------
Construction descriptions arrive in many languages and unit systems. A wall
labelled "Stahlbetonwand" (de), "mur en beton arme" (fr), "muro de hormigon
armado" (es) or "железобетонная стена" (ru) should all match the same
"reinforced concrete wall" cost item. This matcher folds accents, normalises
units across metric and imperial, and maps a curated multilingual synonym set
onto shared concept tokens so the comparison happens on meaning, not spelling.

How the confidence score is computed
------------------------------------
The score is a value in ``[0.0, 1.0]`` built from three transparent factors,
all returned in :class:`MatchScore.factors` so a user can audit any result:

1. ``query_coverage`` - fraction of the query's concept tokens that also
   appear in the candidate. This is the dominant factor: a candidate that
   covers every word the user typed is a strong match.
2. ``term_overlap`` - overlap coefficient ``|Q and C| / min(|Q|, |C|)``,
   which rewards candidates that are focused on the same terms rather than
   long catch-all descriptions.
3. ``unit_factor`` - a multiplier. Compatible units (same physical
   dimension, e.g. m2 and square feet are both area) leave the score
   untouched; a hard unit mismatch (area vs volume) multiplies the score
   down so it can never masquerade as a confident match.

    base       = 0.65 * query_coverage + 0.35 * term_overlap
    confidence = round(base * unit_factor, 4)

A normalised exact-string equality short-circuits to ``1.0`` before any of
the above. Scores at or above :data:`HIGH_CONFIDENCE` are treated as
confident; between :data:`REVIEW_CONFIDENCE` and that as needs-review; below
it as no confident match, in which case a short hint tells the user what to
try next.

Everything here is deterministic and free of I/O, so it is trivially unit
testable and safe to run on any input, including regex metacharacters.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.modules.cost_match.messages import DEFAULT_LOCALE, translate

# ── Confidence bands ────────────────────────────────────────────────────────

HIGH_CONFIDENCE = 0.75
"""At or above this score a match is shown as confident (green)."""

REVIEW_CONFIDENCE = 0.45
"""Between this and :data:`HIGH_CONFIDENCE` a match is flagged needs-review."""

_UNIT_MISMATCH_PENALTY = 0.55
"""Multiplier applied when query and candidate units differ in dimension."""

_COVERAGE_WEIGHT = 0.65
_OVERLAP_WEIGHT = 0.35


# ── Accent folding and normalisation ────────────────────────────────────────

# Characters that do not decompose under NFKD but have a well-known Latin
# fold. Kept explicit so German, Scandinavian and Slavic-Latin spellings all
# collapse to a shared form before comparison.
_FOLD_MAP = {
    "ß": "ss",
    "ẞ": "ss",
    "ø": "o",
    "Ø": "o",
    "đ": "d",
    "Đ": "d",
    "ł": "l",
    "Ł": "l",
    "æ": "ae",
    "Æ": "ae",
    "œ": "oe",
    "Œ": "oe",
    "þ": "th",
    "ð": "d",
}

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def fold_accents(text: str) -> str:
    """Strip diacritics and fold special letters to a plain-Latin base.

    ``"béton"`` becomes ``"beton"``, ``"Dämmung"`` becomes ``"dammung"`` and
    ``"straße"`` becomes ``"strasse"``. Non-Latin scripts (for example
    Cyrillic) are left intact so their own synonym forms still match.
    """
    if not text:
        return ""
    out = []
    for ch in text:
        if ch in _FOLD_MAP:
            out.append(_FOLD_MAP[ch])
            continue
        decomposed = unicodedata.normalize("NFKD", ch)
        stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
        out.append(stripped or ch)
    return "".join(out)


def normalize_text(text: str | None) -> str:
    """Lower-case, fold accents and collapse whitespace to a canonical form.

    Punctuation and regex metacharacters are treated as plain separators, so
    input such as ``"C30/37 [*+]"`` is handled safely and never compiled as a
    pattern.
    """
    if not text:
        return ""
    folded = fold_accents(text).lower()
    tokens = _TOKEN_RE.findall(folded)
    return " ".join(tokens)


# ── Multilingual synonym index ──────────────────────────────────────────────

# Concept -> surface forms in en/de/fr/es/it/pt/ru (and common variants).
# Surface forms are normalised at build time, so accents and case here are
# only for readability. Add a language by appending its word to the concept.
_CONCEPT_SYNONYMS: dict[str, tuple[str, ...]] = {
    "concrete": ("concrete", "beton", "hormigon", "calcestruzzo", "betao", "betong", "бетон"),
    "reinforcement": (
        "reinforcement",
        "reinforced",
        "rebar",
        "bewehrung",
        "bewehrt",
        "armierung",
        "armatura",
        "armato",
        "armata",
        "armadura",
        "armado",
        "armada",
        "ferraillage",
        "armature",
        "arme",
        "армированный",
        "арматура",
        "refuerzo",
    ),
    "formwork": (
        "formwork",
        "shuttering",
        "schalung",
        "coffrage",
        "encofrado",
        "cassaforma",
        "casseforme",
        "cofragem",
        "опалубка",
    ),
    "masonry": (
        "masonry",
        "brickwork",
        "brick",
        "mauerwerk",
        "ziegel",
        "maconnerie",
        "ladrillo",
        "mattone",
        "muratura",
        "alvenaria",
        "кирпич",
        "кладка",
    ),
    "plaster": (
        "plaster",
        "plastering",
        "render",
        "putz",
        "enduit",
        "revoco",
        "enlucido",
        "intonaco",
        "reboco",
        "штукатурка",
    ),
    "insulation": (
        "insulation",
        "dammung",
        "isolation",
        "aislamiento",
        "isolamento",
        "isolante",
        "coibentazione",
        "isolamento",
        "утеплитель",
        "изоляция",
    ),
    "painting": (
        "paint",
        "painting",
        "anstrich",
        "malerarbeiten",
        "peinture",
        "pintura",
        "pittura",
        "verniciatura",
        "покраска",
        "окраска",
        "краска",
    ),
    "screed": ("screed", "estrich", "chape", "solera", "massetto", "стяжка"),
    "excavation": (
        "excavation",
        "earthwork",
        "aushub",
        "erdarbeiten",
        "terrassement",
        "excavacion",
        "scavo",
        "escavacao",
        "выемка",
        "земляные",
    ),
    "waterproofing": (
        "waterproofing",
        "abdichtung",
        "etancheite",
        "impermeabilizacion",
        "impermeabilizzazione",
        "impermeabilizacao",
        "гидроизоляция",
    ),
    "tiling": (
        "tiling",
        "tile",
        "tiles",
        "fliesen",
        "carrelage",
        "alicatado",
        "baldosa",
        "piastrelle",
        "azulejo",
        "плитка",
    ),
    "steel": ("steel", "stahl", "acier", "acero", "acciaio", "aco", "сталь"),
    "timber": ("timber", "wood", "holz", "bois", "madera", "legno", "madeira", "дерево", "древесина"),
    "door": ("door", "tur", "porte", "puerta", "porta", "дверь"),
    "window": ("window", "fenster", "fenetre", "ventana", "finestra", "janela", "окно"),
    "roof": ("roof", "roofing", "dach", "toiture", "cubierta", "tejado", "tetto", "copertura", "кровля", "крыша"),
    "drywall": ("drywall", "plasterboard", "gipskarton", "trockenbau", "cartongesso", "гипсокартон"),
    "pipe": ("pipe", "piping", "rohr", "tuyau", "tuberia", "tubo", "tubazione", "труба"),
    "cable": ("cable", "wiring", "kabel", "cavo", "кабель", "проводка"),
    "sand": ("sand", "sable", "arena", "sabbia", "areia", "песок"),
    "aggregate": ("gravel", "aggregate", "kies", "gravier", "grava", "ghiaia", "гравий", "щебень"),
    "cement": ("cement", "zement", "ciment", "cemento", "цемент"),
    "wall": ("wall", "wand", "mur", "pared", "muro", "parete", "parede", "стена"),
    "slab": ("slab", "floor", "boden", "decke", "platte", "dalle", "losa", "solaio", "soletta", "плита", "перекрытие"),
    "waterstop": ("waterstop", "fugenband", "гидрошпонка"),
    "membrane": ("membrane", "membran", "membrana", "мембрана"),
    "glazing": ("glazing", "glass", "glas", "verre", "vidrio", "vetro", "стекло"),
}

# Multilingual stopwords stripped before scoring so grammar glue words do not
# dilute the token overlap. Kept intentionally small and language-spanning.
_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "of",
        "and",
        "or",
        "for",
        "with",
        "in",
        "on",
        "to",
        "per",
        "der",
        "die",
        "das",
        "und",
        "mit",
        "aus",
        "fur",
        "von",
        "im",
        "le",
        "la",
        "les",
        "de",
        "du",
        "des",
        "et",
        "avec",
        "pour",
        "en",
        "el",
        "los",
        "las",
        "y",
        "con",
        "para",
        "il",
        "lo",
        "gli",
        "e",
        "di",
        "da",
        "o",
        "os",
        "as",
        "com",
        "и",
        "с",
        "из",
        "для",
        "на",
    }
)

# Reverse index: normalised surface form -> concept token. Built once.
_SYNONYM_INDEX: dict[str, str] = {}
for _concept, _forms in _CONCEPT_SYNONYMS.items():
    _SYNONYM_INDEX[_concept] = _concept
    for _form in _forms:
        _SYNONYM_INDEX[normalize_text(_form)] = _concept
del _concept, _forms, _form  # keep module namespace clean

# Surface forms long enough to be safely recognised inside a compound word
# (>= 4 chars), used only for closed compounds like German "Stahlbetonwand"
# where several concepts are glued into one token with no separator.
_COMPOUND_FORMS: tuple[tuple[str, str], ...] = tuple(
    (form, concept) for form, concept in _SYNONYM_INDEX.items() if len(form) >= 4
)

# Only tokens at least this long are scanned for glued concepts, so ordinary
# short words never trip a spurious substring hit.
_COMPOUND_MIN_LEN = 8


def _decompose_compound(token: str) -> list[str]:
    """Return concept tokens glued inside a long compound, or ``[]``.

    German (and Cyrillic) closed compounds such as ``"stahlbetonwand"`` or
    ``"железобетонная"`` carry several concepts in one token. We scan the
    curated multi-character surface forms and return every concept that
    appears as a substring, so the compound still matches its parts.
    """
    if len(token) < _COMPOUND_MIN_LEN:
        return []
    found: dict[str, None] = {}
    for form, concept in _COMPOUND_FORMS:
        if form in token:
            found.setdefault(concept, None)
    return list(found)


def canonical_tokens(text: str | None) -> tuple[str, ...]:
    """Return meaning-bearing tokens for ``text`` in a language-neutral form.

    Each word is folded, lower-cased, mapped through the multilingual synonym
    index to a shared concept when known, and stopwords are dropped. Long
    closed compounds are split into their concept parts. The result is
    order-preserving and de-duplicated so scoring is stable.
    """
    seen: dict[str, None] = {}
    for token in normalize_text(text).split():
        if token in _STOPWORDS:
            continue
        canonical = _SYNONYM_INDEX.get(token)
        if canonical is not None:
            seen.setdefault(canonical, None)
            continue
        parts = _decompose_compound(token)
        if parts:
            for part in parts:
                seen.setdefault(part, None)
        else:
            seen.setdefault(token, None)
    return tuple(seen)


# ── Unit normalisation (metric + imperial) ──────────────────────────────────

# Normalised unit surface form -> physical dimension. Anything not listed is
# treated as unknown, which is neutral for scoring (never a false penalty).
_UNIT_DIMENSION: dict[str, str] = {
    # length
    "mm": "length",
    "cm": "length",
    "dm": "length",
    "m": "length",
    "km": "length",
    "lm": "length",
    "lfm": "length",
    "rm": "length",
    "in": "length",
    "inch": "length",
    "ft": "length",
    "foot": "length",
    "feet": "length",
    "yd": "length",
    "yard": "length",
    "mi": "length",
    "mile": "length",
    # area
    "m2": "area",
    "sqm": "area",
    "qm": "area",
    "quadratmeter": "area",
    "ha": "area",
    "are": "area",
    "sf": "area",
    "sqft": "area",
    "ft2": "area",
    "yd2": "area",
    "sqyd": "area",
    # volume
    "m3": "volume",
    "cbm": "volume",
    "kubikmeter": "volume",
    "cum": "volume",
    "cf": "volume",
    "cuft": "volume",
    "ft3": "volume",
    "yd3": "volume",
    "cuyd": "volume",
    "l": "volume",
    "liter": "volume",
    "litre": "volume",
    "gal": "volume",
    "gallon": "volume",
    # mass
    "kg": "mass",
    "g": "mass",
    "mg": "mass",
    "t": "mass",
    "to": "mass",
    "ton": "mass",
    "tonne": "mass",
    "lb": "mass",
    "lbs": "mass",
    "pound": "mass",
    "oz": "mass",
    "cwt": "mass",
    # count
    "pcs": "count",
    "pc": "count",
    "pce": "count",
    "piece": "count",
    "stk": "count",
    "stuck": "count",
    "st": "count",
    "ea": "count",
    "each": "count",
    "nr": "count",
    "no": "count",
    "un": "count",
    "u": "count",
    "pz": "count",
    "stuk": "count",
    "шт": "count",
    # time / labour
    "h": "time",
    "hr": "time",
    "hour": "time",
    "std": "time",
    "stunde": "time",
    "day": "time",
    "tag": "time",
    "jour": "time",
    # lump sum
    "ls": "sum",
    "lumpsum": "sum",
    "psch": "sum",
    "pauschal": "sum",
    "forfait": "sum",
    "global": "sum",
}


def normalize_unit(unit: str | None) -> str | None:
    """Return the physical dimension of a unit, or ``None`` if unknown.

    Superscripts and separators are folded so ``"m²"``, ``"m2"``, ``"sq m"``
    and ``"SQM"`` all resolve to ``"area"``, and imperial units land on the
    same dimension as their metric counterparts.
    """
    if not unit:
        return None
    folded = fold_accents(unit).lower().replace("²", "2").replace("³", "3")
    key = re.sub(r"[\s.\-/]", "", folded)
    return _UNIT_DIMENSION.get(key)


def units_compatible(a: str | None, b: str | None) -> bool | None:
    """Compare two units by dimension.

    Returns ``True`` if both map to the same dimension, ``False`` if they map
    to different dimensions, and ``None`` when either unit is unknown so the
    caller can treat it as no-signal rather than a mismatch.
    """
    dim_a = normalize_unit(a)
    dim_b = normalize_unit(b)
    if dim_a is None or dim_b is None:
        return None
    return dim_a == dim_b


# ── Data carriers ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Candidate:
    """A single cost-database entry to score against a query.

    ``payload`` carries opaque pass-through data (for example a Decimal
    unit rate and currency) that the matcher never mutates or coerces, so
    money stays Decimal-exact end to end.
    """

    ref: str
    text: str
    unit: str | None = None
    payload: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class MatchScore:
    """The confidence of one query-candidate comparison, fully explained."""

    confidence: float
    band: str  # "high" | "medium" | "low"
    factors: dict[str, float]
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MatchResult:
    """Outcome of matching a query against a set of candidates."""

    query: str
    candidate: Candidate | None
    score: MatchScore | None
    is_confident: bool
    tie: bool
    hint: str | None
    alternatives: list[tuple[Candidate, MatchScore]] = field(default_factory=list)


def _band(confidence: float) -> str:
    """Map a raw confidence to a traffic-light band."""
    if confidence >= HIGH_CONFIDENCE:
        return "high"
    if confidence >= REVIEW_CONFIDENCE:
        return "medium"
    return "low"


def score_match(
    query: str,
    candidate_text: str,
    *,
    query_unit: str | None = None,
    candidate_unit: str | None = None,
) -> MatchScore:
    """Score how well ``candidate_text`` answers ``query`` in ``[0, 1]``.

    The returned :class:`MatchScore` exposes every factor and a list of
    reason codes so the number is auditable. See the module docstring for
    the exact formula.
    """
    q_tokens = canonical_tokens(query)
    c_tokens = canonical_tokens(candidate_text)
    factors: dict[str, float] = {
        "query_coverage": 0.0,
        "term_overlap": 0.0,
        "unit_factor": 1.0,
        "exact": 0.0,
    }
    reasons: list[str] = []

    # Unit relationship first: it can only reduce a score, never inflate it.
    compat = units_compatible(query_unit, candidate_unit)
    if compat is True:
        reasons.append("unit_match")
    elif compat is False:
        factors["unit_factor"] = _UNIT_MISMATCH_PENALTY
        reasons.append("unit_mismatch")
    elif query_unit or candidate_unit:
        reasons.append("unit_unknown")

    if not q_tokens or not c_tokens:
        reasons.append("weak_overlap")
        return MatchScore(confidence=0.0, band="low", factors=factors, reasons=reasons)

    # Normalised exact equality short-circuits to a perfect content score.
    if normalize_text(query) == normalize_text(candidate_text):
        factors["exact"] = 1.0
        factors["query_coverage"] = 1.0
        factors["term_overlap"] = 1.0
        confidence = round(1.0 * factors["unit_factor"], 4)
        reasons.insert(0, "exact_match")
        return MatchScore(confidence=confidence, band=_band(confidence), factors=factors, reasons=reasons)

    q_set = set(q_tokens)
    c_set = set(c_tokens)
    inter = len(q_set & c_set)
    coverage = inter / len(q_set)
    overlap = inter / min(len(q_set), len(c_set))
    factors["query_coverage"] = round(coverage, 4)
    factors["term_overlap"] = round(overlap, 4)

    base = _COVERAGE_WEIGHT * coverage + _OVERLAP_WEIGHT * overlap
    confidence = round(base * factors["unit_factor"], 4)

    if coverage >= 0.99:
        reasons.insert(0, "strong_overlap")
    elif inter > 0:
        reasons.insert(0, "partial_overlap")
    else:
        reasons.insert(0, "weak_overlap")

    return MatchScore(confidence=confidence, band=_band(confidence), factors=factors, reasons=reasons)


def explain(score: MatchScore, locale: str = DEFAULT_LOCALE) -> str:
    """Render a match's reason codes as a localized, human-readable sentence."""
    parts = [translate(f"match.reason.{code}", locale=locale) for code in score.reasons]
    return " ".join(parts)


def no_match_hint(reason: str, locale: str = DEFAULT_LOCALE) -> str:
    """Return a short, plain-language hint for a non-result.

    ``reason`` is one of ``"empty_query"``, ``"no_candidates"`` or
    ``"no_good_match"``.
    """
    return translate(f"match.hint.{reason}", locale=locale)


def best_match(
    query: str | None,
    candidates: Iterable[Candidate] | Sequence[Candidate],
    *,
    query_unit: str | None = None,
    locale: str = DEFAULT_LOCALE,
    top_n: int = 3,
) -> MatchResult:
    """Find the best cost-database candidate for ``query``, with guards.

    Handles the awkward cases explicitly so callers never have to: an empty
    or whitespace-only query and an empty candidate set both return a result
    with ``candidate=None`` and a plain-language ``hint``. Ties on the top
    score are resolved by input order and flagged via ``tie=True``. When the
    best score is below :data:`REVIEW_CONFIDENCE` the candidate is still
    offered as ``candidate`` for context but ``is_confident`` is ``False`` and
    a hint suggests what to try next.
    """
    normalized_query = (query or "").strip()
    if not normalized_query or not canonical_tokens(normalized_query):
        return MatchResult(
            query=normalized_query,
            candidate=None,
            score=None,
            is_confident=False,
            tie=False,
            hint=no_match_hint("empty_query", locale=locale),
        )

    scored: list[tuple[Candidate, MatchScore]] = []
    for cand in candidates:
        score = score_match(
            normalized_query,
            cand.text,
            query_unit=query_unit,
            candidate_unit=cand.unit,
        )
        scored.append((cand, score))

    if not scored:
        return MatchResult(
            query=normalized_query,
            candidate=None,
            score=None,
            is_confident=False,
            tie=False,
            hint=no_match_hint("no_candidates", locale=locale),
        )

    # Stable sort: highest confidence first, input order breaks ties.
    ordered = sorted(
        enumerate(scored),
        key=lambda pair: (-pair[1][1].confidence, pair[0]),
    )
    top_index, (best_cand, best_score) = ordered[0]
    tie = len(ordered) > 1 and ordered[1][1][1].confidence == best_score.confidence

    alternatives = [(cand, score) for _, (cand, score) in ordered[:top_n]]
    is_confident = best_score.confidence >= HIGH_CONFIDENCE
    hint = None
    if best_score.confidence < REVIEW_CONFIDENCE:
        hint = no_match_hint("no_good_match", locale=locale)

    return MatchResult(
        query=normalized_query,
        candidate=best_cand,
        score=best_score,
        is_confident=is_confident,
        tie=tie,
        hint=hint,
        alternatives=alternatives,
    )


def suggestion_rate(candidate: Candidate) -> Decimal | None:
    """Extract the candidate's unit rate as an exact Decimal, if present.

    Reads ``payload["unit_rate"]`` without float coercion so currency values
    stay Decimal-exact. Strings are parsed through Decimal; anything missing
    or unparseable yields ``None`` rather than a lossy fallback.
    """
    if not candidate.payload:
        return None
    raw = candidate.payload.get("unit_rate")
    if raw is None:
        return None
    if isinstance(raw, Decimal):
        return raw
    if isinstance(raw, int):
        return Decimal(raw)
    if isinstance(raw, str):
        try:
            return Decimal(raw)
        except (ValueError, ArithmeticError):
            return None
    return None


__all__ = [
    "HIGH_CONFIDENCE",
    "REVIEW_CONFIDENCE",
    "Candidate",
    "MatchResult",
    "MatchScore",
    "best_match",
    "canonical_tokens",
    "explain",
    "fold_accents",
    "no_match_hint",
    "normalize_text",
    "normalize_unit",
    "score_match",
    "suggestion_rate",
    "units_compatible",
]

# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure multi-source change-request intake normalizer.

Change requests arrive in many foreign shapes - a row pulled from a tracker
spreadsheet ("Change No", "Estimated $", "Time (days)"), an email intake form
("Subject", "Cost Impact", "Raised By"), a partner portal export. Each names the
same handful of facts differently, prices money as a formatted string with a
currency symbol, and states a schedule slip in whatever unit the author felt
like typing. This engine takes one such foreign record plus a mapping profile
that describes its dialect and turns it into a canonical
:class:`NormalizedChangeDraft` the change / variation modules can act on.

The normalisation is deterministic and forgiving. Field names are matched
case-insensitively and whitespace-tolerantly against the profile's alias table;
money strings are parsed to :class:`decimal.Decimal` with thousands separators
and currency symbols / codes stripped (and the currency recorded when one is
detected); schedule values are coerced through a unit-synonym table to a plain
day count; categorical values are run through a value-synonym table. Nothing in
a foreign record is ever dropped silently: a field with no alias is recorded in
``unmapped_fields``, a required canonical field left empty lands in
``missing_required``, and anything that could not be parsed adds a warning
rather than raising. ``completeness`` is the fraction of the profile's required
fields that ended up present and parseable, mirroring the completeness signal the
:mod:`~app.modules.change_intelligence.clarifier` exposes.

No database, no ORM, no ``app.*`` imports - standard library only (Decimal for
money) - so it unit-tests on the local Python 3.11 runner like the other pure
engines. A thin service layer (written separately) loads the stored mapping
profile, feeds the foreign record in, and either previews or persists the draft.

Scope note: money / currency detection is lexical, not semantic. It reads the
symbols and codes present in the text, so a field that mixes two currency codes
records the first one detected and warns; it does not attempt FX or validate
that the recorded currency is the project currency. Confirming the real figures
stays with the author and the commercial review, exactly as in the clarifier.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

# --- Canonical fields ------------------------------------------------------

#: The canonical change-request fields this engine targets. ``title`` and
#: ``description`` are free text; ``cost_impact`` / ``currency`` are money;
#: ``schedule_impact_days`` is a day count; ``requested_by`` / ``source_ref``
#: are attribution. Any canonical key a profile does not map simply stays unset
#: on the draft (or, if required, is reported in ``missing_required``).
FIELD_TITLE = "title"
FIELD_DESCRIPTION = "description"
FIELD_COST_IMPACT = "cost_impact"
FIELD_CURRENCY = "currency"
FIELD_SCHEDULE_IMPACT_DAYS = "schedule_impact_days"
FIELD_REQUESTED_BY = "requested_by"
FIELD_SOURCE_REF = "source_ref"

#: Every canonical field, in a stable order. Used to validate alias targets and
#: to decide which mapped values land on typed draft slots vs. ``extra``.
CANONICAL_FIELDS: tuple[str, ...] = (
    FIELD_TITLE,
    FIELD_DESCRIPTION,
    FIELD_COST_IMPACT,
    FIELD_CURRENCY,
    FIELD_SCHEDULE_IMPACT_DAYS,
    FIELD_REQUESTED_BY,
    FIELD_SOURCE_REF,
)

#: Canonical fields whose value is money and is parsed to ``Decimal``.
_MONEY_FIELDS: frozenset[str] = frozenset({FIELD_COST_IMPACT})

#: Canonical fields whose value is a duration and is coerced to a day count.
_DURATION_FIELDS: frozenset[str] = frozenset({FIELD_SCHEDULE_IMPACT_DAYS})

# --- Money parsing ---------------------------------------------------------

#: Two-decimal-place quantum for money rounding (matches the cost engines'
#: ``TWOPLACES``). Parsed money is quantized to two places half-up-free here -
#: we keep the parsed precision and let the money engines quantize on use - but
#: the constant is exposed for callers that want it.
TWOPLACES = Decimal("0.01")

#: Currency symbols recognised when attached to a money string. Built from code
#: points so this source file stays pure ASCII: ``$`` (dollar), U+20AC (euro),
#: U+00A3 (pound), U+00A5 (yen), U+20B9 (rupee).
_CURRENCY_SYMBOLS: dict[str, str] = {
    "$": "USD",
    chr(0x20AC): "EUR",
    chr(0x00A3): "GBP",
    chr(0x00A5): "JPY",
    chr(0x20B9): "INR",
}

#: Three-letter ISO currency codes recognised when present as a whole word in a
#: money string (for example ``1,200 EUR`` or ``USD 4,500``). Kept to the codes
#: the platform's packs use plus the common majors.
_CURRENCY_CODES: tuple[str, ...] = (
    "USD",
    "EUR",
    "GBP",
    "CHF",
    "ZAR",
    "AUD",
    "CAD",
    "JPY",
    "INR",
    "AED",
    "SAR",
    "NGN",
    "KES",
)

_CURRENCY_CODE_RE = re.compile(
    r"\b(?:" + "|".join(_CURRENCY_CODES) + r")\b",
    re.IGNORECASE,
)

#: The characters that make up the numeric body of a money string once symbols
#: and codes are gone: digits, separators, sign, and surrounding space.
_MONEY_BODY_RE = re.compile(r"[0-9.,()+\-\s]+")

#: A leading minus, or a fully parenthesised body, denotes a negative amount
#: (accounting style ``(1,200.00)``).
_PARENS_RE = re.compile(r"^\s*\((.*)\)\s*$")


def _detect_currency(text: str) -> str | None:
    """Return the currency code implied by *text*, or ``None``.

    A whole-word ISO code wins over a symbol so an explicit ``... EUR`` is
    honoured even if a stray ``$`` appears; otherwise the first recognised
    symbol decides. Detection is first-match and deterministic.
    """
    code_match = _CURRENCY_CODE_RE.search(text)
    if code_match is not None:
        return code_match.group(0).upper()
    for symbol, code in _CURRENCY_SYMBOLS.items():
        if symbol in text:
            return code
    return None


def _strip_currency_tokens(text: str) -> str:
    """Remove currency symbols and ISO codes from *text*."""
    out = text
    for symbol in _CURRENCY_SYMBOLS:
        out = out.replace(symbol, " ")
    out = _CURRENCY_CODE_RE.sub(" ", out)
    return out


def _normalise_decimal_separators(body: str) -> str:
    """Turn a grouped numeric *body* into a plain ``[-]int[.frac]`` string.

    Handles both Anglo (``1,234.56`` - comma groups, dot decimal) and European
    (``1.234,56`` - dot groups, comma decimal) conventions by treating whichever
    of ``.`` / ``,`` appears LAST as the decimal separator and the other as a
    group separator. A single separator with exactly three trailing digits is
    read as a thousands group (``1,200`` -> ``1200``); otherwise a lone
    separator is the decimal point (``12,50`` -> ``12.50``, ``1200.5`` ->
    ``1200.5``). Spaces (a common group separator) are dropped.
    """
    cleaned = body.replace(" ", "")
    has_dot = "." in cleaned
    has_comma = "," in cleaned
    if has_dot and has_comma:
        # The rightmost of the two is the decimal separator.
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
        return cleaned
    if has_comma:
        # Lone comma: a group separator when it lays out a recognised grouping
        # of the integer - either Anglo (1,234,567: a 1-3 digit lead then 3-digit
        # groups) or South-Asian (1,00,000: a 1-2 digit lead, 2-digit groups,
        # then a final 3-digit group). Otherwise it is the decimal point
        # (12,50 -> 12.50). A single comma with a trailing group that is not 3
        # digits (12,5 / 1,23) reads as a decimal, which is the common European
        # short form.
        anglo = re.fullmatch(r"-?\d{1,3}(?:,\d{3})+", cleaned)
        south_asian = re.fullmatch(r"-?\d{1,2}(?:,\d{2})+,\d{3}", cleaned)
        if anglo or south_asian:
            return cleaned.replace(",", "")
        return cleaned.replace(",", ".")
    if has_dot:
        # Lone dot: group separator only when it looks like 1.234.567 grouping;
        # a single trailing 3-digit group (1.234) is ambiguous, so treat a dot
        # as the decimal point unless there are multiple dot groups.
        if re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+", cleaned) and cleaned.count(".") > 1:
            return cleaned.replace(".", "")
        return cleaned
    return cleaned


def parse_money(raw: str) -> tuple[Decimal | None, str | None, str | None]:
    """Parse a money *raw* string to ``(amount, currency, warning)``.

    Strips currency symbols and ISO codes (recording the currency when one is
    detected), removes thousands separators, honours a leading minus and the
    accounting ``(1,200.00)`` negative form, and returns the amount as a
    :class:`Decimal`. Never raises: an unparseable body yields
    ``(None, currency_or_None, warning)`` so the caller can record the problem
    and carry on. An empty / whitespace input yields ``(None, None, None)`` -
    absence is not an error here, missing-required handles it.
    """
    if raw is None:
        return None, None, None
    text = str(raw).strip()
    if not text:
        return None, None, None

    currency = _detect_currency(text)
    body = _strip_currency_tokens(text)

    negative = False
    paren = _PARENS_RE.match(body)
    if paren is not None:
        negative = True
        body = paren.group(1)

    # Keep only the numeric body; if stray letters remain the field was not money.
    body = body.strip()
    if not _MONEY_BODY_RE.fullmatch(body) if body else True:
        return None, currency, f"could not parse money from {text!r}"

    if body.count("-") > 1 or ("-" in body and not body.lstrip().startswith("-")):
        return None, currency, f"could not parse money from {text!r}"
    if body.startswith("-"):
        negative = True
        body = body[1:]

    normalised = _normalise_decimal_separators(body)
    if normalised in ("", ".", "-"):
        return None, currency, f"could not parse money from {text!r}"

    try:
        amount = Decimal(normalised)
    except InvalidOperation:
        return None, currency, f"could not parse money from {text!r}"

    if negative:
        amount = -amount
    return amount, currency, None


# --- Schedule / duration parsing -------------------------------------------

#: How many days one of each recognised duration unit is worth. The engine
#: coerces a schedule value to a plain day count by multiplying the parsed
#: figure by this factor. A "working day" is counted as one calendar day here;
#: the working-vs-calendar distinction belongs to the scheduling engine's
#: calendars, not to lexical intake.
_UNIT_DAY_FACTORS: dict[str, Decimal] = {
    "day": Decimal("1"),
    "days": Decimal("1"),
    "d": Decimal("1"),
    "working day": Decimal("1"),
    "working days": Decimal("1"),
    "business day": Decimal("1"),
    "business days": Decimal("1"),
    "calendar day": Decimal("1"),
    "calendar days": Decimal("1"),
    "wd": Decimal("1"),
    "week": Decimal("7"),
    "weeks": Decimal("7"),
    "wk": Decimal("7"),
    "wks": Decimal("7"),
    "w": Decimal("7"),
    "month": Decimal("30"),
    "months": Decimal("30"),
    "mo": Decimal("30"),
    "mon": Decimal("30"),
}

#: A duration string: an optional sign, a number, and an optional trailing unit
#: word. The unit (group 2) is looked up in :data:`_UNIT_DAY_FACTORS`.
_DURATION_RE = re.compile(
    r"^\s*([+-]?\d+(?:[.,]\d+)?)\s*([a-zA-Z][a-zA-Z .]*)?\s*$",
)


def parse_duration_days(
    raw: str,
    unit_synonyms: dict[str, str] | None = None,
) -> tuple[Decimal | None, str | None]:
    """Parse a schedule *raw* string to ``(days, warning)``.

    Accepts a bare number (read as days), or a number with a trailing unit word
    that is first mapped through the profile's *unit_synonyms* and then through
    the built-in :data:`_UNIT_DAY_FACTORS` (so ``"3 wks"`` or a profile that
    aliases ``"sprint" -> "weeks"`` both resolve). The decimal comma is accepted
    (``"1,5 days"``). Never raises: an unrecognised unit or a non-numeric body
    yields ``(None, warning)``. Empty input yields ``(None, None)``.
    """
    if raw is None:
        return None, None
    text = str(raw).strip()
    if not text:
        return None, None

    match = _DURATION_RE.match(text)
    if match is None:
        return None, f"could not parse schedule impact from {text!r}"

    number_part = match.group(1).replace(",", ".")
    unit_part = (match.group(2) or "").strip().lower()
    # Collapse internal whitespace in the unit so "working  days" matches.
    unit_part = re.sub(r"\s+", " ", unit_part)

    try:
        figure = Decimal(number_part)
    except InvalidOperation:
        return None, f"could not parse schedule impact from {text!r}"

    if not unit_part:
        # No unit -> already a day count.
        return figure, None

    synonyms = unit_synonyms or {}
    mapped_unit = synonyms.get(unit_part, unit_part)
    mapped_unit = re.sub(r"\s+", " ", mapped_unit.strip().lower())

    factor = _UNIT_DAY_FACTORS.get(mapped_unit)
    if factor is None:
        return None, f"unrecognised schedule unit {unit_part!r} in {text!r}"
    return figure * factor, None


# --- Mapping profile -------------------------------------------------------


def _alias_key(name: str) -> str:
    """Normalise a foreign field name for case-/whitespace-insensitive lookup.

    Lower-cases, collapses internal whitespace to a single space, and strips a
    handful of cosmetic punctuation (``:``, ``*``, surrounding quotes) that
    intake forms tend to append to labels. Deterministic and idempotent.
    """
    cleaned = (name or "").strip().lower()
    cleaned = cleaned.strip("\"'")
    cleaned = re.sub(r"[:*]+$", "", cleaned).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


@dataclass(frozen=True)
class IntakeMapping:
    """A dialect description for one foreign change-request source.

    ``field_aliases`` maps a foreign field name to a canonical field (one of
    :data:`CANONICAL_FIELDS`); keys are matched case-insensitively and
    whitespace-tolerantly. ``unit_synonyms`` maps a foreign duration unit word
    to a built-in unit (for example ``"sprint" -> "weeks"``). ``value_synonyms``
    maps a foreign categorical value to a normalised one (for example a status
    ``"in review" -> "under_review"``); it is applied to every mapped non-money,
    non-duration value. ``required_fields`` is the subset of canonical fields a
    record from this source must carry for the draft to be considered complete.

    The mapping is a plain value object - no I/O - so a service layer can build
    it from a stored row and feed it straight in.
    """

    profile_name: str
    field_aliases: dict[str, str]
    unit_synonyms: dict[str, str]
    value_synonyms: dict[str, str]
    required_fields: tuple[str, ...]

    def canonical_for(self, foreign_name: str) -> str | None:
        """Return the canonical field a *foreign_name* maps to, or ``None``.

        Lookup is case-insensitive and whitespace-tolerant via
        :func:`_alias_key`; the alias table is normalised the same way so a
        profile authored with ``"Change Title"`` matches an incoming
        ``"change  title"``.
        """
        target = _normalised_aliases(self.field_aliases).get(_alias_key(foreign_name))
        return target

    def value_synonym(self, value: str) -> str:
        """Normalise a categorical *value* via :data:`value_synonyms`.

        Matching is case-insensitive and whitespace-tolerant; the original
        casing of an unmapped value is preserved.
        """
        return _normalised_value_synonyms(self.value_synonyms).get(_alias_key(value), value)


def _normalised_aliases(aliases: dict[str, str]) -> dict[str, str]:
    """Return *aliases* re-keyed through :func:`_alias_key`.

    Computed on demand (the mapping is frozen and may be built from arbitrary
    input) so authors can write natural labels. On a key collision after
    normalisation the first-written wins, which keeps the result deterministic
    for a given insertion order.
    """
    out: dict[str, str] = {}
    for foreign, canonical in aliases.items():
        key = _alias_key(foreign)
        if key not in out:
            out[key] = canonical
    return out


def _normalised_value_synonyms(synonyms: dict[str, str]) -> dict[str, str]:
    """Return *synonyms* re-keyed through :func:`_alias_key` (first wins)."""
    out: dict[str, str] = {}
    for foreign, normalised in synonyms.items():
        key = _alias_key(foreign)
        if key not in out:
            out[key] = normalised
    return out


# --- Result types ----------------------------------------------------------


@dataclass(frozen=True)
class NormalizedChangeDraft:
    """A canonical change-request draft built from a foreign record.

    ``cost_impact`` is a :class:`Decimal` (or ``None`` if absent / unparseable)
    and ``currency`` the ISO code detected alongside it (or ``None``).
    ``schedule_impact_days`` is a plain day count as a :class:`Decimal`. The
    free-text and attribution slots are strings or ``None``. ``extra`` holds any
    mapped canonical value that is not one of the typed slots - it is reserved
    for forward-compatibility and is normally empty, since every canonical field
    has a typed slot today.
    """

    title: str | None = None
    description: str | None = None
    cost_impact: Decimal | None = None
    currency: str | None = None
    schedule_impact_days: Decimal | None = None
    requested_by: str | None = None
    source_ref: str | None = None
    extra: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class NormalizationResult:
    """The outcome of normalising one foreign record.

    ``draft`` is the canonical draft. ``unmapped_fields`` lists the foreign
    field names that had no alias (sorted, so the report is stable).
    ``missing_required`` lists the required canonical fields that ended up empty
    or unparseable (in :data:`CANONICAL_FIELDS` order). ``warnings`` collects
    every non-fatal problem (a money / duration string that would not parse, a
    duplicate currency, and so on) in encounter order. ``completeness`` is the
    fraction of required fields that are present and parseable, in ``[0, 1]``,
    rounded to two places - mirroring the clarifier's completeness signal.
    """

    draft: NormalizedChangeDraft
    unmapped_fields: tuple[str, ...]
    missing_required: tuple[str, ...]
    warnings: tuple[str, ...]
    completeness: float


# --- Normalisation core ----------------------------------------------------


def _coerce_text(value: object) -> str | None:
    """Trim a free-text *value* to a string, or ``None`` if blank."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _present_and_parseable(draft: NormalizedChangeDraft, canonical: str) -> bool:
    """Whether *canonical* ended up with a usable value on *draft*.

    Money / duration fields count only when they parsed to a non-``None``
    Decimal; text fields count when non-empty. ``currency`` counts when set.
    """
    value = getattr(draft, canonical, None)
    return value is not None


def normalize(raw: dict, mapping: IntakeMapping) -> NormalizationResult:
    """Normalise a foreign change-request record *raw* using *mapping*.

    Walks the foreign record, routing each field through the profile's alias
    table to a canonical slot; parses money to :class:`Decimal` (recording the
    detected currency), coerces schedule values to a day count via the profile's
    unit synonyms, and runs categorical values through the profile's value
    synonyms. Foreign fields with no alias are collected into ``unmapped_fields``
    and required canonical fields left empty into ``missing_required``;
    completeness is the fraction of required fields present and parseable.

    Deterministic and side-effect free, and it never raises on bad data - a
    value it cannot parse becomes a warning and a ``None`` slot. An empty record
    yields an empty draft with every required field reported missing.
    """
    title: str | None = None
    description: str | None = None
    cost_impact: Decimal | None = None
    currency: str | None = None
    schedule_impact_days: Decimal | None = None
    requested_by: str | None = None
    source_ref: str | None = None
    extra: dict[str, object] = {}

    unmapped: list[str] = []
    warnings: list[str] = []

    # A mapping may legitimately target the same canonical field from two foreign
    # columns; the first non-empty value wins and the second adds a warning so the
    # collision is visible rather than silently overwriting.
    seen_canonical: set[str] = set()

    for foreign_name, foreign_value in _iter_record(raw):
        canonical = mapping.canonical_for(foreign_name)
        if canonical is None:
            unmapped.append(str(foreign_name))
            continue
        if canonical not in CANONICAL_FIELDS:
            # An alias pointing at an unknown canonical name is a profile bug;
            # keep the value in extra and warn rather than dropping it.
            extra[canonical] = foreign_value
            warnings.append(f"alias for {foreign_name!r} targets unknown canonical field {canonical!r}")
            continue

        if canonical in _MONEY_FIELDS:
            amount, detected_currency, warn = parse_money(_as_str(foreign_value))
            if warn:
                warnings.append(warn)
            if canonical in seen_canonical and amount is not None and cost_impact is not None:
                warnings.append(f"duplicate value for {canonical!r}; keeping the first")
            elif amount is not None:
                cost_impact = amount
                seen_canonical.add(canonical)
            if detected_currency is not None:
                if currency is None:
                    currency = detected_currency
                elif currency != detected_currency:
                    warnings.append(f"conflicting currency {detected_currency!r} ignored; keeping {currency!r}")
            continue

        if canonical in _DURATION_FIELDS:
            days, warn = parse_duration_days(_as_str(foreign_value), mapping.unit_synonyms)
            if warn:
                warnings.append(warn)
            if canonical in seen_canonical and days is not None and schedule_impact_days is not None:
                warnings.append(f"duplicate value for {canonical!r}; keeping the first")
            elif days is not None:
                schedule_impact_days = days
                seen_canonical.add(canonical)
            continue

        if canonical == FIELD_CURRENCY:
            text = _coerce_text(foreign_value)
            explicit = _detect_currency(text) if text else None
            resolved = explicit or (text.upper() if text else None)
            if resolved is not None and currency is None:
                currency = resolved
                seen_canonical.add(canonical)
            elif resolved is not None and currency is not None and currency != resolved:
                warnings.append(f"conflicting currency {resolved!r} ignored; keeping {currency!r}")
            continue

        # Free-text / attribution field: trim, normalise via value synonyms.
        text = _coerce_text(foreign_value)
        if text is None:
            continue
        normalised_value = mapping.value_synonym(text)
        if canonical in seen_canonical:
            warnings.append(f"duplicate value for {canonical!r}; keeping the first")
            continue
        seen_canonical.add(canonical)
        if canonical == FIELD_TITLE:
            title = normalised_value
        elif canonical == FIELD_DESCRIPTION:
            description = normalised_value
        elif canonical == FIELD_REQUESTED_BY:
            requested_by = normalised_value
        elif canonical == FIELD_SOURCE_REF:
            source_ref = normalised_value

    draft = NormalizedChangeDraft(
        title=title,
        description=description,
        cost_impact=cost_impact,
        currency=currency,
        schedule_impact_days=schedule_impact_days,
        requested_by=requested_by,
        source_ref=source_ref,
        extra=extra,
    )

    missing_required = tuple(
        f for f in CANONICAL_FIELDS if f in mapping.required_fields and not _present_and_parseable(draft, f)
    )
    completeness = _completeness(draft, mapping.required_fields)

    return NormalizationResult(
        draft=draft,
        unmapped_fields=tuple(sorted(unmapped)),
        missing_required=missing_required,
        warnings=tuple(warnings),
        completeness=completeness,
    )


def _completeness(draft: NormalizedChangeDraft, required_fields: tuple[str, ...]) -> float:
    """Fraction of *required_fields* present and parseable on *draft*, 2 dp.

    With no required fields the record is trivially complete (1.0), matching the
    intuition that a profile that demands nothing is always satisfied.
    """
    wanted = tuple(f for f in CANONICAL_FIELDS if f in required_fields)
    if not wanted:
        return 1.0
    present = sum(1 for f in wanted if _present_and_parseable(draft, f))
    return round(present / len(wanted), 2)


def _iter_record(raw: dict) -> list[tuple[object, object]]:
    """Return *raw*'s items as a list, tolerating a non-dict input.

    A ``None`` or non-mapping *raw* yields an empty list so the engine degrades
    to "everything required is missing" rather than raising on garbage input.
    """
    if not isinstance(raw, dict):
        return []
    return list(raw.items())


def _as_str(value: object) -> str:
    """Render a foreign value as text for the lexical parsers.

    A real number is rendered without scientific notation so a spreadsheet cell
    that arrives as a float (``1200.0``) parses the same as the string
    ``"1200.0"``. Everything else falls back to ``str``.
    """
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (int, float)):
        return format(Decimal(str(value)), "f")
    return str(value)


# --- Built-in profiles -----------------------------------------------------

#: A generic tracker-spreadsheet profile: the column names a change log exported
#: from a spreadsheet tends to carry. Money sits in a column with a currency
#: symbol baked into the cell; schedule is a day count column.
SPREADSHEET_PROFILE = IntakeMapping(
    profile_name="generic_spreadsheet",
    field_aliases={
        "change title": FIELD_TITLE,
        "title": FIELD_TITLE,
        "summary": FIELD_TITLE,
        "change description": FIELD_DESCRIPTION,
        "description": FIELD_DESCRIPTION,
        "details": FIELD_DESCRIPTION,
        "notes": FIELD_DESCRIPTION,
        "cost impact": FIELD_COST_IMPACT,
        "estimated cost": FIELD_COST_IMPACT,
        "cost": FIELD_COST_IMPACT,
        "amount": FIELD_COST_IMPACT,
        "value": FIELD_COST_IMPACT,
        "currency": FIELD_CURRENCY,
        "ccy": FIELD_CURRENCY,
        "schedule impact": FIELD_SCHEDULE_IMPACT_DAYS,
        "schedule impact (days)": FIELD_SCHEDULE_IMPACT_DAYS,
        "time impact": FIELD_SCHEDULE_IMPACT_DAYS,
        "delay (days)": FIELD_SCHEDULE_IMPACT_DAYS,
        "days": FIELD_SCHEDULE_IMPACT_DAYS,
        "raised by": FIELD_REQUESTED_BY,
        "requested by": FIELD_REQUESTED_BY,
        "originator": FIELD_REQUESTED_BY,
        "owner": FIELD_REQUESTED_BY,
        "change no": FIELD_SOURCE_REF,
        "change number": FIELD_SOURCE_REF,
        "ref": FIELD_SOURCE_REF,
        "reference": FIELD_SOURCE_REF,
        "id": FIELD_SOURCE_REF,
    },
    unit_synonyms={
        "day(s)": "days",
        "wd": "working days",
        "cd": "calendar days",
    },
    value_synonyms={},
    required_fields=(FIELD_TITLE, FIELD_COST_IMPACT),
)

#: A generic email-intake-form profile: the labels an emailed change form or a
#: ticketing system tends to use. Cost and currency arrive in separate fields,
#: and schedule slip is phrased with a unit word ("Time Impact: 2 weeks").
EMAIL_FORM_PROFILE = IntakeMapping(
    profile_name="generic_email_form",
    field_aliases={
        "subject": FIELD_TITLE,
        "title": FIELD_TITLE,
        "change request": FIELD_TITLE,
        "body": FIELD_DESCRIPTION,
        "message": FIELD_DESCRIPTION,
        "description": FIELD_DESCRIPTION,
        "what is changing": FIELD_DESCRIPTION,
        "cost impact": FIELD_COST_IMPACT,
        "estimated value": FIELD_COST_IMPACT,
        "price": FIELD_COST_IMPACT,
        "currency": FIELD_CURRENCY,
        "time impact": FIELD_SCHEDULE_IMPACT_DAYS,
        "schedule impact": FIELD_SCHEDULE_IMPACT_DAYS,
        "delay": FIELD_SCHEDULE_IMPACT_DAYS,
        "raised by": FIELD_REQUESTED_BY,
        "from": FIELD_REQUESTED_BY,
        "submitted by": FIELD_REQUESTED_BY,
        "requested by": FIELD_REQUESTED_BY,
        "ticket": FIELD_SOURCE_REF,
        "ticket id": FIELD_SOURCE_REF,
        "case": FIELD_SOURCE_REF,
        "reference": FIELD_SOURCE_REF,
    },
    unit_synonyms={
        "wks": "weeks",
        "wk": "weeks",
        "mo": "months",
        "mos": "months",
    },
    value_synonyms={},
    required_fields=(FIELD_TITLE, FIELD_DESCRIPTION, FIELD_COST_IMPACT),
)

#: The built-in profiles, keyed by profile name, for a service layer that wants
#: to offer them as presets.
BUILTIN_PROFILES: dict[str, IntakeMapping] = {
    SPREADSHEET_PROFILE.profile_name: SPREADSHEET_PROFILE,
    EMAIL_FORM_PROFILE.profile_name: EMAIL_FORM_PROFILE,
}


__all__ = [
    "BUILTIN_PROFILES",
    "CANONICAL_FIELDS",
    "EMAIL_FORM_PROFILE",
    "FIELD_COST_IMPACT",
    "FIELD_CURRENCY",
    "FIELD_DESCRIPTION",
    "FIELD_REQUESTED_BY",
    "FIELD_SCHEDULE_IMPACT_DAYS",
    "FIELD_SOURCE_REF",
    "FIELD_TITLE",
    "SPREADSHEET_PROFILE",
    "TWOPLACES",
    "IntakeMapping",
    "NormalizationResult",
    "NormalizedChangeDraft",
    "normalize",
    "parse_duration_days",
    "parse_money",
]

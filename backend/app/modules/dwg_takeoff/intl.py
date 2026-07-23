# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""International, database-free helpers for DWG/DXF quantity takeoff.

Everything in this file is a pure function: no session, no I/O, no module
state that a request can mutate. That keeps the takeoff arithmetic easy to
reason about, easy to unit-test without a database, and safe to reuse from
the service layer, an export, or a future report.

Why this file exists
    A drawing can be measured by anyone, anywhere. One estimator works in
    millimetres, another in feet and inches, a third in square yards. If we
    stored whatever unit each person typed, two takeoffs of the same wall
    would never add up and a BOQ rollup would silently mix feet with metres.
    So on the way in we accept metric and imperial length, area, volume and
    count, and we store and compare everything in one canonical metric form:
    metres (``m``), square metres (``m2``), cubic metres (``m3``) and pieces
    (``pcs``). The stored and exported number is always canonical.

    All conversion factors are exact :class:`~decimal.Decimal` values. The
    imperial base (one inch is exactly 0.0254 m) has an exact finite decimal
    expansion, so every factor here is exact and there is no float drift: a
    measurement converted to canonical and back lands on the same number.

    Nothing here can raise a 500, produce a ``NaN`` / ``inf``, or return a
    silently wrong number. A bad input is either a clean :class:`ValueError`
    (unknown unit, negative measurement, zero or negative scale, mixing two
    physical dimensions in one sum) or a well-defined zero (an empty list, a
    zero measurement).

Vocabulary
    A takeoff has four physical dimensions, matching the sibling takeoff and
    BOQ modules: ``length``, ``area``, ``volume`` and ``count``. Each has one
    canonical metric unit (``m``, ``m2``, ``m3``, ``pcs``). A "measured
    quantity" is the number read off the drawing. A "scale" is how many real
    units one drawing unit represents. "Count vs measure" is the split
    between things you tally one by one (doors, sockets) and things you
    measure with a ruler (a wall length, a slab area). The two modules stay
    decoupled (no import between them) but share the same canonical spellings
    so behaviour is consistent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

# ── Canonical vocabulary ────────────────────────────────────────────────────

#: The four physical dimensions a takeoff can produce. A measured value is
#: only comparable to, or summable with, another value of the SAME dimension.
LENGTH = "length"
AREA = "area"
VOLUME = "volume"
COUNT = "count"

DIMENSIONS: tuple[str, ...] = (LENGTH, AREA, VOLUME, COUNT)

#: The single canonical metric unit each dimension is stored and compared in.
#: Everything on the way in is converted to one of these before storage.
CANONICAL_UNIT: dict[str, str] = {
    LENGTH: "m",
    AREA: "m2",
    VOLUME: "m3",
    COUNT: "pcs",
}


# ── Unit table: folded alias -> (dimension, exact factor to canonical) ──────
#
# The factor multiplies the source value to reach the canonical metric unit
# of that dimension (metres, square metres, cubic metres, pieces). Every
# factor is an exact Decimal: the imperial base inch = 0.0254 m is exact, so
# all derived imperial factors (ft = 0.3048, ft2 = 0.09290304, ft3 =
# 0.028316846592, and so on) terminate exactly in decimal. No float appears
# anywhere in this table, so no rounding creeps in on conversion.
_UNIT_SPEC: dict[str, tuple[str, Decimal]] = {
    # ── Length -> metres ────────────────────────────────────────────────
    "mm": (LENGTH, Decimal("0.001")),
    "cm": (LENGTH, Decimal("0.01")),
    "dm": (LENGTH, Decimal("0.1")),
    "m": (LENGTH, Decimal("1")),
    "km": (LENGTH, Decimal("1000")),
    "in": (LENGTH, Decimal("0.0254")),
    "ft": (LENGTH, Decimal("0.3048")),
    "yd": (LENGTH, Decimal("0.9144")),
    "mi": (LENGTH, Decimal("1609.344")),
    # ── Area -> square metres ───────────────────────────────────────────
    "mm2": (AREA, Decimal("0.000001")),
    "cm2": (AREA, Decimal("0.0001")),
    "dm2": (AREA, Decimal("0.01")),
    "m2": (AREA, Decimal("1")),
    "km2": (AREA, Decimal("1000000")),
    "ha": (AREA, Decimal("10000")),
    "in2": (AREA, Decimal("0.00064516")),
    "ft2": (AREA, Decimal("0.09290304")),
    "yd2": (AREA, Decimal("0.83612736")),
    "ac": (AREA, Decimal("4046.8564224")),
    # ── Volume -> cubic metres ──────────────────────────────────────────
    "mm3": (VOLUME, Decimal("0.000000001")),
    "cm3": (VOLUME, Decimal("0.000001")),
    "dm3": (VOLUME, Decimal("0.001")),
    "l": (VOLUME, Decimal("0.001")),
    "m3": (VOLUME, Decimal("1")),
    "in3": (VOLUME, Decimal("0.000016387064")),
    "ft3": (VOLUME, Decimal("0.028316846592")),
    "yd3": (VOLUME, Decimal("0.764554857984")),
    "gal": (VOLUME, Decimal("0.003785411784")),
    # ── Count -> pieces ─────────────────────────────────────────────────
    "pcs": (COUNT, Decimal("1")),
}


#: Free-text unit spellings folded onto a key of :data:`_UNIT_SPEC`. Drawings
#: label units in whatever the author typed, so "sqm", "sq ft", "lin m",
#: "cu yd" and "nos" all have to resolve. Keys are folded to the same shape
#: :func:`_fold` produces (lower case, no spaces or dots, superscripts and
#: ``^2`` folded to a trailing digit).
_UNIT_ALIASES: dict[str, str] = {
    # Length
    "meter": "m",
    "metre": "m",
    "meters": "m",
    "metres": "m",
    "lm": "m",
    "ml": "m",
    "rm": "m",
    "rmt": "m",
    "runningmetre": "m",
    "runningmeter": "m",
    "linm": "m",
    "linearmetre": "m",
    "linearmeter": "m",
    "millimeter": "mm",
    "millimetre": "mm",
    "centimeter": "cm",
    "centimetre": "cm",
    "kilometer": "km",
    "kilometre": "km",
    "inch": "in",
    "inches": "in",
    '"': "in",
    "foot": "ft",
    "feet": "ft",
    "'": "ft",
    "lf": "ft",
    "linft": "ft",
    "linearfoot": "ft",
    "linearfeet": "ft",
    "yard": "yd",
    "yards": "yd",
    "mile": "mi",
    "miles": "mi",
    # Area
    "sqm": "m2",
    "squaremetre": "m2",
    "squaremeter": "m2",
    "sqmm": "mm2",
    "sqcm": "cm2",
    "sqkm": "km2",
    "hectare": "ha",
    "sqft": "ft2",
    "sf": "ft2",
    "squarefoot": "ft2",
    "squarefeet": "ft2",
    "sqin": "in2",
    "squareinch": "in2",
    "sqyd": "yd2",
    "sy": "yd2",
    "squareyard": "yd2",
    "acre": "ac",
    "acres": "ac",
    # Volume
    "cum": "m3",
    "cbm": "m3",
    "cubicmetre": "m3",
    "cubicmeter": "m3",
    "cuft": "ft3",
    "cf": "ft3",
    "cubicfoot": "ft3",
    "cubicfeet": "ft3",
    "cuyd": "yd3",
    "cy": "yd3",
    "cubicyard": "yd3",
    "cuin": "in3",
    "cubicinch": "in3",
    "liter": "l",
    "litre": "l",
    "liters": "l",
    "litres": "l",
    "ltr": "l",
    "gallon": "gal",
    "gallons": "gal",
    # Count
    "pc": "pcs",
    "pce": "pcs",
    "piece": "pcs",
    "pieces": "pcs",
    "ea": "pcs",
    "each": "pcs",
    "no": "pcs",
    "nos": "pcs",
    "nr": "pcs",
    "number": "pcs",
    "item": "pcs",
    "items": "pcs",
    "stk": "pcs",
    "stuck": "pcs",
}


#: Takeoff measurement-type codes (the annotation ``type`` a user draws with)
#: to the physical dimension they produce. The geometric type is the
#: authoritative dimension of a value; the typed unit is only a fallback.
_MEASUREMENT_TYPE_DIMENSION: dict[str, str] = {
    "distance": LENGTH,
    "line": LENGTH,
    "polyline": LENGTH,
    "arc": LENGTH,
    "perimeter": LENGTH,
    "area": AREA,
    "rectangle": AREA,
    "circle": AREA,
    "polygon": AREA,
    "volume": VOLUME,
    "count": COUNT,
}


#: Plain-language label for each measurement-type code, so a report or the UI
#: can explain what a code means without a lookup table of its own.
_MEASUREMENT_TYPE_LABEL: dict[str, str] = {
    "distance": "measured distance (length)",
    "line": "measured line length (length)",
    "polyline": "measured path length (length)",
    "arc": "measured arc length (length)",
    "perimeter": "measured perimeter (length)",
    "area": "measured area",
    "rectangle": "measured rectangular area",
    "circle": "measured circular area",
    "polygon": "measured polygon area",
    "volume": "measured volume",
    "count": "counted items",
    "text_pin": "text note (no measurement)",
    "arrow": "arrow marker (no measurement)",
}


# ── Folding ─────────────────────────────────────────────────────────────────


def _fold(value: str) -> str:
    """Reduce an arbitrary unit spelling to a lookup key.

    Lower-cases, drops surrounding and internal whitespace and dots, and
    folds the superscript and caret forms of squared / cubed onto a plain
    trailing digit so ``m2``, ``m2`` written with a superscript and ``m^2``
    all collapse to ``m2``. Returns an empty string for a blank input.
    """
    text = value.strip().lower()
    # Superscript digits and caret/star exponent notation -> plain digit.
    text = text.replace("²", "2").replace("³", "3")
    text = text.replace("^2", "2").replace("^3", "3")
    text = text.replace("**2", "2").replace("**3", "3")
    # Remove spaces and dots; keep the ' and " length symbols intact.
    return text.replace(" ", "").replace(".", "")


def _resolve_unit_key(unit: str | None) -> str | None:
    """Fold a unit spelling and resolve it to a :data:`_UNIT_SPEC` key.

    Returns the canonical spec key (for example ``ft2``) or ``None`` when the
    spelling is blank or not recognised. Never raises.
    """
    if not unit:
        return None
    folded = _fold(unit)
    if not folded:
        return None
    if folded in _UNIT_SPEC:
        return folded
    return _UNIT_ALIASES.get(folded)


# ── Coercion ────────────────────────────────────────────────────────────────


def _to_decimal(value: object) -> Decimal:
    """Coerce a number / Decimal / numeric string to an exact ``Decimal``.

    Floats are routed through ``repr`` so a value like ``0.1`` keeps its
    intended decimal form instead of the binary-float tail. Raises
    :class:`ValueError` for ``None``, a non-finite value (``NaN`` / ``inf``),
    or anything that will not parse - so a bad number can never propagate as
    a silent zero or blow up later as a 500.
    """
    if value is None:
        raise ValueError("A measurement value is required (got None).")
    try:
        dec = value if isinstance(value, Decimal) else Decimal(repr(value) if isinstance(value, float) else str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"Not a valid number: {value!r}.") from exc
    if not dec.is_finite():
        raise ValueError(f"Measurement value must be finite, got {value!r}.")
    return dec


# ── Public classification helpers ───────────────────────────────────────────


def classify_unit(unit: str | None) -> str | None:
    """Return the physical dimension of a unit, or ``None`` when unknown.

    Accepts metric and imperial spellings in any case, with or without
    spaces, and with superscript or caret exponents. A count unit (``pcs``,
    ``nos``, ``ea`` and friends) classifies as :data:`COUNT`. This is a pure
    classifier: an unrecognised unit returns ``None`` rather than raising, so
    a caller can decide whether to treat a custom unit as an error or pass it
    through untouched.
    """
    key = _resolve_unit_key(unit)
    if key is None:
        return None
    return _UNIT_SPEC[key][0]


def canonical_unit_for(dimension: str) -> str:
    """Return the canonical metric unit for a dimension.

    Raises :class:`ValueError` for an unknown dimension so a typo cannot
    silently pick the wrong storage unit.
    """
    try:
        return CANONICAL_UNIT[dimension]
    except KeyError as exc:
        raise ValueError(
            f"Unknown dimension {dimension!r}; expected one of {', '.join(DIMENSIONS)}.",
        ) from exc


def measurement_type_dimension(measurement_type: str | None) -> str | None:
    """Dimension implied by a takeoff measurement-type code, or ``None``.

    The geometric type a user drew with (``distance``, ``area``, ``count``
    and so on) is the authoritative dimension of the value. Returns ``None``
    for a marker type that carries no measurement (``text_pin``, ``arrow``)
    or an unknown code, so the caller can fall back to the unit.
    """
    if not measurement_type:
        return None
    return _MEASUREMENT_TYPE_DIMENSION.get(measurement_type.strip().lower())


def describe_measurement_type(measurement_type: str | None) -> str:
    """One-line plain-language label for a measurement-type code.

    Falls back to a readable form of the raw code so an unknown or future
    type still reads sensibly instead of showing a blank.
    """
    if not measurement_type:
        return "unspecified measurement"
    key = measurement_type.strip().lower()
    label = _MEASUREMENT_TYPE_LABEL.get(key)
    if label is not None:
        return label
    return key.replace("_", " ")


# ── Converted-quantity value objects ────────────────────────────────────────


@dataclass(frozen=True)
class ConvertedQuantity:
    """A measurement converted to its canonical metric form.

    Carries both the result and every component used to derive it, so the
    conversion is fully explainable and re-checkable: ``value`` is
    ``source_value * factor`` expressed in ``unit`` (the canonical metric
    unit of ``dimension``). ``derivation`` is a one-line human string. The
    value stored / exported downstream is always ``value`` (canonical).
    """

    value: Decimal
    unit: str
    dimension: str
    source_value: Decimal
    source_unit: str
    factor: Decimal
    derivation: str


@dataclass(frozen=True)
class SummedQuantity:
    """The total of several same-dimension quantities, in canonical units.

    ``components`` keeps each converted part so the total can be explained
    and audited. An empty input yields a well-defined zero with ``dimension``
    and ``unit`` set to ``None`` (there is nothing to take a dimension from).
    """

    total: Decimal
    dimension: str | None
    unit: str | None
    components: list[ConvertedQuantity] = field(default_factory=list)
    derivation: str = ""


def convert_to_canonical(value: object, unit: str | None) -> ConvertedQuantity:
    """Convert a measured ``value`` in ``unit`` to canonical metric.

    Accepts metric or imperial length, area, volume or count. The result is
    expressed in the canonical unit of the unit's dimension (``m``, ``m2``,
    ``m3`` or ``pcs``) using an exact Decimal factor, so no float drift can
    occur.

    Edge cases are surfaced cleanly, never as a 500 or a silent wrong number:

    * an unknown or blank unit raises :class:`ValueError`;
    * a negative measurement raises :class:`ValueError` (a physical takeoff
      quantity is never negative);
    * a non-finite or unparseable value raises :class:`ValueError`;
    * a zero measurement is allowed and converts to a well-defined zero.
    """
    key = _resolve_unit_key(unit)
    if key is None:
        raise ValueError(
            f"Unknown unit {unit!r}. Use a metric or imperial length, area, "
            "volume or count unit (for example m, mm, ft, m2, sqft, m3, cuyd, pcs).",
        )
    dimension, factor = _UNIT_SPEC[key]
    source = _to_decimal(value)
    if source < 0:
        raise ValueError(f"A measured quantity cannot be negative, got {source}.")

    canonical_unit = CANONICAL_UNIT[dimension]
    result = source * factor
    derivation = f"{source} {key} = {source} x {factor} = {result} {canonical_unit} ({dimension})"
    return ConvertedQuantity(
        value=result,
        unit=canonical_unit,
        dimension=dimension,
        source_value=source,
        source_unit=key,
        factor=factor,
        derivation=derivation,
    )


def apply_scale(raw_value: object, scale_factor: object) -> Decimal:
    """Scale a raw drawing measurement to real-world units.

    A drawing carries measurements in its own drawing units; the scale factor
    is how many real units one drawing unit represents, supplied explicitly
    by the caller (never guessed here). The real measurement is
    ``raw_value * scale_factor``.

    * a zero or negative scale factor raises :class:`ValueError` (a scale is
      a strictly positive ratio; zero would collapse every measurement and is
      the classic division-by-zero trap);
    * a negative raw value raises :class:`ValueError`;
    * a zero raw value scales to a well-defined zero.

    Returns an exact ``Decimal`` so the scaled value can feed
    :func:`convert_to_canonical` without float drift.
    """
    raw = _to_decimal(raw_value)
    scale = _to_decimal(scale_factor)
    if scale <= 0:
        raise ValueError(
            f"Scale factor must be greater than zero, got {scale}. A zero or "
            "negative scale cannot map drawing units to real units.",
        )
    if raw < 0:
        raise ValueError(f"A raw measurement cannot be negative, got {raw}.")
    return raw * scale


def sum_quantities(items: object) -> SummedQuantity:
    """Sum an iterable of ``(value, unit)`` pairs in canonical metric units.

    Every part is converted to canonical form first, then added. All parts
    must share one physical dimension: adding a length to an area is
    physically meaningless, so a mixed-dimension input raises
    :class:`ValueError` rather than returning a misleading number. An empty
    input returns a well-defined zero (total ``0``, no dimension). Each part
    is kept in ``components`` so the total stays explainable.
    """
    try:
        pairs = list(items)  # type: ignore[call-overload]
    except TypeError as exc:
        raise ValueError("sum_quantities expects an iterable of (value, unit) pairs.") from exc

    components: list[ConvertedQuantity] = []
    dimension: str | None = None
    total = Decimal("0")

    for pair in pairs:
        try:
            value, unit = pair
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Each item must be a (value, unit) pair, got {pair!r}.") from exc
        converted = convert_to_canonical(value, unit)
        if dimension is None:
            dimension = converted.dimension
        elif converted.dimension != dimension:
            raise ValueError(
                f"Cannot sum across dimensions: {dimension} and {converted.dimension}. "
                "Group measurements by dimension before summing.",
            )
        components.append(converted)
        total += converted.value

    if dimension is None:
        return SummedQuantity(
            total=Decimal("0"),
            dimension=None,
            unit=None,
            components=[],
            derivation="No measurements to sum; total is 0.",
        )

    unit = CANONICAL_UNIT[dimension]
    parts = " + ".join(str(c.value) for c in components)
    derivation = f"{parts} = {total} {unit} ({dimension}, {len(components)} parts)"
    return SummedQuantity(
        total=total,
        dimension=dimension,
        unit=unit,
        components=components,
        derivation=derivation,
    )


# ── One-line concept explainers ─────────────────────────────────────────────


_CONCEPT_HELP: dict[str, str] = {
    "measured_quantity": (
        "A measured quantity is the number read off the drawing (a length, "
        "an area, a volume or a count) that becomes a BOQ quantity."
    ),
    "scale": (
        "Scale is how many real-world units one drawing unit represents, so a "
        "line on the sheet becomes a real length; it must be greater than zero."
    ),
    "unit_dimension": (
        "A unit's dimension is what it measures - length, area, volume or "
        "count - and only quantities of the same dimension can be compared or added."
    ),
    "canonical_unit": (
        "The canonical unit is the single metric form we store and compare in: "
        "metres, square metres, cubic metres or pieces, whatever unit was typed."
    ),
    "count_vs_measure": (
        "Count means tallying items one by one (doors, sockets); measure means "
        "reading a length, area or volume with a ruler on the drawing."
    ),
}


def explain_concept(concept: str) -> str:
    """Return a one-line plain-language explanation of a takeoff concept.

    Known concepts: ``measured_quantity``, ``scale``, ``unit_dimension``,
    ``canonical_unit`` and ``count_vs_measure``. An unknown key returns a
    short generic line rather than raising, so a caller can pass a UI label
    through without a guard.
    """
    key = (concept or "").strip().lower()
    return _CONCEPT_HELP.get(
        key,
        "A takeoff turns what is drawn into measured quantities for the estimate.",
    )


def explain_conversion(value: object, unit: str | None) -> str:
    """One-line explanation of how a measured value converts to canonical.

    Convenience wrapper over :func:`convert_to_canonical` that returns just
    the human ``derivation`` string. Propagates the same :class:`ValueError`
    for unknown units or negative / non-finite values.
    """
    return convert_to_canonical(value, unit).derivation

# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Parametric formula engine for assembly components.

Evaluates formulas with variable substitution, conditionals, and lookups.
Used to calculate resource quantities dynamically based on parameters
like height, length, thickness, etc.

Example:
    evaluator = FormulaEvaluator()
    result = evaluator.evaluate(
        "${height} * ${length} * ${thickness}",
        parameters={"height": 3.0, "length": 12.0, "thickness": 0.24},
    )
    # result = 8.64
"""

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Union

# Cheap structural caps applied BEFORE any recursive work, so a
# pathological input (e.g. 5000 nested parens) is rejected in O(n)
# instead of burning the C stack until Python raises RecursionError.
_MAX_FORMULA_LEN = 4096
_MAX_PAREN_DEPTH = 64


class FormulaError(ValueError):
    """Raised when a formula cannot be evaluated."""


class FormulaEvaluator:
    """Safe parametric formula evaluator.

    Supports:
    - Basic math: +, -, *, /, (), decimals
    - Variables: ${height}, ${length}
    - Functions: max(a, b), min(a, b), round(x, n), abs(x), sqrt(x)
    - Conditionals: if(a > b, true_val, false_val)
    - Lookups: lookup("table_name", "key")
    """

    def evaluate(
        self,
        formula: str,
        parameters: dict[str, Union[float, int, str]] | None = None,
        lookup_tables: dict[str, dict[str, Any]] | None = None,
    ) -> float:
        """Evaluate a formula string with parameter substitution.

        Args:
            formula: Formula string, e.g. "${height} * ${length} * 0.24"
            parameters: Named values, e.g. {"height": 3.0, "length": 12.0}
            lookup_tables: Named tables, e.g. {"steel_weights": {"HEB300": 117.7}}

        Returns:
            Computed float result.

        Raises:
            FormulaError: If formula is invalid or evaluation fails.
        """
        params = parameters or {}
        lookups = lookup_tables or {}

        # Reject pathological structure cheaply, up front - never let a
        # caller drive the recursive-descent parser to a RecursionError.
        if not isinstance(formula, str):
            raise FormulaError("Formula must be a string")
        if len(formula) > _MAX_FORMULA_LEN:
            raise FormulaError(f"Formula too long ({len(formula)} > {_MAX_FORMULA_LEN} chars)")
        depth = 0
        for ch in formula:
            if ch == "(":
                depth += 1
                if depth > _MAX_PAREN_DEPTH:
                    raise FormulaError(f"Parenthesis nesting too deep (> {_MAX_PAREN_DEPTH})")
            elif ch == ")":
                depth -= 1

        try:
            # Step 1: Substitute ${param} with values
            substituted = self._substitute_params(formula, params)

            # Step 2: Expand lookup() calls
            expanded = self._expand_lookups(substituted, lookups)

            # Step 3: Expand if() conditionals
            resolved = self._expand_conditionals(expanded)

            # Step 4: Expand built-in functions
            resolved = self._expand_functions(resolved)

            # Step 5: Safe math evaluation
            result = self._safe_eval(resolved)

            if not isinstance(result, (int, float)):
                raise FormulaError(f"Formula must evaluate to a number, got {type(result)}")

            result_f = float(result)
            # A non-finite result (overflow to inf, or 0*inf → nan) must
            # NOT be returned silently - it would propagate as a corrupt
            # null total downstream (same class as ASM-002).
            if not math.isfinite(result_f):
                raise FormulaError("Formula produced a non-finite result (overflow / NaN)")

            return result_f

        except FormulaError:
            raise
        except Exception as exc:
            raise FormulaError(f"Formula evaluation failed: {exc}") from exc

    def _substitute_params(self, formula: str, params: dict) -> str:
        """Replace ${param_name} with parameter values."""

        def replace_var(match: re.Match) -> str:
            name = match.group(1)
            if name not in params:
                raise FormulaError(f"Unknown parameter: '{name}'")
            val = params[name]
            if isinstance(val, str):
                raise FormulaError(f"Parameter '{name}' is a string ('{val}'), cannot use in arithmetic")
            return str(val)

        return re.sub(r"\$\{([a-zA-Z_]\w*)\}", replace_var, formula)

    def _expand_lookups(self, formula: str, lookups: dict) -> str:
        """Replace lookup("table", "key") with looked-up value."""
        pattern = r'lookup\s*\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\)'

        def replace_lookup(match: re.Match) -> str:
            table_name = match.group(1)
            key = match.group(2)
            if table_name not in lookups:
                raise FormulaError(f"Unknown lookup table: '{table_name}'")
            table = lookups[table_name]
            if key not in table:
                raise FormulaError(f"Key '{key}' not found in table '{table_name}'")
            val = table[key]
            if isinstance(val, dict):
                raise FormulaError(f"Lookup '{table_name}[{key}]' returned a dict - use specific field")
            return str(val)

        return re.sub(pattern, replace_lookup, formula)

    def _expand_conditionals(self, formula: str) -> str:
        """Replace if(cond, true_val, false_val) with the evaluated branch.

        The previous implementation used a flat ``[^,]`` regex that
        could not represent a comma inside a branch - so any nested
        ``if(...)`` (whose own commas live inside the parent's branch)
        was sliced apart into a malformed expression. This resolves the
        *innermost* ``if(...)`` first using brace-aware argument
        splitting, then loops, so arbitrarily nested conditionals
        collapse correctly from the inside out.
        """
        max_iterations = 100  # generous; each pass removes one if()
        for _ in range(max_iterations):
            span = self._find_innermost_if(formula)
            if span is None:
                break
            start, end = span
            args = self._split_call_args(formula[start:end])
            if len(args) != 3:
                raise FormulaError(f"if() takes exactly 3 arguments, got {len(args)}: '{formula[start:end]}'")
            cond_str, true_val, false_val = (a.strip() for a in args)
            cond_result = self._eval_condition(cond_str)
            replacement = true_val if cond_result else false_val
            formula = formula[:start] + replacement + formula[end:]
        else:
            raise FormulaError("if() nesting too deep")

        return formula

    def _find_innermost_if(self, formula: str) -> tuple[int, int] | None:
        """Locate an ``if(...)`` whose argument list contains no nested ``if(``.

        Returns the ``(start, end)`` slice - ``start`` at the ``i`` of
        ``if``, ``end`` one past its matching ``)`` - or ``None`` when
        there is no ``if(`` left to expand. Resolving an *innermost*
        ``if`` first guarantees its branches are plain expressions, so
        the brace-aware arg split is unambiguous.
        """
        for m in re.finditer(r"\bif\s*\(", formula):
            open_idx = formula.index("(", m.start())
            depth = 0
            for i in range(open_idx, len(formula)):
                ch = formula[i]
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        # Body strictly between the if()'s own parens.
                        body = formula[open_idx + 1 : i]
                        if not re.search(r"\bif\s*\(", body):
                            return (m.start(), i + 1)
                        break  # nested → try the next match (deeper one)
        return None

    @staticmethod
    def _split_call_args(call: str) -> list[str]:
        """Split ``if(a, b, c)`` into ``['a',' b',' c']`` at top-level commas.

        Commas inside nested parentheses are NOT split points, so a
        branch like ``min(1, 2)`` survives intact.
        """
        inner = call[call.index("(") + 1 : call.rindex(")")]
        args: list[str] = []
        depth = 0
        current = ""
        for ch in inner:
            if ch == "(":
                depth += 1
                current += ch
            elif ch == ")":
                depth -= 1
                current += ch
            elif ch == "," and depth == 0:
                args.append(current)
                current = ""
            else:
                current += ch
        args.append(current)
        return args

    def _eval_condition(self, cond: str) -> bool:
        """Evaluate a comparison: 'a > b', 'a == b', etc."""
        for op in (">=", "<=", "!=", "==", ">", "<"):
            if op in cond:
                parts = cond.split(op, 1)
                if len(parts) != 2:
                    continue
                try:
                    left = self._safe_eval(parts[0].strip())
                    right = self._safe_eval(parts[1].strip())
                except FormulaError:
                    # Wrong split - try the next operator. Programmer
                    # errors (TypeError etc.) propagate so they don't
                    # silently corrupt cost numbers.
                    continue
                if op == ">=":
                    return left >= right
                if op == "<=":
                    return left <= right
                if op == "!=":
                    return left != right
                if op == "==":
                    return left == right
                if op == ">":
                    return left > right
                if op == "<":
                    return left < right
        raise FormulaError(f"Invalid condition: '{cond}'")

    def _expand_functions(self, formula: str) -> str:
        """Expand max(), min(), round(), abs(), sqrt()."""
        # max(a, b, ...)
        formula = re.sub(
            r"max\s*\(([^)]+)\)",
            lambda m: str(max(float(x.strip()) for x in m.group(1).split(","))),
            formula,
        )
        # min(a, b, ...)
        formula = re.sub(
            r"min\s*\(([^)]+)\)",
            lambda m: str(min(float(x.strip()) for x in m.group(1).split(","))),
            formula,
        )
        # round(x, n)
        formula = re.sub(
            r"round\s*\(\s*([^,]+)\s*,\s*(\d+)\s*\)",
            lambda m: str(round(float(m.group(1).strip()), int(m.group(2)))),
            formula,
        )
        # abs(x)
        formula = re.sub(
            r"abs\s*\(\s*([^)]+)\s*\)",
            lambda m: str(abs(float(m.group(1).strip()))),
            formula,
        )
        # sqrt(x)
        formula = re.sub(
            r"sqrt\s*\(\s*([^)]+)\s*\)",
            lambda m: str(math.sqrt(float(m.group(1).strip()))),
            formula,
        )
        return formula

    def _safe_eval(self, expr: str) -> float:
        """Safely evaluate a math expression (no eval/exec).

        Uses a simple recursive descent parser.
        Only allows: numbers, +, -, *, /, (, ), spaces, decimals.
        """
        expr = expr.strip()
        if not expr:
            raise FormulaError("Empty expression")

        # Validate: only safe characters
        if not re.match(r"^[\d+\-*/().\s]+$", expr):
            raise FormulaError(f"Unsafe characters in expression: '{expr}'")

        tokens = self._tokenize(expr)
        pos = [0]  # mutable index

        def parse_expr() -> float:
            result = parse_term()
            while pos[0] < len(tokens) and tokens[pos[0]] in ("+", "-"):
                op = tokens[pos[0]]
                pos[0] += 1
                right = parse_term()
                result = result + right if op == "+" else result - right
            return result

        def parse_term() -> float:
            result = parse_factor()
            while pos[0] < len(tokens) and tokens[pos[0]] in ("*", "/"):
                op = tokens[pos[0]]
                pos[0] += 1
                right = parse_factor()
                if op == "/":
                    if right == 0:
                        raise FormulaError("Division by zero")
                    result /= right
                else:
                    result *= right
            return result

        def parse_factor() -> float:
            if pos[0] >= len(tokens):
                raise FormulaError("Unexpected end of expression")
            tok = tokens[pos[0]]
            if tok == "-":
                pos[0] += 1
                return -parse_factor()
            if tok == "+":
                pos[0] += 1
                return parse_factor()
            if tok == "(":
                pos[0] += 1
                val = parse_expr()
                if pos[0] >= len(tokens) or tokens[pos[0]] != ")":
                    raise FormulaError("Missing closing parenthesis")
                pos[0] += 1
                return val
            try:
                val = float(tok)
                pos[0] += 1
                return val
            except ValueError:
                raise FormulaError(f"Unexpected token: '{tok}'")

        result = parse_expr()
        if pos[0] < len(tokens):
            raise FormulaError(f"Unexpected token: '{tokens[pos[0]]}'")
        return result

    def _tokenize(self, expr: str) -> list[str]:
        """Tokenize a math expression into numbers and operators."""
        tokens: list[str] = []
        i = 0
        while i < len(expr):
            ch = expr[i]
            if ch == " ":
                i += 1
                continue
            if ch in "+-*/()":
                tokens.append(ch)
                i += 1
            elif ch.isdigit() or ch == ".":
                num = ""
                while i < len(expr) and (expr[i].isdigit() or expr[i] == "."):
                    num += expr[i]
                    i += 1
                tokens.append(num)
            else:
                raise FormulaError(f"Unexpected character: '{ch}'")
        return tokens


# ═══════════════════════════════════════════════════════════════════════════
# Factor synthesis (grounded assembly-recipe generation)
# ═══════════════════════════════════════════════════════════════════════════
#
# Turns a plain description ("reinforced concrete wall C30/37, 240mm") plus one
# catalogue component (concrete / rebar / formwork / labour / equipment / …)
# into a grounded *per-unit factor*: the quantity of that component consumed by
# ONE unit of the finished assembly (e.g. 1 m3 of wall). The catalogue rate is
# never touched - only the quantity-per-unit is proposed, so an estimator can
# review and edit each line before saving. The arithmetic is routed through the
# same ``FormulaEvaluator`` used everywhere else so the formula string is
# auditable ("${faces} / ${t}" → 8.3333 m2 of formwork per m3 of wall).


# ── Unit families ──────────────────────────────────────────────────────────
_VOLUME_UNITS = frozenset({"m3", "m³", "cbm", "cum", "cy", "cyd"})
_AREA_UNITS = frozenset({"m2", "m²", "sqm", "sf", "sft"})
_LENGTH_UNITS = frozenset({"m", "lm", "rm", "lf", "rft", "mtr"})
_MASS_T_UNITS = frozenset({"t", "to", "ton", "tonne", "tonnes", "mt"})
_MASS_KG_UNITS = frozenset({"kg", "kgs"})
_HOUR_UNITS = frozenset({"h", "hr", "hrs", "hour", "hours", "std", "stunde"})


def unit_family(unit: str) -> str:
    """Classify a unit string into a dimensional family.

    Args:
        unit: A raw unit label such as ``"m3"``, ``"t"``, ``"h"`` or ``"pcs"``.

    Returns:
        One of ``"volume"``, ``"area"``, ``"length"``, ``"mass_t"``,
        ``"mass_kg"``, ``"hours"`` or ``"other"``.
    """
    normalized = (unit or "").strip().lower()
    if normalized in _VOLUME_UNITS:
        return "volume"
    if normalized in _AREA_UNITS:
        return "area"
    if normalized in _MASS_T_UNITS:
        return "mass_t"
    if normalized in _MASS_KG_UNITS:
        return "mass_kg"
    if normalized in _HOUR_UNITS:
        return "hours"
    if normalized in _LENGTH_UNITS:
        return "length"
    return "other"


# ── Material-kind classification ───────────────────────────────────────────
MATERIAL_KIND_CONCRETE = "concrete"
MATERIAL_KIND_REBAR = "rebar"
MATERIAL_KIND_FORMWORK = "formwork"
MATERIAL_KIND_MASONRY = "masonry"
MATERIAL_KIND_FINISH = "finish"
MATERIAL_KIND_GENERIC = "generic"

# ``reinforc`` is deliberately avoided so "reinforced concrete" is NOT mistaken
# for rebar; only the noun/gerund forms ("reinforcing", "reinforcement") and
# the local(multi-language) rebar terms match.
_REBAR_WORDS = (
    "rebar",
    "reinforcing",
    "reinforcement",
    "bewehrung",
    "betonstahl",
    "rundstahl",
    "moniereisen",
    "armierung",
    "armature",
    "ferraillage",
    "армат",
)
_FORMWORK_WORDS = (
    "formwork",
    "shutter",
    "schalung",
    "falsework",
    "coffrage",
    "encofrado",
    "опалуб",
)
_CONCRETE_WORDS = (
    "concrete",
    "beton",
    "readymix",
    "ready-mix",
    "ready mix",
    "shotcrete",
    "gunite",
    "c12",
    "c16",
    "c20",
    "c25",
    "c30",
    "c35",
    "c40",
    "бетон",
)
_MASONRY_WORDS = (
    "masonry",
    "brick",
    "block",
    "mauerwerk",
    "ziegel",
    "brique",
    "кирпич",
    "блок",
    "кладк",
)
_FINISH_WORDS = (
    "plaster",
    "render",
    "screed",
    "putz",
    "estrich",
    "mortar",
    "mörtel",
    "mortel",
    "paint",
    "coating",
    "enduit",
    "chape",
    "штукатур",
    "стяжк",
)


def classify_material_kind(description: str) -> str:
    """Infer the construction material kind from a component description.

    Order matters: rebar is tested before concrete so "reinforcing steel"
    does not fall through to the concrete branch, and formwork before
    concrete so "wall formwork" is never read as a concrete line.

    Args:
        description: The component (catalogue item) description.

    Returns:
        One of the ``MATERIAL_KIND_*`` constants.
    """
    text = (description or "").lower()
    if any(word in text for word in _REBAR_WORDS):
        return MATERIAL_KIND_REBAR
    if any(word in text for word in _FORMWORK_WORDS):
        return MATERIAL_KIND_FORMWORK
    if any(word in text for word in _CONCRETE_WORDS):
        return MATERIAL_KIND_CONCRETE
    if any(word in text for word in _MASONRY_WORDS):
        return MATERIAL_KIND_MASONRY
    if any(word in text for word in _FINISH_WORDS):
        return MATERIAL_KIND_FINISH
    return MATERIAL_KIND_GENERIC


# ── Resource-type (M / L / E) classification ───────────────────────────────
_LABOR_WORDS = (
    "labor",
    "labour",
    "worker",
    "crew",
    "mason",
    "carpenter",
    "plumber",
    "electrician",
    "fitter",
    "welder",
    "helper",
    "operator",
    "plasterer",
    "roofer",
    "driver",
    "arbeit",
    "lohn",
    "monteur",
    "arbeiter",
)
_EQUIP_WORDS = (
    "equip",
    "machine",
    "crane",
    "excavator",
    "pump",
    "mixer",
    "truck",
    "scaffold",
    "vibrator",
    "compressor",
    "generator",
    "maschine",
    "bagger",
    "kran",
    "gerät",
)


def classify_resource_type(
    description: str,
    tags: Iterable[str] | None = None,
    item_type: str | None = None,
) -> str:
    """Infer the resource type (``material`` / ``labor`` / ``equipment``).

    Prefers an explicit ``item_type`` (e.g. a catalogue ``metadata.type``),
    then description keywords, then a ``tags`` hint, mirroring the way the
    cost catalogue is normally tagged.

    Args:
        description: The component description.
        tags: Optional catalogue tags.
        item_type: Optional explicit type label from catalogue metadata.

    Returns:
        ``"labor"``, ``"equipment"`` or ``"material"`` (the default).
    """
    explicit = (item_type or "").strip().lower()
    if explicit in ("labor", "labour"):
        return "labor"
    if explicit in ("equipment", "plant"):
        return "equipment"
    text = (description or "").lower()
    tag_set = {str(t).lower() for t in (tags or [])}
    if any(word in text for word in _LABOR_WORDS) or "labor" in tag_set:
        return "labor"
    if any(word in text for word in _EQUIP_WORDS) or "equipment" in tag_set:
        return "equipment"
    return "material"


# ── Dimension parsing ──────────────────────────────────────────────────────
_DEFAULT_THICKNESS_M = 0.20
_DEFAULT_REBAR_KG = 100.0
_ASSUMED_THICKNESS_NOTE = f"assumed thickness {int(_DEFAULT_THICKNESS_M * 1000)} mm"
_ASSUMED_HEIGHT_NOTE = "assumed height 1.0 m"

# Formwork faces in contact with concrete, and typical reinforcement ratios
# (kg of steel per m3 of concrete), keyed by structural element.
_FACE_COUNT_BY_ELEMENT = {"wall": 2, "column": 4, "beam": 3, "slab": 1, "foundation": 1}
_REBAR_KG_BY_ELEMENT = {
    "wall": 110.0,
    "column": 150.0,
    "beam": 140.0,
    "slab": 100.0,
    "foundation": 80.0,
}

_GRADE_PAIR = re.compile(r"\bC\s?(\d{2})\s?/\s?(\d{2})\b", re.IGNORECASE)
_GRADE_SINGLE = re.compile(r"\bC(\d{2})\b", re.IGNORECASE)
_DIM_TOKEN = re.compile(r"(\d+(?:[.,]\d+)?)\s*(mm|cm|m)\b", re.IGNORECASE)
_DT_EQUALS = re.compile(r"\b[dt]\s*[:=]\s*(\d+(?:[.,]\d+)?)\s*(mm|cm|m)?", re.IGNORECASE)
# A length unit is REQUIRED on the keyword forms so a "thick" nearby a
# unrelated number (e.g. "24 cm thick, 120 kg/m3") cannot capture the far,
# unitless "120". The backward form covers "24 cm thick" (number first).
_THICK_FWD = re.compile(
    r"(?:thick(?:ness)?|dicke|st[aä]rke|épaisseur|epaisseur|толщ\w*)\D{0,4}"
    r"(\d+(?:[.,]\d+)?)\s*(mm|cm|m)\b",
    re.IGNORECASE,
)
_THICK_BWD = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(mm|cm|m)\b\s*(?:thick|dick|st[aä]rke|épais|epais|толщ)",
    re.IGNORECASE,
)
_HEIGHT_KW = re.compile(
    r"(?:high|height|hoch|h[oö]he|haut\w*|выс\w*)\D{0,6}(\d+(?:[.,]\d+)?)\s*m\b"
    r"|(\d+(?:[.,]\d+)?)\s*m\b\s*(?:high|height|hoch|h[oö]he)",
    re.IGNORECASE,
)
_REBAR_KG_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*kg\s*/\s*m\s?(?:3|³|\^3|cu)", re.IGNORECASE)
_REBAR_T_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:t|to|tonnes?)\s*/\s*m\s?(?:3|³)", re.IGNORECASE)

_ELEMENT_WORDS = (
    ("wall", ("wall", "wand", "voile", "muro", "mauer", "стен")),
    ("column", ("column", "pillar", "stütze", "stutze", "pilier", "poteau", "колонн", "pilar")),
    ("beam", ("beam", "girder", "balken", "poutre", "балк", "ригель", "viga")),
    ("slab", ("slab", "floor", "deck", "platte", "decke", "dalle", "перекрыт", "плит", "losa")),
    ("foundation", ("foundation", "footing", "fundament", "semelle", "фундамент", "zapata")),
)


@dataclass
class DimensionProfile:
    """Dimensions parsed from an assembly description.

    Only the fields that could be recovered from free text are populated;
    the ``effective_*`` helpers supply grounded, element-aware defaults so
    a factor can always be synthesized even from a terse description.
    """

    thickness_m: float | None = None
    height_m: float | None = None
    length_m: float | None = None
    concrete_grade: str | None = None
    element_hint: str | None = None
    rebar_kg_per_m3: float | None = None

    @property
    def face_count(self) -> int:
        """Number of formwork faces in contact with concrete for the element."""
        return _FACE_COUNT_BY_ELEMENT.get(self.element_hint or "", 2)

    def effective_thickness(self) -> float:
        """Return the parsed thickness, or the safe default when unknown."""
        if self.thickness_m is not None and self.thickness_m > 0:
            return self.thickness_m
        return _DEFAULT_THICKNESS_M

    def effective_rebar_ratio(self) -> float:
        """Return the parsed reinforcement ratio (kg/m3) or an element default."""
        if self.rebar_kg_per_m3 is not None and self.rebar_kg_per_m3 > 0:
            return self.rebar_kg_per_m3
        return _REBAR_KG_BY_ELEMENT.get(self.element_hint or "", _DEFAULT_REBAR_KG)


def _num(token: str) -> float:
    """Parse a numeric token, tolerating the EU decimal comma."""
    try:
        return float(str(token).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def _to_metres(value: float, unit: str | None) -> float:
    """Convert a length ``value`` in ``unit`` (mm/cm/m, default mm) to metres."""
    normalized = (unit or "mm").lower()
    if normalized == "m":
        return value
    if normalized == "cm":
        return value / 100.0
    return value / 1000.0


def _match_concrete_grade(text: str) -> str | None:
    pair = _GRADE_PAIR.search(text)
    if pair:
        return f"C{pair.group(1)}/{pair.group(2)}"
    single = _GRADE_SINGLE.search(text)
    if single:
        return f"C{single.group(1)}"
    return None


def _match_element_hint(low: str) -> str | None:
    for hint, words in _ELEMENT_WORDS:
        if any(word in low for word in words):
            return hint
    return None


def _match_thickness(text: str) -> float | None:
    # Explicit thickness markers, most specific first: "24 cm thick" (number
    # before keyword), "thickness 240 mm" (keyword before number), "d=200".
    for pattern in (_THICK_BWD, _THICK_FWD, _DT_EQUALS):
        match = pattern.search(text)
        if match:
            metres = _to_metres(_num(match.group(1)), match.group(2))
            if 0.0 < metres <= 3.0:
                return metres
    # No explicit marker: pick the smallest unit-bearing dimension that falls
    # in a plausible wall/slab thickness band (30 mm … 1.5 m).
    candidates = [
        metres
        for match in _DIM_TOKEN.finditer(text)
        if 0.03 <= (metres := _to_metres(_num(match.group(1)), match.group(2))) <= 1.5
    ]
    if candidates:
        return min(candidates)
    return None


def _match_height(low: str) -> float | None:
    match = _HEIGHT_KW.search(low)
    if not match:
        return None
    token = match.group(1) or match.group(2)
    value = _num(token) if token else 0.0
    return value if value > 0 else None


def _match_rebar_ratio(low: str) -> float | None:
    kg = _REBAR_KG_RE.search(low)
    if kg:
        value = _num(kg.group(1))
        return value if value > 0 else None
    tonnes = _REBAR_T_RE.search(low)
    if tonnes:
        value = _num(tonnes.group(1))
        return value * 1000.0 if value > 0 else None
    return None


def parse_dimensions(text: str) -> DimensionProfile:
    """Parse a dimension profile from a free-text assembly description.

    Recovers thickness (``240mm`` / ``d=240`` / ``0.24 m``), height, concrete
    grade (``C30/37``), a structural-element hint (wall / slab / column / …)
    and an explicit reinforcement ratio (``120 kg/m3``) when present.

    Args:
        text: The assembly description.

    Returns:
        A :class:`DimensionProfile`; any field that could not be parsed is
        left ``None`` and covered by the ``effective_*`` defaults.
    """
    raw = text or ""
    low = raw.lower()
    return DimensionProfile(
        thickness_m=_match_thickness(raw),
        height_m=_match_height(low),
        concrete_grade=_match_concrete_grade(raw),
        element_hint=_match_element_hint(low),
        rebar_kg_per_m3=_match_rebar_ratio(low),
    )


# ── Factor synthesis ───────────────────────────────────────────────────────
_FACTOR_MAX = 1000.0

# Labour / equipment productivity norms (hours consumed per unit of assembly).
_LABOUR_HOURS = {"volume": 2.5, "area": 0.7, "length": 0.6, "other": 1.0, "default": 1.0}
_EQUIP_HOURS = {"volume": 0.35, "area": 0.1, "length": 0.1, "other": 0.3, "default": 0.3}


@dataclass
class SynthesizedFactor:
    """A synthesized per-unit factor with its provenance.

    Attributes:
        factor: Quantity of the component per one unit of the assembly.
        formula: The evaluated formula string (auditable in the UI).
        basis: A short human label for how the factor was derived.
        assumptions: Notes about any defaults applied (e.g. assumed thickness).
    """

    factor: float
    formula: str
    basis: str
    assumptions: tuple[str, ...] = ()


def _clamp_factor(value: float) -> float:
    """Bound a synthesized factor to a finite, non-negative, sane range."""
    if not math.isfinite(value) or value < 0.0:
        return 1.0
    if value > _FACTOR_MAX:
        return _FACTOR_MAX
    return round(value, 4)


def _unit_match_factor(assembly_family: str, component_family: str) -> SynthesizedFactor:
    """Fallback 1:1 factor used when no dimensional rule applies."""
    same = assembly_family == component_family and assembly_family != "other"
    return SynthesizedFactor(1.0, "1.0", "unit-match" if same else "fallback", ())


def _concrete_volume_expr(
    assembly_family: str,
    dims: DimensionProfile,
) -> tuple[str, dict[str, float], tuple[str, ...]]:
    """Formula + params for concrete volume (m3) consumed per assembly unit."""
    if assembly_family == "volume":
        return "1.0", {}, ()
    if assembly_family == "area":
        thickness = dims.effective_thickness()
        notes = () if dims.thickness_m else (_ASSUMED_THICKNESS_NOTE,)
        return "${t}", {"t": thickness}, notes
    if assembly_family == "length":
        thickness = dims.effective_thickness()
        height = dims.height_m if dims.height_m else 1.0
        notes: tuple[str, ...] = () if dims.thickness_m else (_ASSUMED_THICKNESS_NOTE,)
        if not dims.height_m:
            notes = (*notes, _ASSUMED_HEIGHT_NOTE)
        return "${t} * ${h}", {"t": thickness, "h": height}, notes
    return "", {}, ()


def _concrete_factor(
    evaluator: FormulaEvaluator,
    assembly_family: str,
    component_family: str,
    dims: DimensionProfile,
) -> SynthesizedFactor:
    if component_family != "volume":
        return _unit_match_factor(assembly_family, component_family)
    formula, params, notes = _concrete_volume_expr(assembly_family, dims)
    if not formula:
        return _unit_match_factor(assembly_family, component_family)
    value = evaluator.evaluate(formula, params)
    return SynthesizedFactor(_clamp_factor(value), formula, "concrete volume per unit", notes)


def _rebar_factor(
    evaluator: FormulaEvaluator,
    assembly_family: str,
    component_family: str,
    dims: DimensionProfile,
) -> SynthesizedFactor:
    if component_family not in ("mass_t", "mass_kg"):
        return _unit_match_factor(assembly_family, component_family)
    vol_formula, vol_params, notes = _concrete_volume_expr(assembly_family, dims)
    if not vol_formula:
        return _unit_match_factor(assembly_family, component_family)
    ratio = dims.effective_rebar_ratio()
    params = {"ratio": ratio, **vol_params}
    if component_family == "mass_t":
        formula = f"${{ratio}} * ({vol_formula}) / 1000"
    else:
        formula = f"${{ratio}} * ({vol_formula})"
    value = evaluator.evaluate(formula, params)
    ratio_note = () if dims.rebar_kg_per_m3 else (f"assumed rebar ratio {int(ratio)} kg/m3",)
    return SynthesizedFactor(
        _clamp_factor(value),
        formula,
        "rebar ratio x concrete volume",
        (*notes, *ratio_note),
    )


def _formwork_factor(
    evaluator: FormulaEvaluator,
    assembly_family: str,
    component_family: str,
    dims: DimensionProfile,
) -> SynthesizedFactor:
    if component_family != "area":
        return _unit_match_factor(assembly_family, component_family)
    faces = float(dims.face_count)
    if assembly_family == "volume":
        thickness = dims.effective_thickness()
        formula = "${faces} / ${t}"
        value = evaluator.evaluate(formula, {"faces": faces, "t": thickness})
        notes = () if dims.thickness_m else (_ASSUMED_THICKNESS_NOTE,)
        return SynthesizedFactor(_clamp_factor(value), formula, "formwork area per volume", notes)
    if assembly_family == "area":
        value = evaluator.evaluate("${faces}", {"faces": faces})
        return SynthesizedFactor(_clamp_factor(value), "${faces}", "formwork faces per area", ())
    if assembly_family == "length":
        height = dims.height_m if dims.height_m else 1.0
        formula = "${faces} * ${h}"
        value = evaluator.evaluate(formula, {"faces": faces, "h": height})
        notes = () if dims.height_m else (_ASSUMED_HEIGHT_NOTE,)
        return SynthesizedFactor(_clamp_factor(value), formula, "formwork faces x height", notes)
    return _unit_match_factor(assembly_family, component_family)


def _productivity_factor(
    evaluator: FormulaEvaluator,
    assembly_family: str,
    component_family: str,
    table: dict[str, float],
    basis: str,
) -> SynthesizedFactor:
    if component_family != "hours":
        return _unit_match_factor(assembly_family, component_family)
    hours = table.get(assembly_family, table["default"])
    value = evaluator.evaluate("${hours}", {"hours": hours})
    return SynthesizedFactor(_clamp_factor(value), "${hours}", basis, ())


def synthesize_factor(
    *,
    resource_type: str | None,
    component_unit: str,
    assembly_unit: str,
    dims: DimensionProfile,
    description: str = "",
    evaluator: FormulaEvaluator | None = None,
) -> SynthesizedFactor:
    """Synthesize a grounded per-unit factor for one assembly component.

    Labour and equipment lines use productivity norms (hours per unit); every
    other line is classified into a material kind and given a dimension-driven
    factor (concrete by thickness, rebar by ratio × volume, formwork by contact
    area). Anything the rules cannot ground falls back to ``1.0`` so the result
    is never worse than the naive default.

    Args:
        resource_type: ``material`` / ``labor`` / ``equipment`` (or ``None``).
        component_unit: The catalogue component's own unit (``m3``/``t``/``m2``…).
        assembly_unit: The finished assembly's unit (``m3``/``m2``/``m``…).
        dims: Dimensions parsed from the assembly description.
        description: The component description (drives material classification).
        evaluator: Optional shared :class:`FormulaEvaluator` instance.

    Returns:
        A :class:`SynthesizedFactor` carrying the factor, its formula, a basis
        label and any assumption notes. Never raises on bad input.
    """
    engine = evaluator if evaluator is not None else FormulaEvaluator()
    rtype = (resource_type or "material").strip().lower()
    assembly_family = unit_family(assembly_unit)
    component_family = unit_family(component_unit)
    try:
        if rtype == "labor":
            return _productivity_factor(
                engine, assembly_family, component_family, _LABOUR_HOURS, "labour productivity norm"
            )
        if rtype == "equipment":
            return _productivity_factor(
                engine, assembly_family, component_family, _EQUIP_HOURS, "equipment productivity norm"
            )
        kind = classify_material_kind(description)
        if kind == MATERIAL_KIND_CONCRETE:
            return _concrete_factor(engine, assembly_family, component_family, dims)
        if kind == MATERIAL_KIND_REBAR:
            return _rebar_factor(engine, assembly_family, component_family, dims)
        if kind == MATERIAL_KIND_FORMWORK:
            return _formwork_factor(engine, assembly_family, component_family, dims)
        return _unit_match_factor(assembly_family, component_family)
    except FormulaError:
        return SynthesizedFactor(1.0, "1.0", "fallback", ("synthesis error, defaulted to 1.0",))


# ── Typed metadata defaults (waste / burden) ───────────────────────────────
_WASTE_PCT_BY_KIND = {
    MATERIAL_KIND_CONCRETE: 3.0,
    MATERIAL_KIND_REBAR: 5.0,
    MATERIAL_KIND_FORMWORK: 5.0,
    MATERIAL_KIND_MASONRY: 5.0,
    MATERIAL_KIND_FINISH: 10.0,
    MATERIAL_KIND_GENERIC: 5.0,
}
_DEFAULT_LABOUR_BURDEN_PCT = 25.0


def default_component_metadata(resource_type: str, material_kind: str) -> dict[str, float]:
    """Return typed default metadata (waste / burden) for a component.

    The keys mirror the vocabulary the assembly editor already reads when it
    computes the typed total, so an estimator sees a sensible starting point:
    a material carries a ``waste_pct`` sized to its kind, labour carries a
    ``crew_size`` and a social-charge ``burden_pct``, equipment carries the
    ``rental_days`` / ``fuel_cost`` add-on fields.

    Args:
        resource_type: ``material`` / ``labor`` / ``equipment``.
        material_kind: One of the ``MATERIAL_KIND_*`` constants (materials).

    Returns:
        A flat dict of default metadata values.
    """
    rtype = (resource_type or "material").strip().lower()
    if rtype == "labor":
        return {"crew_size": 1.0, "burden_pct": _DEFAULT_LABOUR_BURDEN_PCT}
    if rtype == "equipment":
        return {"rental_days": 0.0, "fuel_cost": 0.0}
    return {"waste_pct": _WASTE_PCT_BY_KIND.get(material_kind, 5.0)}

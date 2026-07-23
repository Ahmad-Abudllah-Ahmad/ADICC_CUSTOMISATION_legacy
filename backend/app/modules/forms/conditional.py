# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Conditional (branching) logic for form templates.

A field in a template may carry two optional rule expressions that make it adapt
to the answers already given on the same form:

* ``visible_if``  - the field is shown only while the expression is true;
* ``required_if`` - the field becomes required while the expression is true (in
  addition to any static ``required`` flag - a rule can turn a field on, never
  silently off).

Both rules live inside the template's ``fields_data`` JSON (per field), so
branching needs no new table and no migration. This module is deliberately
dependency-free - stdlib only, no ORM, no FastAPI, no app imports - so it
unit-tests on a bare interpreter and is imported by
:mod:`app.modules.forms.validation` to gate a submission's completion.

Rule shape
----------
A *rule expression* is either a single comparison or a boolean group, nestable::

    leaf   {"field": "<other field key>", "op": "<operator>", "value": <x>}
    group  {"all": [expr, ...]}   # every sub-expression must hold
           {"any": [expr, ...]}   # at least one sub-expression must hold

Only the operators in :data:`CONDITION_OPERATORS` are allowed. Anything else is
rejected by :func:`collect_rule_issues` (so a bad rule never reaches storage) and
handled defensively by :func:`evaluate_visibility` (so an old snapshot can never
crash a completion). Safety rules the run-time evaluator enforces:

* a rule that points at a field not present in the template evaluates to
  ``False`` - the branch is simply not taken;
* a hidden field contributes no answer to the fields that depend on it, so a
  whole branch collapses cleanly;
* reference cycles are broken rather than followed, so evaluation always
  terminates.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

__all__ = [
    "CONDITION_OPERATORS",
    "MAX_RULE_DEPTH",
    "RuleIssue",
    "UnknownOperatorError",
    "collect_rule_issues",
    "evaluate_visibility",
    "sanitize_expr",
]

# Operators a rule may use, grouped by family: equality, membership, ordering,
# presence. Kept as a tuple so schemas.py can build its validation pattern from
# the same single source of truth (mirroring FIELD_TYPES / CATEGORIES).
CONDITION_OPERATORS: tuple[str, ...] = (
    "eq",
    "neq",
    "in",
    "not_in",
    "gt",
    "lt",
    "gte",
    "lte",
    "empty",
    "not_empty",
)

# Operators whose ``value`` must be a list of candidates.
_LIST_OPS: frozenset[str] = frozenset({"in", "not_in"})

# Hard ceiling on how deeply groups may nest - a guard against a pathological or
# hand-crafted expression, honoured by the sanitiser and the static checker.
MAX_RULE_DEPTH = 25

# Resolver callables threaded through evaluation, so the operators stay decoupled
# from how answers and field definitions are looked up.
_AnswerOf = Callable[[str], Any]
_FieldOf = Callable[[str], "dict[str, Any] | None"]


class UnknownOperatorError(ValueError):
    """A leaf rule names an operator outside :data:`CONDITION_OPERATORS`.

    Raised only inside the run-time evaluator, where the caller catches it and
    falls back to a safe default. The static checker never raises - it reports
    the same problem as a :class:`RuleIssue` instead.
    """


@dataclass(frozen=True)
class RuleIssue:
    """One problem found in a field's conditional rules by the static checker.

    Shaped exactly like ``validation.FieldIssue`` so the two lists merge into a
    single 422 payload without translation.
    """

    field_index: int
    field_key: str | None
    code: str
    message: str


# ── Run-time evaluation ──────────────────────────────────────────────────────


def evaluate_visibility(
    fields: list[dict[str, Any]],
    answers: dict[str, Any] | None,
) -> dict[str, dict[str, bool]]:
    """Resolve every field's live ``visible`` / ``required`` state.

    Returns a map ``{field_key: {"visible": bool, "required": bool}}`` covering
    every keyed field (layout fields included, so a section can be hidden too).

    Semantics:

    * a field with no ``visible_if`` is visible; otherwise it is visible only
      while its ``visible_if`` expression holds;
    * a hidden field is never required and contributes no answer to other fields'
      rules (its branch is treated as blank);
    * a visible field is required when its static ``required`` flag is set *or*
      its ``required_if`` expression holds.

    Never raises: an unknown operator, a malformed rule, a missing referenced
    field or a reference cycle all resolve to safe defaults (show, do not
    require) so a stale snapshot cannot break a completion.
    """
    answers = answers or {}
    by_key: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for field in fields or []:
        if not isinstance(field, dict):
            continue
        key = str(field.get("key", "")).strip()
        if not key or key in by_key:
            continue
        by_key[key] = field
        order.append(key)

    field_of: _FieldOf = by_key.get
    visible_cache: dict[str, bool] = {}
    resolving: set[str] = set()

    def resolve_visible(key: str) -> bool:
        cached = visible_cache.get(key)
        if cached is not None:
            return cached
        field = by_key.get(key)
        if field is None:
            return True
        expr = field.get("visible_if")
        if not expr:
            visible_cache[key] = True
            return True
        if key in resolving:
            # Reference cycle: stop following it and treat this field as visible
            # so evaluation terminates deterministically instead of recursing.
            return True
        resolving.add(key)
        try:
            visible = _safe_eval(expr, answer_of, field_of, default=True)
        finally:
            resolving.discard(key)
        visible_cache[key] = visible
        return visible

    def answer_of(key: str) -> Any:
        # A hidden field contributes no answer - its branch was not taken - so
        # dependants see it as blank rather than reading a stale value.
        if not resolve_visible(key):
            return None
        return answers.get(key)

    result: dict[str, dict[str, bool]] = {}
    for key in order:
        field = by_key[key]
        if not resolve_visible(key):
            result[key] = {"visible": False, "required": False}
            continue
        required = bool(field.get("required", False))
        req_expr = field.get("required_if")
        if req_expr and not required:
            required = _safe_eval(req_expr, answer_of, field_of, default=False)
        result[key] = {"visible": True, "required": required}
    return result


def _safe_eval(expr: Any, answer_of: _AnswerOf, field_of: _FieldOf, *, default: bool) -> bool:
    """Evaluate a rule expression, collapsing an unknown operator to ``default``."""
    try:
        return _eval_expr(expr, answer_of, field_of)
    except UnknownOperatorError:
        return default


def _eval_expr(expr: Any, answer_of: _AnswerOf, field_of: _FieldOf) -> bool:
    """Evaluate one expression: an ``all`` / ``any`` group, or a leaf rule."""
    if not isinstance(expr, dict):
        return False
    if "all" in expr:
        subs = expr.get("all")
        if not isinstance(subs, (list, tuple)):
            return False
        return all(_eval_expr(sub, answer_of, field_of) for sub in subs)
    if "any" in expr:
        subs = expr.get("any")
        if not isinstance(subs, (list, tuple)):
            return False
        return any(_eval_expr(sub, answer_of, field_of) for sub in subs)
    return _eval_rule(expr, answer_of, field_of)


def _eval_rule(rule: dict[str, Any], answer_of: _AnswerOf, field_of: _FieldOf) -> bool:
    """Evaluate a single leaf comparison against the referenced field's answer."""
    op = str(rule.get("op", "")).strip()
    if op not in CONDITION_OPERATORS:
        raise UnknownOperatorError(op)
    ref = str(rule.get("field", "")).strip()
    field = field_of(ref) if ref else None
    if not ref or field is None:
        # Missing / unknown referenced field: the branch is not taken.
        return False
    return _apply_operator(op, field, answer_of(ref), rule.get("value"))


def _apply_operator(op: str, field: dict[str, Any], left: Any, value: Any) -> bool:
    """Apply a whitelisted operator to a field's answer (``left``) and ``value``."""
    if op == "empty":
        return _is_blank(field, left)
    if op == "not_empty":
        return not _is_blank(field, left)
    if op == "eq":
        return _scalar_equal(left, value)
    if op == "neq":
        return not _scalar_equal(left, value)
    if op == "in":
        return _in_candidates(left, value)
    if op == "not_in":
        return not _in_candidates(left, value)
    # Ordering operators: comparable only when both sides parse as numbers.
    left_n = _as_number(left)
    value_n = _as_number(value)
    if left_n is None or value_n is None:
        return False
    if op == "gt":
        return left_n > value_n
    if op == "lt":
        return left_n < value_n
    if op == "gte":
        return left_n >= value_n
    if op == "lte":
        return left_n <= value_n
    raise UnknownOperatorError(op)  # pragma: no cover - op is pre-validated


# ── Value helpers ────────────────────────────────────────────────────────────


def _is_blank(field: dict[str, Any] | None, value: Any) -> bool:
    """Whether ``value`` counts as "not answered" for the referenced field.

    Mirrors ``validation._is_empty_answer`` for the shapes a rule cares about: an
    unticked checkbox, an empty string / list, and a signature with neither name
    nor image data all read as blank.
    """
    ftype = str((field or {}).get("type", "")).strip()
    if value is None:
        return True
    if ftype == "checkbox":
        return value is not True
    if isinstance(value, bool):
        return False
    if isinstance(value, (list, tuple)):
        return not any(str(item).strip() for item in value)
    if isinstance(value, dict):
        name = str(value.get("name", "") or "").strip()
        data = str(value.get("data", "") or "").strip()
        return not (name or data)
    return str(value).strip() == ""


def _as_number(value: Any) -> float | None:
    """Parse a numeric value to float, tolerating a comma decimal. ``None`` on fail."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value if value is not None else "").strip().replace(",", ".")
    if text == "":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _as_truth(value: Any) -> bool:
    """Coerce a value to a boolean for checkbox / yes-no comparisons."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    text = str(value).strip().lower()
    if text in ("true", "yes", "y", "1", "on", "checked"):
        return True
    if text in ("false", "no", "n", "0", "off", "unchecked", ""):
        return False
    return True


def _scalar_equal(left: Any, value: Any) -> bool:
    """Type-tolerant equality: booleans, then numbers, then trimmed strings."""
    if left is None or value is None:
        return left is None and value is None
    if isinstance(left, bool) or isinstance(value, bool):
        return _as_truth(left) == _as_truth(value)
    left_n = _as_number(left)
    value_n = _as_number(value)
    if left_n is not None and value_n is not None:
        return left_n == value_n
    if isinstance(left, (list, tuple)) or isinstance(value, (list, tuple)):
        return _norm_list(left) == _norm_list(value)
    return str(left).strip() == str(value).strip()


def _norm_token(value: Any) -> tuple[str, Any]:
    """Normalise a scalar to a comparable token: numeric when it parses, else text."""
    number = _as_number(value)
    if number is not None:
        return ("n", number)
    return ("s", str(value).strip())


def _norm_list(value: Any) -> list[tuple[str, Any]]:
    """Normalise a value into a sorted list of tokens for order-insensitive compare."""
    items = value if isinstance(value, (list, tuple)) else [value]
    return sorted(_norm_token(item) for item in items if str(item).strip() != "")


def _in_candidates(left: Any, value: Any) -> bool:
    """Membership: does ``left`` (scalar or list) intersect the ``value`` list?"""
    candidates = value if isinstance(value, (list, tuple)) else [value]
    tokens = {_norm_token(candidate) for candidate in candidates if str(candidate).strip() != ""}
    if not tokens:
        return False
    if isinstance(left, (list, tuple)):
        return any(_norm_token(item) in tokens for item in left if str(item).strip() != "")
    if left is None:
        return False
    return _norm_token(left) in tokens


# ── Static validation (template save path) ───────────────────────────────────


def collect_rule_issues(fields: list[dict[str, Any]]) -> list[RuleIssue]:
    """Statically validate every field's ``visible_if`` / ``required_if`` rules.

    Reports, without evaluating against any answers: an unknown operator, a
    malformed structure, a reference to a field that is not in the template, a
    rule that refers to its own field, an over-deep nest, and an ``in`` /
    ``not_in`` whose value is not a list. Empty list == all rules are coherent.

    Used by ``validation.validate_template_fields`` so a template carrying a bad
    rule is rejected on save rather than misbehaving at fill time.
    """
    issues: list[RuleIssue] = []
    known_keys = {
        str(field.get("key", "")).strip()
        for field in fields or []
        if isinstance(field, dict) and str(field.get("key", "")).strip()
    }
    for idx, field in enumerate(fields or []):
        if not isinstance(field, dict):
            continue
        key = str(field.get("key", "")).strip() or None
        for slot in ("visible_if", "required_if"):
            expr = field.get(slot)
            if not expr:
                continue
            _check_expr(expr, idx, key, slot, known_keys, issues, depth=0)
    return issues


def _check_expr(
    expr: Any,
    idx: int,
    key: str | None,
    slot: str,
    known_keys: set[str],
    issues: list[RuleIssue],
    depth: int,
) -> None:
    """Recursively validate one rule expression, appending any problems found."""
    if depth > MAX_RULE_DEPTH:
        issues.append(RuleIssue(idx, key, "rule_too_deep", f"A {slot} rule is nested too deeply."))
        return
    if not isinstance(expr, dict):
        issues.append(RuleIssue(idx, key, "malformed_rule", f"A {slot} rule must be an object."))
        return

    is_group = False
    for group in ("all", "any"):
        if group not in expr:
            continue
        is_group = True
        subs = expr.get(group)
        if not isinstance(subs, (list, tuple)):
            issues.append(RuleIssue(idx, key, "malformed_rule", f"A '{group}' group must be a list."))
            continue
        for sub in subs:
            _check_expr(sub, idx, key, slot, known_keys, issues, depth + 1)
    if is_group:
        return

    op = str(expr.get("op", "")).strip()
    if op not in CONDITION_OPERATORS:
        issues.append(RuleIssue(idx, key, "unknown_operator", f"Unknown condition operator '{op or '(blank)'}'."))

    ref = str(expr.get("field", "")).strip()
    if not ref:
        issues.append(RuleIssue(idx, key, "malformed_rule", f"A {slot} rule must name a field."))
    elif ref not in known_keys:
        issues.append(RuleIssue(idx, key, "unknown_condition_ref", f"A {slot} rule refers to unknown field '{ref}'."))
    elif key is not None and ref == key:
        issues.append(RuleIssue(idx, key, "self_reference", f"A {slot} rule cannot refer to its own field."))

    if op in _LIST_OPS and not isinstance(expr.get("value"), (list, tuple)):
        issues.append(RuleIssue(idx, key, "condition_needs_list", f"Operator '{op}' needs a list of values."))


# ── Persistence normalisation ────────────────────────────────────────────────


def sanitize_expr(expr: Any, _depth: int = 0) -> dict[str, Any] | None:
    """Return a small, JSON-safe copy of a rule expression, or ``None``.

    Keeps only the recognised structure (``field`` / ``op`` / ``value`` for a
    leaf, ``all`` / ``any`` for a group), drops ``None`` and unknown keys, trims
    and coerces scalars, and caps nesting depth. Used by ``normalize_fields`` so
    a template's stored rules stay compact and predictable. Never raises - junk
    collapses to ``None`` (i.e. no rule, the safe default).
    """
    if _depth > MAX_RULE_DEPTH or not isinstance(expr, dict):
        return None
    out: dict[str, Any] = {}
    for group in ("all", "any"):
        raw = expr.get(group)
        if isinstance(raw, (list, tuple)):
            cleaned = [c for c in (sanitize_expr(sub, _depth + 1) for sub in raw) if c is not None]
            if cleaned:
                out[group] = cleaned
    ref = expr.get("field")
    if ref is not None and str(ref).strip():
        out["field"] = str(ref).strip()[:60]
    op = expr.get("op")
    if op is not None and str(op).strip():
        out["op"] = str(op).strip()
    if expr.get("value") is not None:
        cleaned_value = _clean_value(expr["value"])
        if cleaned_value is not None:
            out["value"] = cleaned_value
    return out or None


def _clean_value(value: Any) -> Any:
    """Coerce a rule's comparison value to a JSON scalar or a flat scalar list."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, (list, tuple)):
        flat = [_clean_value(item) for item in value if not isinstance(item, (list, dict))]
        return [item for item in flat if item is not None][:50]
    if isinstance(value, dict):
        return None
    return str(value)[:200]

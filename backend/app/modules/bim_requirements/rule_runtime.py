# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure-function executor for rule packs loaded from YAML.

This module is intentionally side-effect free: no DB access, no logging
of secrets, no network. It accepts already-parsed :class:`RulePack`
objects from :mod:`yaml_loader` plus a list of *element-like* dicts and
returns a structured :class:`PackResult`.

What is an "element"?
~~~~~~~~~~~~~~~~~~~~~
The runtime treats elements as plain dicts with at least these keys
(other keys are tolerated and ignored):

* ``id`` (str)
* ``ifc_class`` (str, optional)
* ``classification`` (dict[str, str], optional) - e.g. ``{"din276": "330"}``
* ``properties`` (dict[str, Any], optional)
* ``quantities`` (dict[str, Any], optional) - e.g. ``{"area": 37.5}``

The reason we use plain dicts (instead of the ORM model from
``bim_hub``) is to keep this module unit-testable and reusable: callers
can feed it any source of element-shaped data - DB rows, IFC parser
output, even hand-written test fixtures - without dragging the DB layer
into the test boundary.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.modules.bim_requirements.yaml_loader import (
    Predicate,
    PropertyAssertion,
    Rule,
    RulePack,
    Selector,
    SetVsSetAssertion,
)

# Re-compiled regexes are cached per process. 256-char ReDoS guard already
# applied at load time, so we can compile freely here.
_REGEX_CACHE: dict[str, re.Pattern[str]] = {}


# ── Result types ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RuleResult:
    """Outcome of one (rule, element) pair."""

    rule_id: str
    element_id: str
    passed: bool
    message: str | None = None
    evidence: dict[str, Any] | None = None


@dataclass
class PackResult:
    """Aggregated outcome of one pack over a full element set."""

    pack_id: str
    total_elements: int = 0
    passed: int = 0
    failed: int = 0
    not_applicable: int = 0
    results: list[RuleResult] = field(default_factory=list)


# ── Property lookup ────────────────────────────────────────────────────────

# Reserved selector keys handled outside the generic property predicate
# loop. ``ifc_class`` is promoted to a top-level attribute in our element
# shape, and ``id`` is always exposed for traceability.
_TOP_LEVEL_KEYS: frozenset[str] = frozenset({"ifc_class", "id", "name"})


def _get_value(element: dict[str, Any], key: str) -> Any:
    """Look up ``key`` on an element with sensible fall-throughs.

    Priority:
        1. top-level field (``ifc_class``, ``id``, ``name``)
        2. ``properties[key]``
        3. ``quantities[key]``
        4. ``classification[key]`` (lowercased classifier name supported)
    """
    if key in _TOP_LEVEL_KEYS:
        return element.get(key)
    props = element.get("properties") or {}
    if isinstance(props, dict) and key in props:
        return props[key]
    qty = element.get("quantities") or {}
    if isinstance(qty, dict) and key in qty:
        return qty[key]
    cls = element.get("classification") or {}
    if isinstance(cls, dict):
        if key in cls:
            return cls[key]
        if key.lower() in cls:
            return cls[key.lower()]
    return None


# ── Operator implementations ───────────────────────────────────────────────


def _to_number(value: Any) -> float | None:
    """Coerce to float; return None if not numeric."""
    if value is None or isinstance(value, bool):
        # Booleans subclass int - exclude them so `True > 0` doesn't pass
        # a numeric comparison rule by accident.
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _equal(a: Any, b: Any) -> bool:
    """Equality with light type-coercion for numeric/string mixes."""
    if a == b:
        return True
    na, nb = _to_number(a), _to_number(b)
    if na is not None and nb is not None:
        return na == nb
    if a is None or b is None:
        return False
    return str(a) == str(b)


def evaluate_predicate(predicate: Predicate, actual: Any) -> bool:
    """Evaluate one operator against an actual value.

    Returns ``True`` when the predicate holds, ``False`` otherwise. Never
    raises - a malformed predicate is impossible because the
    :class:`Predicate` model validated it at load time, and an
    impossible-to-evaluate combination (e.g. ``gt`` against a non-numeric
    string) just yields ``False``.
    """
    op = predicate.op
    expected = predicate.value

    if op == "exists":
        # Honour explicit "must not exist" via `value: false`.
        must_exist = expected is None or bool(expected)
        present = actual is not None and not (isinstance(actual, str) and actual == "")
        return present if must_exist else not present

    if actual is None:
        # All other operators require a value to compare; absence fails.
        return False

    if op == "eq":
        return _equal(actual, expected)
    if op == "neq":
        return not _equal(actual, expected)

    if op in ("gt", "gte", "lt", "lte"):
        a, b = _to_number(actual), _to_number(expected)
        if a is None or b is None:
            return False
        if op == "gt":
            return a > b
        if op == "gte":
            return a >= b
        if op == "lt":
            return a < b
        return a <= b  # lte

    if op == "in":
        return any(_equal(actual, item) for item in expected or [])

    if op == "contains":
        # Works for strings and sequences alike.
        try:
            if isinstance(actual, str):
                return str(expected) in actual
            return expected in actual  # type: ignore[operator]
        except TypeError:
            return False

    if op == "regex":
        pattern = _REGEX_CACHE.get(expected)
        if pattern is None:
            try:
                pattern = re.compile(expected)
            except re.error:
                return False
            _REGEX_CACHE[expected] = pattern
        return pattern.search(str(actual)) is not None

    if op == "between":
        lo, hi = expected
        a = _to_number(actual)
        nlo, nhi = _to_number(lo), _to_number(hi)
        if a is None or nlo is None or nhi is None:
            return False
        return nlo <= a <= nhi

    # Defensive: should be unreachable because op was validated at load.
    return False


# ── Selector ───────────────────────────────────────────────────────────────


def matches_selector(selector: Selector, element: dict[str, Any]) -> bool:
    """True when every predicate in the selector holds against ``element``."""
    # ifc_class shortcut.
    if selector.ifc_class is not None:
        actual = element.get("ifc_class") or element.get("element_type")
        if not isinstance(actual, str):
            return False
        if actual.lower() != selector.ifc_class.lower():
            return False

    # Classification predicates (AND).
    if selector.classification:
        elem_class = element.get("classification") or {}
        if not isinstance(elem_class, dict):
            return False
        for code_sys, expected in selector.classification.items():
            actual = elem_class.get(code_sys)
            if actual is None:
                return False
            # Suffix-wildcard supported (e.g. "300*").
            if isinstance(expected, str) and expected.endswith("*"):
                if not str(actual).startswith(expected[:-1]):
                    return False
            elif str(actual) != str(expected):
                return False

    # Generic property predicates (AND).
    for pred in selector.properties:
        actual = _get_value(element, pred.key)
        if not evaluate_predicate(pred, actual):
            return False

    return True


# ── Failure-message templating ─────────────────────────────────────────────

_TEMPLATE_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_.\-]*)\s*\}\}")


def render_message(template: str, element: dict[str, Any]) -> str:
    """Substitute ``{{Property}}`` placeholders.

    Looks up each placeholder via :func:`_get_value`. Missing properties
    render as ``"<missing>"`` so the operator can see at a glance which
    property is absent. Implemented without any external template engine.
    """
    if not template:
        return ""

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        val = _get_value(element, key)
        if val is None:
            return "<missing>"
        return str(val)

    return _TEMPLATE_RE.sub(_replace, template)


# ── Per-rule evaluation ────────────────────────────────────────────────────


def evaluate_rule(
    rule: Rule,
    element: dict[str, Any],
    *,
    other_elements: list[dict[str, Any]] | None = None,
) -> RuleResult | None:
    """Evaluate one rule against one element.

    Returns ``None`` when the element does not match the rule's selector
    (so the caller can distinguish *not applicable* from *failed*).
    """
    if not matches_selector(rule.selector, element):
        return None

    element_id = str(element.get("id") or element.get("name") or "<unknown>")

    if isinstance(rule.assertion, PropertyAssertion):
        pred = rule.assertion.property
        actual = _get_value(element, pred.key)
        passed = evaluate_predicate(pred, actual)
        message = None if passed else render_message(rule.failure_message, element)
        return RuleResult(
            rule_id=rule.id,
            element_id=element_id,
            passed=passed,
            message=message,
            evidence={"property": pred.key, "actual": actual, "expected": pred.value},
        )

    if isinstance(rule.assertion, SetVsSetAssertion):
        spec = rule.assertion.set_vs_set
        others = other_elements or []
        passed = True
        failing_other: dict[str, Any] | None = None
        for other in others:
            if not matches_selector(spec.other_selector, other):
                continue
            # For our purposes the predicate is evaluated by reading the
            # named property from *this* element and checking against the
            # constant in spec.property. Real geometric clearance would
            # require coordinates; we surface the property used as
            # evidence so the caller (BIM hub) can swap in a geometric
            # implementation later without changing the YAML schema.
            actual = _get_value(element, spec.property.key)
            if not evaluate_predicate(spec.property, actual):
                passed = False
                failing_other = other
                break
        message = None if passed else render_message(rule.failure_message, element)
        return RuleResult(
            rule_id=rule.id,
            element_id=element_id,
            passed=passed,
            message=message,
            evidence={
                "metric": spec.metric,
                "property": spec.property.key,
                "other_id": (failing_other or {}).get("id") if failing_other else None,
            },
        )

    # Unreachable: schema validation has already ensured assertion shape.
    return None


# ── Pack evaluation ────────────────────────────────────────────────────────


def evaluate_rule_pack(
    pack: RulePack,
    elements: list[dict[str, Any]],
) -> PackResult:
    """Run every rule in ``pack`` against every element.

    The pack summary distinguishes three states:

    * **passed**   - every applicable rule passed against this element
    * **failed**   - at least one applicable rule failed against this element
    * **not_applicable** - no rule's selector matched this element

    Result rows are emitted only for *applicable* (rule, element) pairs;
    "not_applicable" is reported only as an aggregate to keep the result
    list bounded on large models.
    """
    result = PackResult(pack_id=pack.pack.id, total_elements=len(elements))
    for element in elements:
        element_passed = True
        element_was_applicable = False
        for rule in pack.rules:
            outcome = evaluate_rule(rule, element, other_elements=elements)
            if outcome is None:
                continue
            element_was_applicable = True
            result.results.append(outcome)
            if not outcome.passed:
                element_passed = False
        if not element_was_applicable:
            result.not_applicable += 1
        elif element_passed:
            result.passed += 1
        else:
            result.failed += 1
    return result


__all__ = [
    "PackResult",
    "RuleResult",
    "evaluate_predicate",
    "evaluate_rule",
    "evaluate_rule_pack",
    "matches_selector",
    "render_message",
]

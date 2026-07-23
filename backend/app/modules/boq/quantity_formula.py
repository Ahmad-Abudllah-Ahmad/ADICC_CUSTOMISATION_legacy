# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Per-element quantity formulas for BOQ<->BIM quantity links (Issue #347).

A quantity link can project a position's quantity out of its bound BIM
elements in two ways:

* ``field`` mode (the original) reads one canonical quantity key off each
  element (``area_m2`` / ``volume_m3`` / ...) and aggregates.
* ``formula`` mode evaluates a small arithmetic expression PER element
  against that element's own variables (``area_m2 * 0.5``,
  ``length_m * height_m``, ``count * 1.15`` ...) and then aggregates the
  per-element results with the SAME aggregation.

This module is the ``formula`` mode engine. It is deliberately
self-contained (``boq`` is a core module and must not import the optional
``measurement`` / ``eac`` packages) and models the same proven
allow-listed-AST + Decimal approach ``measurement.formula`` uses, but with
an intentionally MINIMAL grammar for v1:

    number literals, bare variable names, unary + / -, binary + - * /,
    parentheses, and the allow-listed pure functions ``round`` / ``min`` /
    ``max`` (``round(x)``, ``round(x, n)``, ``min(a, b, ...)``,
    ``max(a, b, ...)``). These three mirror the frontend grid engine
    (``engine.ts``), so a per-element or assembly formula using them resolves
    on both sides; ``round`` uses banker-free half-up rounding on the
    non-negative quantity domain.

There are NO other function calls, NO attribute/subscript access, NO
comparisons, NO power/modulo, and NO names beyond the variables supplied by
the caller. Anything else is rejected at parse time by walking the AST and
whitelisting node types - never ``eval``/``exec``. All arithmetic is
``Decimal`` so quantities stay exact; division by zero and unknown
variables raise explicitly (never a silent zero).

The variable-name normaliser and the numeric test in here are mirrored
byte-for-byte on the frontend (``frontend/src/features/boq/grid/formula/
elementFormula.ts``) and locked by a shared vectors fixture so a formula
written against the in-grid variable names resolves to the same value the
backend computes.
"""

from __future__ import annotations

import ast
import math
import re
from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal, DivisionByZero, InvalidOperation
from typing import Any

# Guardrails - a BOQ formula is a short arithmetic expression, never a program.
MAX_FORMULA_LEN = 512
MAX_AST_DEPTH = 32

# ASCII-only identifier grammar so the normaliser's ``lower()`` matches the
# frontend's ``toLowerCase()`` exactly (no locale-specific case folding).
_NON_IDENT_RE = re.compile(r"[^A-Za-z0-9]")
_MULTI_US_RE = re.compile(r"_+")
_NUMERIC_STR_RE = re.compile(r"^[+-]?(\d+(\.\d+)?|\.\d+)([eE][+-]?\d+)?$")


class FormulaError(ValueError):
    """Base class for every formula problem (all are 4xx-worthy)."""


class FormulaSyntaxError(FormulaError):
    """The formula is empty, too long, unparsable, or uses a banned construct."""


class FormulaMathError(FormulaError):
    """The formula is well-formed but cannot be evaluated (e.g. div by zero)."""


class UnknownVariableError(FormulaError):
    """The formula references a name the element does not provide."""


# ── Shared helpers (mirrored on the frontend) ─────────────────────────────


def normalize_var_name(raw: Any) -> str:
    """Turn an arbitrary quantity/property key into a formula identifier.

    Algorithm (must stay identical to the frontend ``normalizeVarName``):
    replace every non ``[A-Za-z0-9]`` character with ``_``, collapse runs of
    ``_`` and strip leading/trailing ``_``, lowercase (ASCII), and prefix an
    ``_`` when the result would start with a digit. Returns ``""`` for a key
    that has no usable characters (caller skips those).
    """
    s = _NON_IDENT_RE.sub("_", str(raw))
    s = _MULTI_US_RE.sub("_", s).strip("_")
    s = s.lower()
    if not s:
        return ""
    if s[0].isdigit():
        s = "_" + s
    return s


def is_numeric_value(value: Any) -> bool:
    """True when ``value`` is a finite number or a plain numeric string.

    Booleans are NOT numeric (a flag is never a quantity). Mirrors the
    frontend ``isNumericValue``.
    """
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return math.isfinite(value)
    if isinstance(value, str):
        return bool(_NUMERIC_STR_RE.match(value.strip()))
    return False


def _to_decimal(value: Any) -> Decimal:
    """Coerce a numeric value/string to Decimal via ``str`` (exact, no float)."""
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise FormulaMathError(f"not a number: {value!r}") from exc


def build_element_vars(
    quantities: Mapping[str, Any] | None,
    properties: Mapping[str, Any] | None = None,
) -> dict[str, Decimal]:
    """Build the variable map a formula sees for one element.

    Mirrors the frontend ``buildElementVars``: every numeric entry from the
    element's ``quantities`` map (primary), then every numeric ``properties``
    entry whose normalised name is not already taken (secondary). Keys are
    normalised via :func:`normalize_var_name`; non-numeric values are skipped.
    """
    out: dict[str, Decimal] = {}
    for source in (quantities or {}, properties or {}):
        if not isinstance(source, Mapping):
            continue
        for key, val in source.items():
            if not is_numeric_value(val):
                continue
            name = normalize_var_name(key)
            if not name or name in out:
                continue
            out[name] = _to_decimal(val)
    return out


# ── Parser / safety walk ──────────────────────────────────────────────────

# Only these node types may appear anywhere in a formula. Everything else
# (Call, Attribute, Subscript, Compare, BoolOp, Pow, Mod, IfExp, containers,
# comprehensions, ...) is rejected before evaluation.
_ALLOWED_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div)
_ALLOWED_UNARYOPS = (ast.UAdd, ast.USub)

# The only function calls a formula may contain. All are pure, total (given a
# valid argument count) and Decimal-safe. Kept in lock-step with the frontend
# grid engine so the same formula resolves identically on both sides.
_ALLOWED_FUNCS = frozenset({"round", "min", "max"})


def _strip_lead(expr: str) -> str:
    text = (expr or "").strip()
    if text.startswith("="):  # tolerate a spreadsheet-style leading '='
        text = text[1:].strip()
    return text


def _parse(formula: str) -> ast.Expression:
    text = _strip_lead(formula)
    if not text:
        raise FormulaSyntaxError("empty formula")
    if len(text) > MAX_FORMULA_LEN:
        raise FormulaSyntaxError(f"formula too long (>{MAX_FORMULA_LEN} chars)")
    try:
        tree = ast.parse(text, mode="eval")
    except (SyntaxError, ValueError) as exc:
        raise FormulaSyntaxError(f"invalid formula: {text!r}") from exc
    return tree


def _check_safe(tree: ast.Expression) -> None:
    """Reject any node type outside the minimal arithmetic grammar."""

    def walk(node: ast.AST, depth: int) -> None:
        if depth > MAX_AST_DEPTH:
            raise FormulaSyntaxError("formula nested too deeply")
        if isinstance(node, ast.Expression):
            walk(node.body, depth + 1)
            return
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise FormulaSyntaxError(f"unsupported literal: {node.value!r}")
            if isinstance(node.value, float) and not math.isfinite(node.value):
                raise FormulaSyntaxError("non-finite numeric literal")
            return
        if isinstance(node, ast.Name):
            if not isinstance(node.ctx, ast.Load):
                raise FormulaSyntaxError("names are read-only in a formula")
            return
        if isinstance(node, ast.BinOp):
            if not isinstance(node.op, _ALLOWED_BINOPS):
                raise FormulaSyntaxError("only + - * / are allowed")
            walk(node.left, depth + 1)
            walk(node.right, depth + 1)
            return
        if isinstance(node, ast.UnaryOp):
            if not isinstance(node.op, _ALLOWED_UNARYOPS):
                raise FormulaSyntaxError("only unary + / - are allowed")
            walk(node.operand, depth + 1)
            return
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FUNCS:
                raise FormulaSyntaxError("only round / min / max function calls are allowed")
            if node.keywords:
                raise FormulaSyntaxError("function keyword arguments are not allowed")
            name = node.func.id
            n_args = len(node.args)
            if name == "round" and n_args not in (1, 2):
                raise FormulaSyntaxError("round takes 1 or 2 arguments")
            if name in ("min", "max") and n_args < 1:
                raise FormulaSyntaxError(f"{name} needs at least one argument")
            for arg in node.args:
                if isinstance(arg, ast.Starred):
                    raise FormulaSyntaxError("star-arguments are not allowed")
                walk(arg, depth + 1)
            return
        raise FormulaSyntaxError(f"unsupported expression: {type(node).__name__}")

    walk(tree, 0)


def validate_formula(formula: str) -> None:
    """Parse + safety-check a formula. Raise :class:`FormulaSyntaxError` if bad.

    Does NOT evaluate (no variables needed), so it is safe to call at
    create/update time to reject a malformed formula as a 4xx up front.
    """
    _check_safe(_parse(formula))


def list_formula_vars(formula: str) -> list[str]:
    """Return the variable names a formula references, in first-seen order.

    Function-position names (the ``round`` in ``round(x)``) are NOT variables
    and are excluded, so an allow-listed call never looks like an undeclared
    reference to the caller.
    """
    tree = _parse(formula)
    _check_safe(tree)
    func_names = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    ordered = sorted(
        ((n.lineno, n.col_offset, n.id) for n in ast.walk(tree) if isinstance(n, ast.Name) and id(n) not in func_names),
        key=lambda item: (item[0], item[1]),
    )
    seen: list[str] = []
    for _lineno, _col, name in ordered:
        if name not in seen:
            seen.append(name)
    return seen


# ── Evaluation ─────────────────────────────────────────────────────────────


def _eval(node: ast.AST, variables: Mapping[str, Decimal], depth: int) -> Decimal:
    if depth > MAX_AST_DEPTH:
        raise FormulaSyntaxError("formula nested too deeply")
    if isinstance(node, ast.Constant):
        return _to_decimal(node.value)
    if isinstance(node, ast.Name):
        if node.id in variables:
            return variables[node.id]
        raise UnknownVariableError(f"unknown variable: {node.id!r}")
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, _ALLOWED_UNARYOPS):
        val = _eval(node.operand, variables, depth + 1)
        return val if isinstance(node.op, ast.UAdd) else -val
    if isinstance(node, ast.BinOp) and isinstance(node.op, _ALLOWED_BINOPS):
        left = _eval(node.left, variables, depth + 1)
        right = _eval(node.right, variables, depth + 1)
        try:
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            # Div
            if right == 0:
                raise FormulaMathError("division by zero")
            return left / right
        except (InvalidOperation, DivisionByZero, ArithmeticError) as exc:
            raise FormulaMathError(f"arithmetic error: {exc}") from exc
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        name = node.func.id
        args = [_eval(arg, variables, depth + 1) for arg in node.args]
        try:
            if name == "min":
                return min(args)
            if name == "max":
                return max(args)
            if name == "round":
                ndigits = int(args[1]) if len(args) == 2 else 0
                if ndigits < 0:
                    raise FormulaMathError("round digits must be >= 0")
                quantum = Decimal(1).scaleb(-ndigits)
                return args[0].quantize(quantum, rounding=ROUND_HALF_UP)
        except (InvalidOperation, DivisionByZero, ArithmeticError) as exc:
            raise FormulaMathError(f"arithmetic error: {exc}") from exc
    # Should be unreachable after _check_safe, but never fall through to eval.
    raise FormulaSyntaxError(f"unsupported expression: {type(node).__name__}")


def evaluate_formula(formula: str, variables: Mapping[str, Any]) -> Decimal:
    """Evaluate ``formula`` against ``variables`` and return an exact Decimal.

    ``variables`` maps identifier -> numeric value (Decimal / int / float /
    numeric string). Raises :class:`FormulaSyntaxError` for a banned/broken
    grammar, :class:`UnknownVariableError` for a name the map lacks, and
    :class:`FormulaMathError` for division by zero or a non-finite result.
    """
    tree = _parse(formula)
    _check_safe(tree)
    resolved: dict[str, Decimal] = {k: _to_decimal(v) for k, v in variables.items()}
    result = _eval(tree.body, resolved, 0)
    if not result.is_finite():
        raise FormulaMathError("formula produced a non-finite result")
    return result

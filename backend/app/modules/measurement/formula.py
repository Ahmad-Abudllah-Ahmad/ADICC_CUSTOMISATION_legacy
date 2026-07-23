# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Safe arithmetic evaluator for measurement formulas.

Quantity determination should be transparent: every quantity keeps the formula
that produced it (for example ``3.50 * 2.40`` for an area, or ``L * B * H`` with
named dimensions), so a checker can see and audit how a number was reached.
This is exactly how REB 23.003 measurement lines and ÖNORM A 2063 work, and how
any careful estimator writes a take-off anywhere in the world.

The evaluator is a small AST walker, not ``eval``: it accepts only numbers,
named variables, the four operators, power, parentheses and a short whitelist
of functions (min, max, abs, round, sqrt). Anything else raises. All maths is
done in :class:`~decimal.Decimal` so quantities stay exact.
"""

from __future__ import annotations

import ast
from decimal import Decimal, InvalidOperation
from typing import Any


class MeasurementError(ValueError):
    """Raised when a formula is invalid or cannot be evaluated."""


def _dec(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise MeasurementError(f"not a number: {value!r}") from exc


def _sqrt(value: Decimal) -> Decimal:
    if value < 0:
        raise MeasurementError("sqrt of a negative number")
    return value.sqrt()


_FUNCS = {
    "min": lambda *a: min(a),
    "max": lambda *a: max(a),
    "abs": lambda x: abs(x),
    "round": lambda x, n=0: _dec(round(x, int(n))),
    "sqrt": _sqrt,
}


def _norm_vars(variables: dict[str, Any] | None) -> dict[str, Decimal]:
    out: dict[str, Decimal] = {}
    for key, val in (variables or {}).items():
        out[str(key)] = _dec(val)
        out[str(key).lower()] = _dec(val)
    return out


def safe_eval(expr: str, variables: dict[str, Any] | None = None) -> Decimal:
    """Evaluate a measurement formula to a :class:`Decimal`.

    ``variables`` maps names used in the formula (case-insensitive) to values,
    for example ``{"L": 3.5, "B": 2.4}`` for ``"L * B"``.
    """
    tree = _parse(expr)
    return _eval(tree.body, _norm_vars(variables))


def _parse(expr: str) -> ast.Expression:
    """Parse a formula, tolerating a leading ``=`` (spreadsheet paste)."""
    text = (expr or "").strip()
    if text.startswith("="):
        text = text[1:].strip()
    if not text:
        raise MeasurementError("empty formula")
    try:
        return ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise MeasurementError(f"invalid formula: {text!r}") from exc


def list_variables(expr: str) -> list[str]:
    """Return the variable names a formula needs, in first-seen order.

    Lets a take-off UI prompt for exactly the dimensions a template uses, for
    example ``["L", "B", "H"]`` for ``"L * B * H"``. Function names such as
    ``sqrt`` are not variables and are excluded.
    """
    tree = _parse(expr)
    # ast.walk is breadth-first, so sort names by their position in the source
    # to get left-to-right order, then keep the first occurrence of each.
    names = sorted(
        (
            (node.lineno, node.col_offset, node.id)
            for node in ast.walk(tree)
            if isinstance(node, ast.Name) and node.id not in _FUNCS
        ),
        key=lambda item: (item[0], item[1]),
    )
    seen: list[str] = []
    for _lineno, _col, name in names:
        if name not in seen:
            seen.append(name)
    return seen


_BIN_OPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod)


def _eval(node: ast.AST, variables: dict[str, Decimal]) -> Decimal:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise MeasurementError(f"unsupported constant: {node.value!r}")
        return _dec(node.value)
    if isinstance(node, ast.Name):
        key = node.id
        if key in variables:
            return variables[key]
        if key.lower() in variables:
            return variables[key.lower()]
        raise MeasurementError(f"unknown variable: {key!r}")
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        val = _eval(node.operand, variables)
        return val if isinstance(node.op, ast.UAdd) else -val
    if isinstance(node, ast.BinOp) and isinstance(node.op, _BIN_OPS):
        left = _eval(node.left, variables)
        right = _eval(node.right, variables)
        return _apply(node.op, left, right)
    if isinstance(node, ast.Call):
        return _call(node, variables)
    raise MeasurementError("formula contains an unsupported expression")


def _apply(op: ast.operator, left: Decimal, right: Decimal) -> Decimal:
    try:
        if isinstance(op, ast.Add):
            return left + right
        if isinstance(op, ast.Sub):
            return left - right
        if isinstance(op, ast.Mult):
            return left * right
        if isinstance(op, ast.Div):
            if right == 0:
                raise MeasurementError("division by zero")
            return left / right
        if isinstance(op, ast.Mod):
            if right == 0:
                raise MeasurementError("division by zero")
            return left % right
        if isinstance(op, ast.Pow):
            # Only integer exponents keep Decimal exactness.
            if right != right.to_integral_value():
                raise MeasurementError("only integer powers are allowed")
            return left ** int(right)
    except (InvalidOperation, ArithmeticError) as exc:
        raise MeasurementError(f"arithmetic error: {exc}") from exc
    raise MeasurementError("unsupported operator")


def _call(node: ast.Call, variables: dict[str, Decimal]) -> Decimal:
    if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCS:
        raise MeasurementError("formula calls an unsupported function")
    if node.keywords:
        raise MeasurementError("keyword arguments are not allowed in a formula")
    args = [_eval(a, variables) for a in node.args]
    try:
        return _dec(_FUNCS[node.func.id](*args))
    except MeasurementError:
        raise
    except (TypeError, ValueError, ArithmeticError) as exc:
        raise MeasurementError(f"bad call to {node.func.id}: {exc}") from exc

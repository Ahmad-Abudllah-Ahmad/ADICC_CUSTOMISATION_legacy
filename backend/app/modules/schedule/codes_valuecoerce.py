# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure typed-value coercion for schedule UDFs (T2.3).

Dependency-free (stdlib only) so it imports and unit-tests on the local runner.
A UDF stores its value in the typed column matching its declared kind, so the
grouped query can ORDER/GROUP natively; this module is the single place that
validates a raw value against a kind and decides which column it lands in.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

UDF_VALUE_TYPES = ("text", "number", "date", "bool", "enum")


def _to_bool(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    s = str(raw).strip().lower()
    if s in ("true", "1", "yes", "y", "on"):
        return True
    if s in ("false", "0", "no", "n", "off"):
        return False
    raise ValueError(f"{raw!r} is not a boolean")


def coerce_udf_value(value_type: str, enum_values: list[str] | None, raw: Any) -> dict[str, Any]:
    """Validate + place ``raw`` into the typed column for ``value_type``.

    Returns a dict with keys ``value_text`` / ``value_number`` / ``value_date`` /
    ``value_bool`` (exactly one non-null, or all null when ``raw`` is None / ""
    to clear the value). Raises ``ValueError`` (router -> 422) on a value that
    does not fit the declared type.
    """
    cols: dict[str, Any] = {"value_text": None, "value_number": None, "value_date": None, "value_bool": None}
    if raw is None or (isinstance(raw, str) and raw == ""):
        return cols
    if value_type == "text":
        cols["value_text"] = str(raw)
    elif value_type == "number":
        try:
            cols["value_number"] = Decimal(str(raw))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"{raw!r} is not a number") from exc
    elif value_type == "date":
        s = str(raw)
        try:
            date.fromisoformat(s)
        except ValueError as exc:
            raise ValueError(f"{raw!r} is not an ISO date (YYYY-MM-DD)") from exc
        cols["value_date"] = s
    elif value_type == "bool":
        cols["value_bool"] = _to_bool(raw)
    elif value_type == "enum":
        s = str(raw)
        if s not in (enum_values or []):
            raise ValueError(f"{s!r} is not one of the allowed enum values")
        cols["value_text"] = s
    else:
        raise ValueError(f"unknown UDF value_type {value_type!r}")
    return cols


def udf_value_readback(value_type: str, row: Any) -> Any:
    """Return the stored value for a UDF value row, by the UDF's declared type.

    ``row`` is any object exposing ``value_text`` / ``value_number`` /
    ``value_date`` / ``value_bool`` (an ORM row or a plain stub).
    """
    if value_type == "number":
        return row.value_number
    if value_type == "date":
        return row.value_date
    if value_type == "bool":
        return row.value_bool
    return row.value_text

# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure base-resolution helper for the estimating-methodology module.

This is the small deterministic bridge between a project's resource totals (the
money summed per resource type across a BOQ or one object/section) and the leaf
base tokens that the cascade engine (:mod:`app.modules.methodology.cascade`)
consumes. A methodology's ``base_mapping`` declares, for each cascade base
token, which resource types feed it::

    base_mapping = {
        "labor":     ["labor"],
        "machinery": ["equipment_machinery"],
        "materials": ["material"],
        "equipment": ["installed_equipment"],
    }

:func:`resolve_bases` turns that mapping plus a ``resource_totals`` map into the
``bases`` dict ``compute_cascade`` expects.

Design constraints (intentional, mirror ``cascade.py`` - see
docs/strategy/ESTIMATE_METHODOLOGIES_PLAN.md sections 5-6):

* Standard library only - ``decimal`` and ``typing``. No imports from ``app.*``
  and no third-party packages, so this single file can be loaded and unit-tested
  standalone via ``importlib`` on Python 3.11 (the local interpreter) while the
  rest of the backend requires Python 3.12.
* No PEP 695 ``type X = ...`` aliases (3.12+ only). ``from __future__ import
  annotations`` keeps every annotation a string so nothing is evaluated at
  import time.
* All money is :class:`decimal.Decimal`; ``float`` is rejected to keep the
  arithmetic exact, exactly as the cascade engine does.

The error type :class:`BaseResolutionError` subclasses :class:`ValueError`, the
same contract ``cascade.CascadeError`` follows. It is defined locally (rather
than imported from ``cascade``) so this module stays fully self-contained for
the standalone Python 3.11 import check.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Mapping, Sequence

__all__ = [
    "BaseResolutionError",
    "resolve_bases",
]


class BaseResolutionError(ValueError):
    """Raised when a base mapping or resource totals are structurally invalid.

    Subclasses :class:`ValueError` so callers that only catch ``ValueError``
    still handle it, while code that wants to distinguish base-resolution
    problems can catch this type specifically. Mirrors
    :class:`app.modules.methodology.cascade.CascadeError`.
    """


def _coerce_decimal(value: object, what: str) -> Decimal:
    """Coerce ``value`` to ``Decimal`` (accepting int/str), or raise.

    Floats are rejected to keep resolution exact; callers must pass Decimals
    (or ints/strings) for monetary inputs. ``bool`` is rejected explicitly
    because it is an ``int`` subclass. Identical policy to the cascade engine's
    ``_coerce_decimal`` so the two stay behaviourally consistent.
    """
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):  # bool is an int subclass; reject explicitly.
        raise BaseResolutionError(f"{what} must be a Decimal, got bool")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        try:
            return Decimal(value)
        except Exception as exc:  # noqa: BLE001 - re-raised as a clear error.
            raise BaseResolutionError(f"{what} is not a valid number: {value!r}") from exc
    raise BaseResolutionError(f"{what} must be a Decimal (or int/str), got {type(value).__name__}")


def resolve_bases(
    base_mapping: Mapping[str, Sequence[str]],
    resource_totals: Mapping[str, Decimal],
    *,
    fallback_token: str | None = None,
    fallback_amount: Decimal = Decimal("0"),
) -> dict[str, Decimal]:
    """Resolve cascade base tokens from per-resource-type totals.

    For each base token in ``base_mapping``, sum ``resource_totals`` over each
    listed resource type. A resource type listed in the mapping but absent from
    ``resource_totals`` contributes ``Decimal("0")``.

    Args:
        base_mapping: Maps each cascade base token to the resource types that
            feed it, e.g. ``{"labor": ["labor"], "machinery":
            ["equipment_machinery"]}``. Each value must be a sequence of
            resource-type strings (``str`` itself is rejected: a bare string
            would silently iterate per character).
        resource_totals: Money summed per resource type across the scope (one
            BOQ, object, or section). Values may be ``Decimal`` (preferred),
            ``int``, or numeric ``str``; ``float`` is rejected.
        fallback_token: When ``base_mapping`` is empty, or ``resource_totals``
            is empty (the scope has no resources), and this is given, the
            function returns ``{fallback_token: fallback_amount}`` instead of an
            all-zero / empty result. ``None`` (default) disables the fallback.
        fallback_amount: The amount paired with ``fallback_token`` when the
            fallback fires. Coerced like any monetary input (``float``
            rejected).

    Returns:
        A dict mapping each base token to its resolved :class:`Decimal` total,
        suitable for ``compute_cascade(spec, bases)``. When the fallback fires,
        a single-entry dict keyed by ``fallback_token``.

    Raises:
        BaseResolutionError: If ``base_mapping`` is not a mapping, a mapping
            value is not a (non-string) sequence of strings, a resource type or
            base token is not a string, or any monetary value is a ``float`` /
            not a valid number.
    """
    if not isinstance(base_mapping, Mapping):
        raise BaseResolutionError(f"base_mapping must be a mapping, got {type(base_mapping).__name__}")
    if not isinstance(resource_totals, Mapping):
        raise BaseResolutionError(f"resource_totals must be a mapping, got {type(resource_totals).__name__}")

    # Resolve and validate resource totals up front (Decimal-exact, float-free).
    resolved_totals: dict[str, Decimal] = {}
    for res_type, raw in resource_totals.items():
        if not isinstance(res_type, str):
            raise BaseResolutionError(f"resource type key must be a string, got {type(res_type).__name__}")
        resolved_totals[res_type] = _coerce_decimal(raw, f"resource total {res_type!r}")

    # Fallback path: an empty mapping, or a scope with no resources at all.
    if (not base_mapping or not resolved_totals) and fallback_token is not None:
        if not isinstance(fallback_token, str):
            raise BaseResolutionError(f"fallback_token must be a string, got {type(fallback_token).__name__}")
        return {fallback_token: _coerce_decimal(fallback_amount, "fallback_amount")}

    resolved: dict[str, Decimal] = {}
    for base_token, resource_types in base_mapping.items():
        if not isinstance(base_token, str):
            raise BaseResolutionError(f"base token key must be a string, got {type(base_token).__name__}")
        # A bare string is a sequence of characters - almost never intended and
        # a classic silent bug, so reject it explicitly (a list/tuple is meant).
        if isinstance(resource_types, str) or not isinstance(resource_types, Sequence):
            raise BaseResolutionError(
                f"base_mapping[{base_token!r}] must be a sequence of resource "
                f"types, got {type(resource_types).__name__}"
            )
        total = Decimal(0)
        for res_type in resource_types:
            if not isinstance(res_type, str):
                raise BaseResolutionError(
                    f"base_mapping[{base_token!r}] contains a non-string resource type: {type(res_type).__name__}"
                )
            # Missing resource types contribute 0.
            total += resolved_totals.get(res_type, Decimal(0))
        resolved[base_token] = total

    return resolved

# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Typed exceptions for the saved-views engine.

Each safety primitive raises its own exception so the router can map it to the
correct HTTP status and so a reviewer can trace a refusal back to the gate that
produced it:

    * :class:`RegistrationError` - a queryable entity was registered without a
      scoper, with a duplicate type, or with a field that does not resolve to a
      real mapped column. Raised at module startup, never at request time.
    * :class:`ScopeDenied` - the mandatory scoper refused outright (primitive 1).
      Surfaces as HTTP 404 to avoid an existence oracle, mirroring
      :func:`app.dependencies.verify_project_access`.
    * :class:`WhitelistError` - a spec referenced a column / operator that is not
      whitelisted for the target entity (primitive 2). Surfaces as HTTP 422.
    * :class:`BudgetError` - a spec exceeded the static complexity ceiling, the
      row cap, or the statement timeout (primitive 3). Surfaces as HTTP 422.
"""

from __future__ import annotations


class SavedViewsError(Exception):
    """Base class for every saved-views engine error."""


class RegistrationError(SavedViewsError):
    """A queryable entity registration is invalid.

    Raised by :func:`app.modules.saved_views.registry.register_queryable_entity`
    at startup so a misconfigured module fails the boot rather than a request.
    """


class ScopeDenied(SavedViewsError):
    """The scoper refused to resolve the query.

    The router maps this to HTTP 404 (not 403) so the caller cannot tell a
    forbidden resource apart from a missing one.
    """


class WhitelistError(SavedViewsError):
    """A spec referenced a non-whitelisted column or operator.

    Carries the offending field/operator so the API response can name it.
    The router maps this to HTTP 422.
    """

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


class BudgetError(SavedViewsError):
    """A spec exceeded a result-budget gate.

    Raised by the static complexity ceiling, the row cap, or the statement
    timeout. The router maps this to HTTP 422.
    """

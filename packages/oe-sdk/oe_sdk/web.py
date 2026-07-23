"""Web and data-layer building blocks, re-exported from the platform core.

Importing this module imports ``app.database`` and ``app.dependencies``, which
build the SQLAlchemy async engine at import time and therefore need a configured
PostgreSQL ``DATABASE_URL``. Inside a running deployment that is always
satisfied. The top-level ``oe_sdk`` package resolves these names lazily, so a
bare ``import oe_sdk`` does not require a database. Accessing ``oe_sdk.SessionDep``
(or importing directly from ``oe_sdk.web``) is what pulls the engine in.

Data layer:

- ``Base`` is the declarative base every model subclasses. It provides ``id``
  (a UUID primary key), ``created_at`` and ``updated_at`` already, so do not
  redeclare them. Name your table ``oe_<short>_<entity>``.
- ``GUID`` is the portable UUID column type decorator.

Router dependencies (from ``app.dependencies``):

- ``SessionDep`` yields an ``AsyncSession`` that commits or rolls back around
  the request.
- ``CurrentUserId`` is the authenticated user id and forces a 401 when there is
  no valid token. ``CurrentUserPayload`` is the full decoded token,
  ``OptionalUserPayload`` is ``None`` for anonymous callers.
- ``RequirePermission("<perm>")`` gates a route by permission. Wire it in
  ``dependencies=[Depends(RequirePermission("..."))]``. ``RequireRole`` gates by
  minimum role, and ``RequirePermissionOrApiKey`` accepts either a bearer token
  or an ``X-API-Key`` header and returns the caller's user id.
- ``verify_project_access(project_id, user_id, session)`` enforces that the
  caller owns or is a team member of a project, returning 404 rather than 403 so
  it cannot be used to probe for ids.
"""

from __future__ import annotations

from app.database import GUID, Base
from app.dependencies import (
    CurrentUserId,
    CurrentUserPayload,
    OptionalUserPayload,
    RequirePermission,
    RequirePermissionOrApiKey,
    RequireRole,
    SessionDep,
    get_current_user_id,
    get_session,
    verify_project_access,
)

__all__ = [
    "Base",
    "GUID",
    "SessionDep",
    "CurrentUserId",
    "CurrentUserPayload",
    "OptionalUserPayload",
    "RequirePermission",
    "RequirePermissionOrApiKey",
    "RequireRole",
    "verify_project_access",
    "get_session",
    "get_current_user_id",
]

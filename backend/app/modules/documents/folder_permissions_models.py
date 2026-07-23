# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Per-folder permission ORM models for the file-manager.

Tables:
    oe_documents_folder_permission - grants a project member ``viewer``,
                                     ``editor``, or ``owner`` access to a
                                     specific ``(scope_kind, scope_path)``
                                     folder within a project.

Semantics
---------
A "folder" here is a virtual concept: it is identified by a
:class:`FileKind`-style key (``bim_model``, ``dwg_drawing``, ``sheet``,
``photo``, ``document``, …) optionally narrowed by a ``scope_path``
sub-path. ``scope_path = NULL`` means "all files of this kind". A
non-null ``scope_path`` lets the owner restrict sub-paths
(e.g. ``photo`` kind, path ``site/2026-05`` → only the May 2026 site
photos).

Access logic (enforced in :mod:`folder_permissions_service`):

* Project owner → bypass entirely (existing repository behaviour).
* Project member with NO matching grant on a scoped folder → 404.
* Project member with a matching grant → role determines write capability:

  =======  =====================  =========================
  Role     Read (list / get)      Write (upload / delete)
  =======  =====================  =========================
  viewer   yes                    no
  editor   yes                    upload + delete OWN files
  owner    yes                    full
  =======  =====================  =========================

* Folders that have **no grants at all** stay open to every project
  member - keeps the default UX (Team Strip) backward compatible.

Why a soft-delete column instead of ``DELETE``?
    Revoking is a frequent operation and we want it to be an atomic
    flip. Hard-deleting would also lose the audit trail of who had
    access when. A future ``GET /folder-permissions/audit/`` endpoint
    can replay history off the same table.

Why ``UniqueConstraint(project_id, scope_kind, scope_path, user_id)``?
    Prevents a user accumulating multiple conflicting roles on the
    same scope (one user, one role per folder). On re-grant the
    router maps the unique violation to **409 Conflict** so the UI
    can surface a useful message instead of a generic 500.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import GUID, Base

# Allowed roles. Kept as a tuple (rather than a SQLAlchemy ``Enum``) so
# adding a new role is a Python-only change - no DDL alteration needed.
FOLDER_ROLE_VIEWER = "viewer"
FOLDER_ROLE_EDITOR = "editor"
FOLDER_ROLE_OWNER = "owner"

FOLDER_ROLES: tuple[str, ...] = (
    FOLDER_ROLE_VIEWER,
    FOLDER_ROLE_EDITOR,
    FOLDER_ROLE_OWNER,
)

# Ordered for ``can_write`` / role-strength comparisons. Higher index
# means broader capability.
FOLDER_ROLE_RANK: dict[str, int] = {
    FOLDER_ROLE_VIEWER: 0,
    FOLDER_ROLE_EDITOR: 1,
    FOLDER_ROLE_OWNER: 2,
}


def role_satisfies(actual: str, required: str) -> bool:
    """Return True when ``actual`` is at least as strong as ``required``."""
    return FOLDER_ROLE_RANK.get(actual, -1) >= FOLDER_ROLE_RANK.get(required, 99)


class FolderPermission(Base):
    """Per-folder grant scoped to a project member.

    The ``(project_id, scope_kind, scope_path, user_id)`` unique
    constraint includes a special-case for ``NULL`` ``scope_path``:
    SQLite and PostgreSQL both treat NULLs as distinct under a unique
    index, which is exactly the behaviour we want - an "all files of
    this kind" grant and a "specific sub-path" grant are independent
    rows.
    """

    __tablename__ = "oe_documents_folder_permission"

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "scope_kind",
            "scope_path",
            "user_id",
            name="uq_folder_permission_scope_user",
        ),
        # Hot-path index: "what does user X see on project P?"
        Index(
            "ix_folder_permission_project_user",
            "project_id",
            "user_id",
        ),
        # Hot-path index: "is this (kind, path) restricted at all?"
        Index(
            "ix_folder_permission_scope",
            "project_id",
            "scope_kind",
            "scope_path",
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scope_kind: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    scope_path: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        default=None,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_users_user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=FOLDER_ROLE_VIEWER,
        server_default=FOLDER_ROLE_VIEWER,
    )
    granted_by: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_users_user.id", ondelete="CASCADE"),
        nullable=False,
    )
    granted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    revoked: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        scope = f"{self.scope_kind}:{self.scope_path or '*'}"
        return (
            f"<FolderPermission project={self.project_id} scope={scope}"
            f" user={self.user_id} role={self.role} revoked={self.revoked}>"
        )

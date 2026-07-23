# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Activity codes, user-defined fields and saved layouts (T2.3).

One scope model, deliberately: every code dictionary, UDF and layout is owned
by exactly one project. There is no implicit enterprise/global namespace that
silently merges on exchange. Workspace "library" dictionaries are rows with
``is_library=True`` + NULL ``project_id`` that are *copied* into a project
(brand new rows), never referenced live, so an export never carries a dangling
cross-scope reference.

These tables live under the ``schedule`` module (prefix ``oe_schedule_*``) and
attach to :class:`app.modules.schedule.models.Activity` via plain ``GUID`` FKs.
They are imported for their side effect (table registration on ``Base.metadata``)
from :mod:`app.modules.schedule.models`.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import GUID, Base

# Allowed UDF value types. ``enum`` constrains to ``enum_values``.
UDF_VALUE_TYPES = ("text", "number", "date", "bool", "enum")
# Allowed layout share scopes (mirrors saved_views; never ``public``).
LAYOUT_SHARE_SCOPES = ("private", "project", "workspace")


class CodeDictionary(Base):
    """A named code dimension (e.g. "Area", "Discipline") scoped to ONE project.

    Workspace library templates are rows with ``is_library=True`` and a NULL
    ``project_id``; they are copied into a project, never referenced live.
    """

    __tablename__ = "oe_schedule_code_dictionary"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_sched_codedict_project_name"),
        Index("ix_sched_codedict_project", "project_id"),
    )

    # Nullable ONLY when ``is_library`` is true (a workspace-level template).
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
        nullable=True,
    )
    is_library: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    color_band: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"<CodeDictionary {self.name!r} project={self.project_id} library={self.is_library}>"


class CodeValue(Base):
    """One node in a dictionary's value tree (self-parented).

    ``depth`` is denormalized for cheap color-banding. Sibling-code uniqueness
    among root values (NULL parent) is enforced in the service layer because a
    SQL unique over a nullable column treats NULLs as distinct.
    """

    __tablename__ = "oe_schedule_code_value"
    __table_args__ = (
        UniqueConstraint("dictionary_id", "parent_id", "code", name="uq_sched_codeval_dict_parent_code"),
        Index("ix_sched_codeval_dict", "dictionary_id"),
        Index("ix_sched_codeval_parent", "parent_id"),
    )

    dictionary_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_schedule_code_dictionary.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_schedule_code_value.id", ondelete="CASCADE"),
        nullable=True,
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default="")
    color: Mapped[str] = mapped_column(String(20), nullable=False, default="", server_default="")
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"<CodeValue {self.code!r} dict={self.dictionary_id} depth={self.depth}>"


class CodeAssignment(Base):
    """Assigns ONE value of a dictionary to an activity (v1 single-valued).

    The ``(dictionary_id, value_id)`` index makes server-side grouping an index
    scan; the unique ``(activity_id, dictionary_id)`` enforces "one Area per
    activity".
    """

    __tablename__ = "oe_schedule_code_assignment"
    __table_args__ = (
        UniqueConstraint("activity_id", "dictionary_id", name="uq_sched_codeassign_activity_dict"),
        Index("ix_sched_codeassign_value", "dictionary_id", "value_id"),
        Index("ix_sched_codeassign_activity", "activity_id"),
    )

    activity_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_schedule_activity.id", ondelete="CASCADE"),
        nullable=False,
    )
    dictionary_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_schedule_code_dictionary.id", ondelete="CASCADE"),
        nullable=False,
    )
    value_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_schedule_code_value.id", ondelete="CASCADE"),
        nullable=False,
    )

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"<CodeAssignment act={self.activity_id} dict={self.dictionary_id} value={self.value_id}>"


class ScheduleUdf(Base):
    """A typed user-defined field definition per project."""

    __tablename__ = "oe_schedule_udf"
    __table_args__ = (
        UniqueConstraint("project_id", "key", name="uq_sched_udf_project_key"),
        Index("ix_sched_udf_project", "project_id"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
        nullable=False,
    )
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default="")
    value_type: Mapped[str] = mapped_column(String(16), nullable=False, default="text", server_default="text")
    enum_values: Mapped[list] = mapped_column(  # type: ignore[assignment]
        JSON, nullable=False, default=list, server_default="[]"
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"<ScheduleUdf {self.key!r} type={self.value_type} project={self.project_id}>"


class ScheduleUdfValue(Base):
    """One activity's value for one UDF, stored in the typed column for its kind.

    Storing the value in a real typed column (not a JSON blob) lets the grouped
    query ORDER/GROUP natively and keeps grouping cheap via the per-type
    indexes.
    """

    __tablename__ = "oe_schedule_udf_value"
    __table_args__ = (
        UniqueConstraint("activity_id", "udf_id", name="uq_sched_udfval_activity_udf"),
        Index("ix_sched_udfval_udf_text", "udf_id", "value_text"),
        Index("ix_sched_udfval_udf_number", "udf_id", "value_number"),
        Index("ix_sched_udfval_udf_date", "udf_id", "value_date"),
        Index("ix_sched_udfval_activity", "activity_id"),
    )

    activity_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_schedule_activity.id", ondelete="CASCADE"),
        nullable=False,
    )
    udf_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_schedule_udf.id", ondelete="CASCADE"),
        nullable=False,
    )
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_number: Mapped[object | None] = mapped_column(Numeric(18, 4), nullable=True)
    value_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    value_bool: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"<ScheduleUdfValue act={self.activity_id} udf={self.udf_id}>"


class ScheduleLayout(Base):
    """A saved schedule view (columns, grouping, sort, filters, bar styling).

    Modelled on :class:`app.modules.saved_views.models.SavedView`: the same
    ``private``/``project``/``workspace`` sharing, but a dedicated schedule table
    so the rich ``spec`` is first-class and the unique key is per-*schedule*.
    ``spec`` is re-validated by the ``LayoutSpec`` Pydantic model on every read
    and write, never trusted as-is.
    """

    __tablename__ = "oe_schedule_layout"
    __table_args__ = (
        UniqueConstraint("owner_id", "schedule_id", "name", name="uq_sched_layout_owner_schedule_name"),
        Index("ix_sched_layout_schedule", "schedule_id"),
        Index("ix_sched_layout_project", "project_id"),
        Index("ix_sched_layout_owner", "owner_id"),
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_users_user.id", ondelete="CASCADE"),
        nullable=False,
    )
    schedule_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_schedule_schedule.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Denormalized for scope checks; an activity reaches a project via its
    # schedule, but carrying it here keeps share-scope queries a single hop.
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    share_scope: Mapped[str] = mapped_column(String(16), nullable=False, default="private", server_default="private")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    spec: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        JSON, nullable=False, default=dict, server_default="{}"
    )
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"<ScheduleLayout {self.name!r} schedule={self.schedule_id} scope={self.share_scope}>"

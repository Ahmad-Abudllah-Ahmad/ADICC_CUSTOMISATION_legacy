# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pydantic schemas for activity codes, UDFs and saved layouts (T2.3).

The layout ``spec`` uses a small namespaced key grammar: a bare name
(``name``, ``total_float``) is a static :class:`Activity` column resolved
through the ``saved_views`` whitelist; ``code:<uuid>`` and ``udf:<uuid>``
resolve through the join tables. The static-column filter is a real
``saved_views`` :class:`FilterSpec`, so it rides the audited ``bind()``
security path; the dynamic code/UDF predicates are isolated in their own typed
arrays.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.saved_views.schemas import FilterSpec, SortSpec

# Namespaced layout key: a static column name, or ``code:<uuid>`` / ``udf:<uuid>``.
_UUID_RE = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
LAYOUT_KEY_RE = re.compile(rf"^(?:[a-z][a-z0-9_]*|code:{_UUID_RE}|udf:{_UUID_RE})$")

MAX_LAYOUT_GROUP_BY = 3  # schedule layouts allow 3 levels (saved_views caps static group_by at 2)
MAX_LAYOUT_COLUMNS = 60

UDF_VALUE_TYPES = ("text", "number", "date", "bool", "enum")
LAYOUT_SHARE_SCOPES = ("private", "project", "workspace")
TIMESCALES = ("day", "week", "month", "quarter", "year")


def parse_layout_key(key: str) -> tuple[str, str | None]:
    """Return ``(kind, ref)`` for a layout column/group key.

    ``kind`` is ``"static"`` (ref is the bare column name), ``"code"`` (ref is a
    dictionary id string) or ``"udf"`` (ref is a UDF id string).
    """
    if key.startswith("code:"):
        return "code", key[len("code:") :]
    if key.startswith("udf:"):
        return "udf", key[len("udf:") :]
    return "static", key


# ── code dictionaries ────────────────────────────────────────────────────────


class CodeDictionaryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field(default="", max_length=4000)
    color_band: bool = True
    sort_order: int = Field(default=0, ge=0, le=100000)


class CodeDictionaryPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    color_band: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=100000)


class CodeDictionaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID | None = None
    is_library: bool = False
    name: str
    description: str = ""
    color_band: bool = True
    sort_order: int = 0


# ── code values ──────────────────────────────────────────────────────────────


class CodeValueCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., min_length=1, max_length=100)
    label: str = Field(default="", max_length=255)
    color: str = Field(default="", max_length=20)
    parent_id: uuid.UUID | None = None
    sort_order: int = Field(default=0, ge=0, le=100000)


class CodeValuePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str | None = Field(default=None, min_length=1, max_length=100)
    label: str | None = Field(default=None, max_length=255)
    color: str | None = Field(default=None, max_length=20)
    sort_order: int | None = Field(default=None, ge=0, le=100000)


class CodeValueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dictionary_id: uuid.UUID
    parent_id: uuid.UUID | None = None
    code: str
    label: str = ""
    color: str = ""
    depth: int = 0
    sort_order: int = 0


# ── per-activity code assignments ─────────────────────────────────────────────


class CodeAssignmentItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dictionary_id: uuid.UUID
    value_id: uuid.UUID


class ActivityCodesSet(BaseModel):
    """Idempotent upsert of an activity's code values (one per dictionary)."""

    model_config = ConfigDict(extra="forbid")

    assignments: list[CodeAssignmentItem] = Field(default_factory=list)


class BulkAssignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dictionary_id: uuid.UUID
    value_id: uuid.UUID
    activity_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=20000)


class CodeAssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dictionary_id: uuid.UUID
    value_id: uuid.UUID
    code: str = ""
    label: str = ""


class BulkAssignResponse(BaseModel):
    assigned: int


# ── user-defined fields ───────────────────────────────────────────────────────


class UdfCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(..., pattern=r"^[a-z][a-z0-9_]*$", max_length=64)
    label: str = Field(default="", max_length=255)
    value_type: Literal["text", "number", "date", "bool", "enum"] = "text"
    enum_values: list[str] = Field(default_factory=list)
    sort_order: int = Field(default=0, ge=0, le=100000)

    @field_validator("enum_values")
    @classmethod
    def _cap_enum(cls, v: list[str]) -> list[str]:
        if len(v) > 500:
            raise ValueError("enum_values too long")
        return v


class UdfPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, max_length=255)
    enum_values: list[str] | None = None
    sort_order: int | None = Field(default=None, ge=0, le=100000)


class UdfResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    key: str
    label: str = ""
    value_type: str = "text"
    enum_values: list[str] = Field(default_factory=list)
    sort_order: int = 0


class UdfValueItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    udf_id: uuid.UUID
    # The raw value; coerced + validated against the UDF's value_type in the
    # service (the type is only known once the UDF is loaded).
    value: Any = None


class ActivityUdfValuesSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    values: list[UdfValueItem] = Field(default_factory=list)


class UdfValueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    udf_id: uuid.UUID
    value_type: str = "text"
    value: Any = None


class ImportLibraryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    library_dictionary_id: uuid.UUID


# ── saved layouts ─────────────────────────────────────────────────────────────


class LayoutColumn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(..., max_length=128)
    width: int | None = Field(default=None, ge=20, le=2000)

    @field_validator("key")
    @classmethod
    def _validate_key(cls, v: str) -> str:
        if not LAYOUT_KEY_RE.match(v):
            raise ValueError(f"Invalid layout column key {v!r}")
        return v


class LayoutGroupBy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(..., max_length=128)
    color_band: bool = True

    @field_validator("key")
    @classmethod
    def _validate_key(cls, v: str) -> str:
        if not LAYOUT_KEY_RE.match(v):
            raise ValueError(f"Invalid layout group_by key {v!r}")
        return v


class CodeFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dictionary_id: uuid.UUID
    value_ids: list[uuid.UUID] = Field(default_factory=list, max_length=2000)


class UdfFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    udf_id: uuid.UUID
    op: Literal["eq", "neq", "lt", "lte", "gt", "gte", "contains", "is_null", "not_null"] = "eq"
    value: Any = None


class BarStyle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    by: Literal["status", "code", "critical", "none"] = "status"
    show_critical: bool = True
    show_baseline: bool = False


class LayoutSpec(BaseModel):
    """The rich saved-layout spec. ``extra='forbid'``; re-validated every R/W."""

    model_config = ConfigDict(extra="forbid")

    columns: list[LayoutColumn] = Field(default_factory=list)
    group_by: list[LayoutGroupBy] = Field(default_factory=list)
    sort: list[SortSpec] = Field(default_factory=list)
    filter: FilterSpec = Field(default_factory=FilterSpec)
    code_filter: list[CodeFilter] = Field(default_factory=list)
    udf_filter: list[UdfFilter] = Field(default_factory=list)
    timescale: Literal["day", "week", "month", "quarter", "year"] = "week"
    bar_style: BarStyle = Field(default_factory=BarStyle)

    @field_validator("columns")
    @classmethod
    def _cap_columns(cls, v: list[LayoutColumn]) -> list[LayoutColumn]:
        if len(v) > MAX_LAYOUT_COLUMNS:
            raise ValueError(f"Too many columns: {len(v)} > {MAX_LAYOUT_COLUMNS}")
        return v

    @field_validator("group_by")
    @classmethod
    def _cap_group_by(cls, v: list[LayoutGroupBy]) -> list[LayoutGroupBy]:
        if len(v) > MAX_LAYOUT_GROUP_BY:
            raise ValueError(f"Too many group_by levels: {len(v)} > {MAX_LAYOUT_GROUP_BY}")
        return v


class LayoutCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=255)
    share_scope: Literal["private", "project", "workspace"] = "private"
    is_default: bool = False
    spec: LayoutSpec = Field(default_factory=LayoutSpec)


class LayoutPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    share_scope: Literal["private", "project", "workspace"] | None = None
    is_default: bool | None = None
    spec: LayoutSpec | None = None


class LayoutResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    schedule_id: uuid.UUID
    project_id: uuid.UUID | None = None
    name: str
    share_scope: str = "private"
    is_default: bool = False
    spec: dict = Field(default_factory=dict)


# ── grouped grid ──────────────────────────────────────────────────────────────


class GroupedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layout_id: uuid.UUID | None = None
    spec: LayoutSpec | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=100, ge=1, le=1000)
    expanded_groups: list[str] = Field(default_factory=list, max_length=5000)


class GroupBand(BaseModel):
    key: str
    label: str = ""
    color: str = ""
    depth: int = 0
    count: int = 0
    path: list[str] = Field(default_factory=list)


class GroupedRow(BaseModel):
    id: uuid.UUID
    name: str
    wbs_code: str = ""
    start_date: str | None = None
    end_date: str | None = None
    duration_days: int = 0
    progress_pct: float = 0.0
    status: str = ""
    total_float: int | None = None
    is_critical: bool = False
    group_path: list[str] = Field(default_factory=list)
    codes: list[CodeAssignmentResponse] = Field(default_factory=list)
    udf_values: list[UdfValueResponse] = Field(default_factory=list)


class GroupedResponse(BaseModel):
    groups: list[GroupBand] = Field(default_factory=list)
    rows: list[GroupedRow] = Field(default_factory=list)
    page: int = 1
    page_size: int = 100
    total_estimate: int = 0

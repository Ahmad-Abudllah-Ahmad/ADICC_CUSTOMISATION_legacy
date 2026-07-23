# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Export a schedule to Microsoft Project XML (MSPDI).

Pure builder: it takes plain activity / predecessor records and returns an
MSPDI XML string. No database, no ORM, no FastAPI - so it is unit-testable on
any Python and round-trips with the importer in ``router.import_msp_xml``
(same 8h working day, same constraint and relationship code maps, same lag
unit of tenths-of-a-minute).

The document carries the standard MSP default namespace
``http://schemas.microsoft.com/project`` so Microsoft Project, the importer
here, and other MSPDI-aware tools all read it back.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from xml.etree.ElementTree import Element, SubElement, tostring

MSP_NS = "http://schemas.microsoft.com/project"

# Hours in an MSP working day. Mirrors ``_parse_msp_duration_to_days``.
HOURS_PER_DAY = 8
# MSP stores durations/lags in tenths of a minute. One 8h day is therefore
# 8 * 60 * 10 = 4800 tenths-of-a-minute.
_TENTHS_PER_DAY = HOURS_PER_DAY * 60 * 10

# Our constraint enum -> MSP ConstraintType code (reverse of the import map).
_CONSTRAINT_TO_MSP: dict[str, str] = {
    "as_soon_as_possible": "0",
    "must_start_on": "1",
    "must_finish_on": "2",
    "start_no_earlier": "3",
    "start_no_later": "4",
    "finish_no_earlier": "5",
    "finish_no_later": "6",
    "as_late_as_possible": "7",
}
# Our relationship type -> MSP link Type code (reverse of the import map).
_REL_TO_MSP: dict[str, str] = {"FF": "0", "FS": "1", "SF": "2", "SS": "3"}


@dataclass
class MspdiActivity:
    """One task in the export, already mapped to integer MSP UIDs."""

    uid: int
    name: str
    start_date: str  # YYYY-MM-DD (or ISO datetime; only the date is used)
    end_date: str
    duration_days: int
    progress_pct: float = 0.0
    activity_type: str = "task"  # task | milestone | summary
    wbs_code: str = ""
    outline_level: int = 1
    constraint_type: str | None = None
    constraint_date: str | None = None


@dataclass
class MspdiPredecessor:
    """A predecessor link pointing at an earlier task's UID."""

    predecessor_uid: int
    relationship_type: str = "FS"
    lag_days: int = 0


@dataclass
class MspdiProject:
    """The whole export payload."""

    name: str
    activities: Sequence[MspdiActivity] = field(default_factory=list)
    # successor UID -> its predecessor links.
    predecessors_by_uid: Mapping[int, Sequence[MspdiPredecessor]] = field(default_factory=dict)


def _msp_datetime(date_str: str, hour: int) -> str:
    """Normalise a ``YYYY-MM-DD`` (or ISO datetime) to MSP ``...T08:00:00``."""
    day = (date_str or "")[:10]
    if not day:
        return ""
    return f"{day}T{hour:02d}:00:00"


def _msp_duration(duration_days: int) -> str:
    """Render whole days as an MSP ISO-8601 duration at 8h/day."""
    hours = max(0, int(duration_days)) * HOURS_PER_DAY
    return f"PT{hours}H0M0S"


def _percent(progress_pct: float) -> str:
    try:
        pct = round(float(progress_pct))
    except (TypeError, ValueError):
        pct = 0
    return str(max(0, min(100, pct)))


def build_mspdi_xml(project: MspdiProject) -> str:
    """Build an MSPDI XML document string from a project payload."""
    root = Element("Project")
    # Default namespace as a literal attribute - re-parsing applies it to every
    # unprefixed child, which is exactly what MSP-aware readers expect.
    root.set("xmlns", MSP_NS)
    SubElement(root, "Name").text = project.name or "Schedule"
    SubElement(root, "Title").text = project.name or "Schedule"
    # Minutes-based duration math; 7 == "days" display format in MSP.
    SubElement(root, "DurationFormat").text = "7"

    tasks_el = SubElement(root, "Tasks")
    for order, act in enumerate(project.activities, start=1):
        task_el = SubElement(tasks_el, "Task")
        SubElement(task_el, "UID").text = str(act.uid)
        SubElement(task_el, "ID").text = str(order)
        SubElement(task_el, "Name").text = act.name or ""
        SubElement(task_el, "OutlineLevel").text = str(max(1, act.outline_level))
        if act.wbs_code:
            SubElement(task_el, "WBS").text = act.wbs_code
        is_milestone = act.activity_type == "milestone" or act.duration_days <= 0
        is_summary = act.activity_type == "summary"
        SubElement(task_el, "Type").text = "1"  # fixed duration
        SubElement(task_el, "Start").text = _msp_datetime(act.start_date, 8)
        SubElement(task_el, "Finish").text = _msp_datetime(act.end_date, 17)
        SubElement(task_el, "Duration").text = _msp_duration(act.duration_days)
        SubElement(task_el, "DurationFormat").text = "7"
        SubElement(task_el, "PercentComplete").text = _percent(act.progress_pct)
        SubElement(task_el, "Milestone").text = "1" if is_milestone else "0"
        SubElement(task_el, "Summary").text = "1" if is_summary else "0"

        msp_constraint = _CONSTRAINT_TO_MSP.get(act.constraint_type or "")
        if msp_constraint is not None:
            SubElement(task_el, "ConstraintType").text = msp_constraint
            if act.constraint_date:
                SubElement(task_el, "ConstraintDate").text = _msp_datetime(act.constraint_date, 8)

        for link in project.predecessors_by_uid.get(act.uid, []):
            link_el = SubElement(task_el, "PredecessorLink")
            SubElement(link_el, "PredecessorUID").text = str(link.predecessor_uid)
            SubElement(link_el, "Type").text = _REL_TO_MSP.get(link.relationship_type, "1")
            SubElement(link_el, "LinkLag").text = str(int(link.lag_days) * _TENTHS_PER_DAY)
            SubElement(link_el, "LagFormat").text = "7"

    body = tostring(root, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + body

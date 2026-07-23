# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Defensive date parsing/normalisation for the safety module.

``SafetyIncident.incident_date`` is stored as a ``String`` column (no schema
migration is in scope to change that). The API layer enforces a strict
``YYYY-MM-DD`` pattern, but direct service callers, importers (GAEB/Excel),
and legacy rows can still introduce non-canonical strings.

A *wrong* safety number is dangerous: if a malformed stored date were silently
dropped from the "days without incident / LTI" computation, a project with a
real recent incident could falsely read as "no incidents" (reassuring blank)
or a huge "all good" number. These helpers therefore:

* parse the canonical ISO form *and* a small set of unambiguous fallbacks;
* report unparseable values to the caller (so the metric can fail safe toward
  "cannot confirm" instead of a falsely-reassuring value);
* canonicalise on write so future rows are always clean ISO ``YYYY-MM-DD``.
"""

from __future__ import annotations

from datetime import date, datetime

# Accepted fallback formats, ordered most- to least-specific. Only formats
# whose field order is unambiguous are included - e.g. ``DD/MM/YYYY`` and
# ``MM/DD/YYYY`` are mutually ambiguous, so neither slash form is guessed;
# such values are reported as unparseable rather than silently mis-dated
# (a mis-dated incident is as dangerous as a dropped one).
_FALLBACK_FORMATS: tuple[str, ...] = (
    "%Y-%m-%d",  # canonical ISO (also handled by date.fromisoformat)
    "%Y/%m/%d",  # ISO order, slash separator - unambiguous
    "%d.%m.%Y",  # DACH / EU dotted - unambiguous (day-first, 4-digit year last)
    "%Y.%m.%d",  # ISO order, dot separator - unambiguous
    "%Y%m%d",  # compact ISO basic
)


def parse_incident_date(value: str | None) -> date | None:
    """Best-effort parse of a stored incident-date string.

    Returns a ``date`` on success, or ``None`` if the value is empty or
    cannot be parsed unambiguously. ``None`` is *cannot confirm*, never
    *no incident* - callers must treat it as a reason to flag the metric,
    not silently drop the incident.
    """
    if not value:
        return None
    text = value.strip()
    if not text:
        return None

    # Fast path: full ISO date or ISO datetime ("2026-04-10T08:15:00+00:00").
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        pass

    for fmt in _FALLBACK_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()  # noqa: DTZ007
        except ValueError:
            continue
    return None


def canonicalize_incident_date(value: str | None) -> str:
    """Normalise a date string to canonical ISO ``YYYY-MM-DD`` for storage.

    Guarantees future rows are clean so the "days without incident / LTI"
    billboard never has to guess. If the value cannot be parsed it is
    returned **unchanged** (trimmed) rather than dropped - the integrity
    failure must remain visible downstream, not be silently erased.
    """
    parsed = parse_incident_date(value)
    if parsed is not None:
        return parsed.isoformat()
    return (value or "").strip()

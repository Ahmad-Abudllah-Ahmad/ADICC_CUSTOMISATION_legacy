// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Local-date helpers — strictly use the viewer's local calendar fields,
 * NEVER ``new Date().toISOString().slice(0,10)`` (that returns the UTC
 * day, which drifts the highlighted "today" / the "today" query by ±1 for
 * any user away from UTC near midnight).
 *
 * Used by daily-diary and field-reports pages so the calendar grid and
 * the "today" marker / submit timestamp always agree on the local day.
 */

/**
 * Return today's date in ``YYYY-MM-DD`` form using the LOCAL calendar.
 *
 * Equivalent to ``isoDate(now.getFullYear(), now.getMonth(), now.getDate())``.
 */
export function todayLocalISO(now: Date = new Date()): string {
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, '0');
  const d = String(now.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

/**
 * Build a ``YYYY-MM-DD`` string from explicit local calendar fields.
 *
 * ``month`` is 0-based to match ``Date.getMonth()``.
 */
export function isoDateFromLocal(year: number, month: number, day: number): string {
  return `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

/**
 * Return ``now`` as an ISO-8601 timestamp anchored to the LOCAL timezone
 * (i.e. with the local UTC offset suffix, NOT ``Z``).
 *
 * Use this for ``entry_time`` / event timestamps whose owning record's
 * ``*_date`` field is a local ``YYYY-MM-DD`` — using ``toISOString()`` there
 * silently converts the timestamp to UTC, so a diary dated 2026-05-20 in
 * Berlin could carry an ``entry_time`` of 2026-05-21T00:30:00Z for an entry
 * created at 2026-05-21T02:30:00+02:00. The backend stores the timestamp
 * verbatim with timezone, so downstream readers see the correct local day.
 *
 * Example output: ``2026-05-20T23:45:30+02:00``
 */
export function nowLocalISO(now: Date = new Date()): string {
  const y = now.getFullYear();
  const mo = String(now.getMonth() + 1).padStart(2, '0');
  const d = String(now.getDate()).padStart(2, '0');
  const h = String(now.getHours()).padStart(2, '0');
  const mi = String(now.getMinutes()).padStart(2, '0');
  const s = String(now.getSeconds()).padStart(2, '0');
  const ms = String(now.getMilliseconds()).padStart(3, '0');

  // getTimezoneOffset() returns minutes WEST of UTC (positive = behind UTC),
  // so a Berlin client in CEST (UTC+2) returns -120. ISO-8601 expects the
  // opposite sign convention (UTC+2 → "+02:00").
  const offsetMin = -now.getTimezoneOffset();
  const sign = offsetMin >= 0 ? '+' : '-';
  const abs = Math.abs(offsetMin);
  const oh = String(Math.floor(abs / 60)).padStart(2, '0');
  const om = String(abs % 60).padStart(2, '0');

  return `${y}-${mo}-${d}T${h}:${mi}:${s}.${ms}${sign}${oh}:${om}`;
}

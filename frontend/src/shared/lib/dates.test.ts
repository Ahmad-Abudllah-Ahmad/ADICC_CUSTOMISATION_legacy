/**
 * Anti-regression for the local-date helpers used by daily-diary and
 * field-reports. The whole point of these helpers is that they DO NOT
 * follow ``new Date().toISOString().slice(0,10)`` — that returns the UTC
 * day, which drifts ±1 vs the local calendar near midnight for any user
 * away from UTC.
 *
 * The tests fake the system clock so the assertions are timezone-agnostic
 * (they pin behaviour relative to the local fields the runtime exposes).
 */
import { describe, it, expect } from 'vitest';
import { todayLocalISO, isoDateFromLocal, nowLocalISO } from './dates';

describe('todayLocalISO', () => {
  it('uses local calendar fields, not UTC slice', () => {
    // Pick a Date whose local-day and UTC-day can differ: 2026-05-20
    // 23:30 LOCAL. Whatever the test runner's TZ is, the assertion must
    // match the local getFullYear/getMonth/getDate trio — never the UTC
    // slice (which would shift to 2026-05-21 in any tz east of UTC).
    const d = new Date(2026, 4, 20, 23, 30, 0); // month is 0-based → May
    expect(todayLocalISO(d)).toBe('2026-05-20');
  });

  it('zero-pads month and day', () => {
    const d = new Date(2026, 0, 5, 12, 0, 0); // 2026-01-05 local
    expect(todayLocalISO(d)).toBe('2026-01-05');
  });

  it('default arg uses real "now" and returns a YYYY-MM-DD string', () => {
    const s = todayLocalISO();
    expect(s).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});

describe('isoDateFromLocal', () => {
  it('formats from 0-based month', () => {
    expect(isoDateFromLocal(2026, 11, 31)).toBe('2026-12-31');
    expect(isoDateFromLocal(2026, 0, 1)).toBe('2026-01-01');
  });
});

describe('nowLocalISO', () => {
  it('emits a full ISO timestamp with TZ offset suffix (not Z)', () => {
    const d = new Date(2026, 4, 20, 23, 45, 30, 0);
    const s = nowLocalISO(d);
    // Shape: 2026-05-20T23:45:30.000+HH:MM or -HH:MM — never "Z".
    expect(s).toMatch(/^2026-05-20T23:45:30\.000[+-]\d{2}:\d{2}$/);
    expect(s.endsWith('Z')).toBe(false);
  });

  it('local-date portion of nowLocalISO matches todayLocalISO for the same Date', () => {
    const d = new Date(2026, 4, 20, 23, 59, 59, 0);
    expect(nowLocalISO(d).slice(0, 10)).toBe(todayLocalISO(d));
  });
});

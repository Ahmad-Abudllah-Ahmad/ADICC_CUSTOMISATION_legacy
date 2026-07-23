// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// errorLogger contract tests — focused on the bug-report flow.
//
// Background: GitHub issue #115 was filed because a benign 404 from
// the BIM auto-detect path got captured as the "last error" by the
// in-app bug-report dialog. The page handled the 404 gracefully via
// toast, but the warning entry still leaked into the report template.
//
// `getLastError()` now prefers the most recent level=error entry over
// warning-level noise. These tests lock that contract in.

import { describe, it, expect, beforeEach } from 'vitest';
import {
  getLastError,
  logApiError,
  logError,
  clearErrorLog,
  getErrorLog,
  shouldSuppress,
  isLastErrorNetworkOnly,
  isNetworkErrorMessage,
  isTransientHttpStatus,
} from './errorLogger';

describe('errorLogger.getLastError - bug-report payload selection', () => {
  beforeEach(() => {
    clearErrorLog();
  });

  it('returns null when nothing has been logged', () => {
    expect(getLastError()).toBeNull();
  });

  it('returns the most recent entry when only warnings exist', () => {
    logApiError('/v1/foo/', 404, 'not found');
    logApiError('/v1/bar/', 404, 'not found');
    const last = getLastError();
    expect(last).not.toBeNull();
    expect(last!.message).toContain('/v1/bar/');
  });

  it('prefers a level=error entry over a more recent warning', () => {
    // 500 → level=error
    logApiError('/v1/important/', 500, 'oops');
    // 404 → level=warning, but the 500 was the real problem
    logApiError('/v1/bim_hub/abc-123/', 404, 'not found');
    const last = getLastError();
    expect(last!.message).toContain('/v1/important/');
    expect(last!.message).not.toContain('/v1/bim_hub/');
  });

  it('falls back to most recent warning when no error exists in the window', () => {
    logApiError('/v1/some/', 404, 'not found');
    const last = getLastError();
    expect(last!.message).toContain('/v1/some/');
  });
});

// ─────────────────────────────────────────────────────────────────────────
// Recording whitelist — observability noise filters
//
// Source defect: user error log openconstructionerp-log-2026-05-22.json
// captured 50 of 64 errors as the same handled /profile 404 plus a
// handful of converter-install AbortErrors. None of those are
// actionable — they spam the bug-report buffer and bury the real
// errors. The whitelist drops them at recording time.

describe('errorLogger recording whitelist', () => {
  beforeEach(() => {
    clearErrorLog();
  });

  it('drops /v1/projects/{uuid}/profile 404 (handled by backend retrofit)', () => {
    logApiError(
      '/v1/projects/0e92b341-7af3-4d4c-bd2c-a6f7a8f01234/profile',
      404,
      'no setup profile yet',
    );
    expect(getErrorLog()).toHaveLength(0);
    expect(getLastError()).toBeNull();
  });

  it('drops /v1/bim_hub/* 404 (user navigated to a deleted model)', () => {
    logApiError(
      '/v1/bim_hub/models/0e92b341-7af3-4d4c-bd2c-a6f7a8f01234/elements',
      404,
      'model not found',
    );
    expect(getErrorLog()).toHaveLength(0);
  });

  it('drops AbortError from POST /v1/takeoff/converters/{id}/install', () => {
    const e = new Error('aborted');
    e.name = 'AbortError';
    logError(e, 'api_error', {
      url: '/v1/takeoff/converters/rvt/install/',
    });
    expect(getErrorLog()).toHaveLength(0);
  });

  it('drops 422 on /v1/crm/opportunities with the stale oversized limit', () => {
    logApiError(
      '/v1/crm/opportunities/?limit=500',
      422,
      'Input should be less than or equal to 200',
    );
    expect(getErrorLog()).toHaveLength(0);
  });

  it('drops 422 on /v1/users with the stale oversized limit', () => {
    logApiError(
      '/v1/users/?limit=200',
      422,
      'Input should be less than or equal to 100',
    );
    expect(getErrorLog()).toHaveLength(0);
  });

  it('does NOT suppress unrelated 404s on the same modules', () => {
    // A genuine 404 on /v1/projects/{id}/boqs/ is unrelated to the
    // profile-retrofit issue — must still be recorded.
    logApiError(
      '/v1/projects/0e92b341-7af3-4d4c-bd2c-a6f7a8f01234/boqs/',
      404,
      'boq not found',
    );
    expect(getErrorLog().length).toBeGreaterThanOrEqual(1);
  });

  it('does NOT suppress 500 on /v1/projects/{id}/profile (real failure)', () => {
    // A 500 on the profile endpoint is a real bug — must surface.
    logApiError(
      '/v1/projects/0e92b341-7af3-4d4c-bd2c-a6f7a8f01234/profile',
      500,
      'oops',
    );
    expect(getErrorLog().length).toBeGreaterThanOrEqual(1);
  });

  it('shouldSuppress predicate handles each whitelist field independently', () => {
    // Path-only whitelist hit (any status counts → bim_hub 404).
    expect(shouldSuppress({ path: '/v1/bim_hub/x', status: 404 })).toBe(true);
    // Path matches but status doesn't (we whitelisted only 404 → 500
    // must still pass through).
    expect(
      shouldSuppress({
        path: '/v1/projects/00000000-0000-0000-0000-000000000000/profile',
        status: 500,
      }),
    ).toBe(false);
    // errorName predicate requires the right name.
    expect(
      shouldSuppress({
        path: '/v1/takeoff/converters/rvt/install/',
        errorName: 'AbortError',
      }),
    ).toBe(true);
    expect(
      shouldSuppress({
        path: '/v1/takeoff/converters/rvt/install/',
        errorName: 'TypeError',
      }),
    ).toBe(false);
    // Empty input never matches.
    expect(shouldSuppress({})).toBe(false);
  });
});

// ─────────────────────────────────────────────────────────────────────────
// Network-blip filter — GitHub issue #155
//
// User Mourdi59 filed "Failed to fetch" TypeError from a SettingsPage
// React Query function while the backend was simply not running. That's
// not a code defect — getLastError() must skip transport-level blips
// (Failed to fetch / NetworkError / Load failed / AbortError / 0 /
// 502 / 503 / 504) when picking the representative error for the
// auto-bug-report payload.

describe('errorLogger network-blip filter (#155)', () => {
  beforeEach(() => {
    clearErrorLog();
  });

  it('isNetworkErrorMessage matches all browser dialects', () => {
    // Chrome / Edge
    expect(isNetworkErrorMessage('TypeError: Failed to fetch')).toBe(true);
    expect(isNetworkErrorMessage('Failed to fetch')).toBe(true);
    // Firefox
    expect(
      isNetworkErrorMessage(
        'TypeError: NetworkError when attempting to fetch resource.',
      ),
    ).toBe(true);
    // Safari
    expect(isNetworkErrorMessage('TypeError: Load failed')).toBe(true);
    expect(isNetworkErrorMessage('Load failed')).toBe(true);
    // AbortController
    expect(
      isNetworkErrorMessage('AbortError: signal is aborted without reason'),
    ).toBe(true);
    expect(
      isNetworkErrorMessage('AbortError: The user aborted a request'),
    ).toBe(true);
    expect(isNetworkErrorMessage('The operation was aborted.')).toBe(true);
    // Real defects must NOT match
    expect(
      isNetworkErrorMessage("TypeError: Cannot read properties of undefined (reading 'id')"),
    ).toBe(false);
    expect(isNetworkErrorMessage('ReferenceError: foo is not defined')).toBe(false);
    expect(isNetworkErrorMessage('SyntaxError: Unexpected token < in JSON at position 0')).toBe(false);
    expect(isNetworkErrorMessage(null)).toBe(false);
    expect(isNetworkErrorMessage('')).toBe(false);
  });

  it('isTransientHttpStatus flags only the documented codes', () => {
    expect(isTransientHttpStatus(0)).toBe(true);
    expect(isTransientHttpStatus(502)).toBe(true);
    expect(isTransientHttpStatus(503)).toBe(true);
    expect(isTransientHttpStatus(504)).toBe(true);
    // Real failures — NOT transient
    expect(isTransientHttpStatus(400)).toBe(false);
    expect(isTransientHttpStatus(401)).toBe(false);
    expect(isTransientHttpStatus(404)).toBe(false);
    expect(isTransientHttpStatus(422)).toBe(false);
    expect(isTransientHttpStatus(500)).toBe(false);
    expect(isTransientHttpStatus(undefined)).toBe(false);
    expect(isTransientHttpStatus(null)).toBe(false);
  });

  it('getLastError skips a "Failed to fetch" blip in favour of a real error', () => {
    // Real defect captured first (e.g. undefined-property read in a
    // BOQ row renderer).
    logError(
      new TypeError("Cannot read properties of undefined (reading 'rows')"),
    );
    // Backend then went down — multiple Failed to fetch errors filed
    // after the real one. The picker must STILL surface the real bug.
    logError(new TypeError('Failed to fetch'), 'network');
    logError(new TypeError('Failed to fetch'), 'network');
    logError(new TypeError('Failed to fetch'), 'network');

    const last = getLastError();
    expect(last).not.toBeNull();
    expect(last!.message).toContain('Cannot read properties of undefined');
    expect(last!.message).not.toContain('Failed to fetch');
  });

  it('getLastError skips a transient 503 in favour of a real 500', () => {
    logApiError('/v1/projects/abc/boqs/', 500, 'internal error');
    logApiError('/v1/projects/abc/boqs/', 503, 'service unavailable');
    logApiError('/v1/projects/abc/boqs/', 503, 'service unavailable');
    const last = getLastError();
    expect(last).not.toBeNull();
    expect(last!.message).toContain('returned 500');
  });

  it('getLastError falls back to a network blip when nothing else is available', () => {
    // Backend-down session — nothing but Failed to fetch. The picker
    // returns the blip (so the report has *something* to show) but the
    // UI calls isLastErrorNetworkOnly() to decide whether to warn.
    logError(new TypeError('Failed to fetch'), 'network');
    const last = getLastError();
    expect(last).not.toBeNull();
    expect(last!.message).toContain('Failed to fetch');
  });

  it('isLastErrorNetworkOnly is false when no errors exist', () => {
    expect(isLastErrorNetworkOnly()).toBe(false);
  });

  it('isLastErrorNetworkOnly is true when all level=error are network blips', () => {
    logError(new TypeError('Failed to fetch'), 'network');
    logApiError('/v1/foo/', 503, 'unavailable');
    expect(isLastErrorNetworkOnly()).toBe(true);
  });

  it('isLastErrorNetworkOnly is false when a real exception is mixed in', () => {
    logError(new ReferenceError('foo is not defined'));
    logError(new TypeError('Failed to fetch'), 'network');
    expect(isLastErrorNetworkOnly()).toBe(false);
  });

  it('isLastErrorNetworkOnly ignores warning-level entries', () => {
    // Warnings (handled 4xx) should not flip the predicate.
    logApiError('/v1/projects/abc/boqs/', 404, 'not found');
    expect(isLastErrorNetworkOnly()).toBe(false);
    // Now add a network blip → all *error*-level entries are blips → true.
    logError(new TypeError('Failed to fetch'), 'network');
    expect(isLastErrorNetworkOnly()).toBe(true);
  });

  it('preserves the user-override escape hatch by still recording blips', () => {
    // The entries themselves must still hit the buffer — the user can
    // still file the report after clicking "Report anyway", and the
    // downloaded JSON log should contain the blips so support can
    // diagnose connectivity issues. We only filter the *picker*.
    logError(new TypeError('Failed to fetch'), 'network');
    logError(new TypeError('Failed to fetch'), 'network');
    expect(getErrorLog().length).toBeGreaterThanOrEqual(2);
  });
});

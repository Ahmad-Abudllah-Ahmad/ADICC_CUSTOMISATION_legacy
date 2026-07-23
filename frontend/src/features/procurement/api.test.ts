// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for the procurement API client URL/param construction.
//
// These clients are thin wrappers, but the URL + query-string assembly is
// real logic: a regression (wrong path, dropped "?" prefix, mis-named
// param, or a falsy option leaking into the query) silently breaks the
// scorecard / match-status / retainage surfaces with no type error. We mock
// the shared fetch helpers and assert the exact URL (and body) each client
// hands them.

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { apiGet, apiPost } from '@/shared/lib/api';

import {
  getPOMatchStatus,
  getSupplierScorecard,
  getVendorEligibility,
  listPORetainageReleases,
  releasePORetainage,
  getRetainageReconciliation,
} from './api';

vi.mock('@/shared/lib/api', () => ({
  apiGet: vi.fn(() => Promise.resolve({})),
  apiPost: vi.fn(() => Promise.resolve({})),
}));

const mockGet = vi.mocked(apiGet);
const mockPost = vi.mocked(apiPost);

beforeEach(() => {
  vi.clearAllMocks();
});

describe('getPOMatchStatus', () => {
  it('GETs the per-PO match-status path', () => {
    getPOMatchStatus('po-123');
    expect(mockGet).toHaveBeenCalledWith('/v1/procurement/po-123/match-status/');
  });
});

describe('getSupplierScorecard', () => {
  it('GETs the bare scorecard path when no options are given (no trailing "?")', () => {
    getSupplierScorecard('contact-1');
    expect(mockGet).toHaveBeenCalledWith(
      '/v1/procurement/suppliers/contact-1/scorecard/',
    );
    // A dangling "?" must not be appended for an empty query.
    const url = mockGet.mock.calls[0]?.[0] as string;
    expect(url.endsWith('?')).toBe(false);
  });

  it('appends project_id when provided', () => {
    getSupplierScorecard('contact-1', { projectId: 'proj-9' });
    expect(mockGet).toHaveBeenCalledWith(
      '/v1/procurement/suppliers/contact-1/scorecard/?project_id=proj-9',
    );
  });

  it('appends period_days when provided', () => {
    getSupplierScorecard('contact-1', { periodDays: 90 });
    expect(mockGet).toHaveBeenCalledWith(
      '/v1/procurement/suppliers/contact-1/scorecard/?period_days=90',
    );
  });

  it('appends both params in order when both are provided', () => {
    getSupplierScorecard('contact-1', { projectId: 'proj-9', periodDays: 30 });
    expect(mockGet).toHaveBeenCalledWith(
      '/v1/procurement/suppliers/contact-1/scorecard/?project_id=proj-9&period_days=30',
    );
  });

  it('does not leak a zero periodDays into the query (falsy guard)', () => {
    // periodDays: 0 is falsy, so the client intentionally omits it and lets
    // the backend default (365) apply rather than sending period_days=0.
    getSupplierScorecard('contact-1', { periodDays: 0 });
    expect(mockGet).toHaveBeenCalledWith(
      '/v1/procurement/suppliers/contact-1/scorecard/',
    );
  });
});

describe('getVendorEligibility', () => {
  it('GETs the subcontractors vendor-by-contact eligibility path', () => {
    getVendorEligibility('contact-7');
    expect(mockGet).toHaveBeenCalledWith(
      '/v1/subcontractors/vendors/by-contact/contact-7/eligibility',
    );
  });
});

describe('listPORetainageReleases', () => {
  it('GETs the retainage-releases log path for the PO', () => {
    listPORetainageReleases('po-5');
    expect(mockGet).toHaveBeenCalledWith(
      '/v1/procurement/po-5/retainage-releases/',
    );
  });
});

describe('releasePORetainage', () => {
  it('POSTs the release-retainage path with the amount/reason body', () => {
    const body = { amount: '500.00', reason: 'milestone 1' };
    releasePORetainage('po-5', body);
    expect(mockPost).toHaveBeenCalledWith(
      '/v1/procurement/po-5/release-retainage/',
      body,
    );
  });

  it('forwards a body without a reason unchanged', () => {
    const body = { amount: '100' };
    releasePORetainage('po-5', body);
    expect(mockPost).toHaveBeenCalledWith(
      '/v1/procurement/po-5/release-retainage/',
      body,
    );
  });
});

describe('getRetainageReconciliation', () => {
  it('GETs the reporting endpoint with all three required params', () => {
    getRetainageReconciliation({
      projectId: 'proj-1',
      periodStart: '2026-01-01',
      periodEnd: '2026-12-31',
    });
    expect(mockGet).toHaveBeenCalledWith(
      '/v1/reporting/po-retainage-reconciliation/?project_id=proj-1&period_start=2026-01-01&period_end=2026-12-31',
    );
  });
});

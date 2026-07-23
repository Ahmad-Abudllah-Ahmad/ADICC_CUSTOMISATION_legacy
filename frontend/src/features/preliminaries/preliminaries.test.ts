// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for the preliminaries API client URL/param construction and the pure
// preview math (client-side live line totals and the per-category roll-up).
//
// The URL assembly is real logic: a wrong path or a dropped trailing slash
// silently breaks the estimator with no type error. The preview math must mirror
// the backend Decimal formula so the live subtotals a user sees while typing
// agree with what the server stores.

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { apiGet, apiPost, apiPatch, apiDelete } from '@/shared/lib/api';

import {
  fetchPrelimItems,
  createPrelimItem,
  updatePrelimItem,
  deletePrelimItem,
  fetchPreliminariesSummary,
  fetchStarterChecklist,
  previewLineTotal,
  previewRollup,
  type PrelimLineLike,
} from './api';

vi.mock('@/shared/lib/api', () => ({
  apiGet: vi.fn(() => Promise.resolve({ items: [] })),
  apiPost: vi.fn(() => Promise.resolve({})),
  apiPatch: vi.fn(() => Promise.resolve({})),
  apiDelete: vi.fn(() => Promise.resolve(undefined)),
}));

const mockGet = vi.mocked(apiGet);
const mockPost = vi.mocked(apiPost);
const mockPatch = vi.mocked(apiPatch);
const mockDelete = vi.mocked(apiDelete);

beforeEach(() => {
  vi.clearAllMocks();
});

/* ── URL construction ──────────────────────────────────────────────────── */

describe('preliminaries api URLs', () => {
  it('lists items scoped to a project', () => {
    fetchPrelimItems('proj-1');
    expect(mockGet).toHaveBeenCalledWith('/v1/preliminaries/items/?project_id=proj-1');
  });

  it('encodes the project id in the list query', () => {
    fetchPrelimItems('a b/c');
    expect(mockGet).toHaveBeenCalledWith('/v1/preliminaries/items/?project_id=a%20b%2Fc');
  });

  it('creates an item at the items collection', () => {
    const body = { project_id: 'proj-1', label: 'Site office', item_type: 'time_related' as const };
    createPrelimItem(body);
    expect(mockPost).toHaveBeenCalledWith('/v1/preliminaries/items/', body);
  });

  it('updates an item by id with a trailing slash', () => {
    const body = { rate_per_period: '3500.00' };
    updatePrelimItem('item-9', body);
    expect(mockPatch).toHaveBeenCalledWith('/v1/preliminaries/items/item-9/', body);
  });

  it('deletes an item by id with a trailing slash', () => {
    deletePrelimItem('item-9');
    expect(mockDelete).toHaveBeenCalledWith('/v1/preliminaries/items/item-9/');
  });

  it('fetches the per-project summary', () => {
    fetchPreliminariesSummary('proj-1');
    expect(mockGet).toHaveBeenCalledWith('/v1/preliminaries/projects/proj-1/summary/');
  });

  it('fetches the starter checklist and unwraps items', async () => {
    mockGet.mockResolvedValueOnce({
      items: [{ label: 'Site office', category: 'site_establishment', item_type: 'time_related' }],
    });
    const items = await fetchStarterChecklist();
    expect(mockGet).toHaveBeenCalledWith('/v1/preliminaries/starter-checklist/');
    expect(items).toHaveLength(1);
    expect(items[0]?.label).toBe('Site office');
  });
});

/* ── Preview line total ────────────────────────────────────────────────── */

describe('previewLineTotal', () => {
  it('prices a time-related line as rate * periods', () => {
    expect(previewLineTotal({ item_type: 'time_related', rate_per_period: '3500.00', periods: '12' })).toBe(42000);
  });

  it('supports fractional periods', () => {
    expect(previewLineTotal({ item_type: 'time_related', rate_per_period: '800', periods: '12.5' })).toBe(10000);
  });

  it('prices a fixed line as fixed_amount and ignores rate/periods', () => {
    expect(
      previewLineTotal({ item_type: 'fixed', fixed_amount: '15000', rate_per_period: '999', periods: '9' }),
    ).toBe(15000);
  });

  it('defaults to time-related when the type is omitted', () => {
    expect(previewLineTotal({ rate_per_period: '10', periods: '3' })).toBe(30);
  });

  it('treats blank / non-numeric input as zero', () => {
    expect(previewLineTotal({ item_type: 'time_related', rate_per_period: '', periods: '' })).toBe(0);
    expect(previewLineTotal({ item_type: 'fixed', fixed_amount: 'abc' })).toBe(0);
  });

  it('rounds the line to the cent', () => {
    // 100.005 * 1 rounds to 100.01 (half-up, non-negative amounts).
    expect(previewLineTotal({ item_type: 'time_related', rate_per_period: '100.005', periods: '1' })).toBe(100.01);
  });
});

/* ── Preview roll-up ───────────────────────────────────────────────────── */

describe('previewRollup', () => {
  const items: PrelimLineLike[] = [
    { category: 'site_staff', item_type: 'time_related', rate_per_period: '5000', periods: '10' },
    { category: 'site_staff', item_type: 'time_related', rate_per_period: '4000', periods: '10' },
    { category: 'site_establishment', item_type: 'fixed', fixed_amount: '20000' },
    { category: 'site_establishment', item_type: 'time_related', rate_per_period: '1500', periods: '10' },
  ];

  it('splits time-related and fixed per category and totals them', () => {
    const rollup = previewRollup(items);
    expect(rollup.categories.map((c) => c.category)).toEqual(['site_establishment', 'site_staff']);

    const establishment = rollup.categories[0]!;
    expect(establishment.timeRelatedTotal).toBe(15000);
    expect(establishment.fixedTotal).toBe(20000);
    expect(establishment.total).toBe(35000);
    expect(establishment.itemCount).toBe(2);

    const staff = rollup.categories[1]!;
    expect(staff.timeRelatedTotal).toBe(90000);
    expect(staff.fixedTotal).toBe(0);
    expect(staff.itemCount).toBe(2);
  });

  it('reports the grand total split into time-related and fixed', () => {
    const rollup = previewRollup(items);
    expect(rollup.timeRelatedTotal).toBe(105000);
    expect(rollup.fixedTotal).toBe(20000);
    expect(rollup.grandTotal).toBe(125000);
    expect(rollup.itemCount).toBe(4);
  });

  it('keeps the grand total equal to the sum of category totals', () => {
    const rollup = previewRollup(items);
    const sum = rollup.categories.reduce((acc, c) => acc + c.total, 0);
    expect(sum).toBe(rollup.grandTotal);
  });

  it('does not drift on values that are awkward in floating point', () => {
    // 0.1 + 0.2 style values summed in cents must stay exact.
    const rollup = previewRollup([
      { category: 'general', item_type: 'fixed', fixed_amount: '0.10' },
      { category: 'general', item_type: 'fixed', fixed_amount: '0.20' },
    ]);
    expect(rollup.grandTotal).toBe(0.3);
  });

  it('rolls a blank category into general', () => {
    const rollup = previewRollup([{ item_type: 'fixed', fixed_amount: '10' }]);
    expect(rollup.categories.map((c) => c.category)).toEqual(['general']);
    expect(rollup.grandTotal).toBe(10);
  });

  it('is all-zero for an empty list', () => {
    const rollup = previewRollup([]);
    expect(rollup.categories).toEqual([]);
    expect(rollup.grandTotal).toBe(0);
    expect(rollup.itemCount).toBe(0);
  });
});

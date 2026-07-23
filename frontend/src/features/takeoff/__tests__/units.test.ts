// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * D-TKC-021: takeoff → BOQ unit canonicalization.
 *
 * German / EU / raw-OCR unit strings (Stück, lfm, m³, psch, '') must be
 * mapped to the canonical BOQ vocabulary before they become a BOQ
 * position unit, otherwise downstream validation / cost matching /
 * bim_hub quantity sync never sees the row.
 */
import { describe, it, expect } from 'vitest';
import { canonicalizeUnit } from '@/features/takeoff/lib/units';

describe('canonicalizeUnit', () => {
  it('maps German LV units to canonical forms', () => {
    expect(canonicalizeUnit('Stück')).toBe('pcs');
    expect(canonicalizeUnit('Stk')).toBe('pcs');
    expect(canonicalizeUnit('lfm')).toBe('m');
    expect(canonicalizeUnit('m³')).toBe('m3');
    expect(canonicalizeUnit('m²')).toBe('m2');
    expect(canonicalizeUnit('psch')).toBe('lsum');
    expect(canonicalizeUnit('pauschal')).toBe('lsum');
    expect(canonicalizeUnit('cbm')).toBe('m3');
    expect(canonicalizeUnit('qm')).toBe('m2');
  });

  it('empty / nullish → pcs (neutral countable default)', () => {
    expect(canonicalizeUnit('')).toBe('pcs');
    expect(canonicalizeUnit('   ')).toBe('pcs');
    expect(canonicalizeUnit(null)).toBe('pcs');
    expect(canonicalizeUnit(undefined)).toBe('pcs');
  });

  it('is case- / dot- / whitespace-insensitive', () => {
    expect(canonicalizeUnit('M2')).toBe('m2');
    expect(canonicalizeUnit('Sq. M')).toBe('m2');
    expect(canonicalizeUnit('  CU M ')).toBe('m3');
    expect(canonicalizeUnit('No.')).toBe('pcs');
  });

  it('keeps mm / cm distinct (they are real, different units)', () => {
    expect(canonicalizeUnit('mm')).toBe('mm');
    expect(canonicalizeUnit('cm')).toBe('cm');
  });

  it('passes unknown units through lower-cased (better than dropping)', () => {
    expect(canonicalizeUnit('Furlong')).toBe('furlong');
  });

  it('canonical inputs are idempotent', () => {
    for (const u of ['m', 'm2', 'm3', 'kg', 't', 'pcs', 'lsum']) {
      expect(canonicalizeUnit(u)).toBe(u);
    }
  });
});

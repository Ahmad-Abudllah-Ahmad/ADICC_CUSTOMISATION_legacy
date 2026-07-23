// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { describe, it, expect } from 'vitest';
import { readAuditMeta, auditRowTooltip } from './auditMarkers';

const t = (_key: string, opts?: Record<string, unknown>): string => {
  let out = String(opts?.defaultValue ?? _key);
  if (opts) {
    for (const [k, v] of Object.entries(opts)) {
      if (k === 'defaultValue') continue;
      out = out.replace(new RegExp(`{{${k}}}`, 'g'), String(v));
    }
  }
  return out;
};

describe('readAuditMeta', () => {
  it('reads a well-formed audit summary', () => {
    const meta = { audit: { status: 'warnings', groups: ['price_outliers'], count: 1 } };
    expect(readAuditMeta(meta)).toEqual({
      status: 'warnings',
      groups: ['price_outliers'],
      count: 1,
    });
  });

  it('returns null when there is no audit key', () => {
    expect(readAuditMeta({ resources: [] })).toBeNull();
    expect(readAuditMeta(null)).toBeNull();
    expect(readAuditMeta(undefined)).toBeNull();
  });

  it('returns null for an empty audit summary', () => {
    expect(readAuditMeta({ audit: { groups: [], count: 0 } })).toBeNull();
  });

  it('falls back count to the number of groups', () => {
    const meta = { audit: { groups: ['duplicates', 'wrong_units'] } };
    expect(readAuditMeta(meta)?.count).toBe(2);
  });

  it('drops non-string group entries', () => {
    const meta = { audit: { groups: ['duplicates', 5, null], count: 3 } };
    expect(readAuditMeta(meta)?.groups).toEqual(['duplicates']);
  });
});

describe('auditRowTooltip', () => {
  it('builds a labelled tooltip from the persisted groups', () => {
    const data = { metadata: { audit: { groups: ['price_outliers', 'wrong_units'], count: 2 } } };
    expect(auditRowTooltip(data, t)).toBe('Estimate audit: 2 issue(s) - Price outliers, Wrong units');
  });

  it('returns undefined for a clean row (no AG tooltip)', () => {
    expect(auditRowTooltip({ metadata: {} }, t)).toBeUndefined();
    expect(auditRowTooltip(undefined, t)).toBeUndefined();
  });

  it('humanises an unknown group key', () => {
    const data = { metadata: { audit: { groups: ['some_other'], count: 1 } } };
    expect(auditRowTooltip(data, t)).toBe('Estimate audit: 1 issue(s) - some other');
  });
});

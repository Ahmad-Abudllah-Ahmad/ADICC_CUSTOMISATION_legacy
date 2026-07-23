// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { describe, it, expect } from 'vitest';
import {
  groupFindings,
  scoreToPct,
  computeScoreDelta,
  groupLabel,
  fixLabel,
  toApplyFixBody,
  AUDIT_GROUP_ORDER,
  type AuditFinding,
} from './estimateAudit';

/** Minimal i18n stub: return the provided defaultValue with {{vars}} filled. */
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

function finding(overrides: Partial<AuditFinding>): AuditFinding {
  return {
    id: 'f',
    group: 'price_outliers',
    rule_id: 'boq_quality.unit_rate_in_range',
    severity: 'warning',
    message: 'm',
    ordinal: '01',
    description: 'A',
    position_id: 'p1',
    position_ids: ['p1'],
    fix: null,
    ...overrides,
  };
}

describe('groupFindings', () => {
  it('orders groups by AUDIT_GROUP_ORDER regardless of input order', () => {
    const findings = [
      finding({ group: 'price_outliers', id: 'a' }),
      finding({ group: 'missing_items', id: 'b' }),
      finding({ group: 'duplicates', id: 'c' }),
    ];
    const grouped = groupFindings(findings);
    expect(grouped.map(([k]) => k)).toEqual(['missing_items', 'duplicates', 'price_outliers']);
  });

  it('keeps all findings within a group', () => {
    const findings = [
      finding({ group: 'wrong_units', id: 'a' }),
      finding({ group: 'wrong_units', id: 'b' }),
    ];
    const grouped = groupFindings(findings);
    expect(grouped).toHaveLength(1);
    expect(grouped[0]![1].map((f) => f.id)).toEqual(['a', 'b']);
  });

  it('appends unknown groups after the known ones', () => {
    const grouped = groupFindings([
      finding({ group: 'mystery', id: 'x' }),
      finding({ group: 'missing_items', id: 'y' }),
    ]);
    expect(grouped.map(([k]) => k)).toEqual(['missing_items', 'mystery']);
  });
});

describe('scoreToPct', () => {
  it('rounds a 0..1 score to a percentage', () => {
    expect(scoreToPct(0.62)).toBe(62);
    expect(scoreToPct(1)).toBe(100);
  });

  it('treats null / NaN as 0 and clamps out-of-range', () => {
    expect(scoreToPct(null)).toBe(0);
    expect(scoreToPct(undefined)).toBe(0);
    expect(scoreToPct(Number.NaN)).toBe(0);
    expect(scoreToPct(1.5)).toBe(100);
    expect(scoreToPct(-0.2)).toBe(0);
  });
});

describe('computeScoreDelta', () => {
  it('reports an improvement in percentage points', () => {
    const d = computeScoreDelta(0.5, 0.75);
    expect(d).toEqual({ prevPct: 50, nextPct: 75, deltaPct: 25, improved: true });
  });

  it('is not improved when the score is unchanged or lower', () => {
    expect(computeScoreDelta(0.8, 0.8).improved).toBe(false);
    expect(computeScoreDelta(0.8, 0.6)).toMatchObject({ deltaPct: -20, improved: false });
  });

  it('handles a null baseline', () => {
    expect(computeScoreDelta(null, 0.9)).toEqual({
      prevPct: 0,
      nextPct: 90,
      deltaPct: 90,
      improved: true,
    });
  });
});

describe('groupLabel', () => {
  it('maps known group keys to readable labels', () => {
    expect(groupLabel('price_outliers', t)).toBe('Price outliers');
    expect(groupLabel('missing_items', t)).toBe('Missing items');
  });

  it('humanises an unknown key', () => {
    expect(groupLabel('some_other_group', t)).toBe('some other group');
  });
});

describe('fixLabel', () => {
  it('includes the concrete target rate', () => {
    expect(fixLabel({ type: 'set_rate_to_median', params: { unit_rate: '200.00' } }, t)).toBe(
      'Set rate to 200.00',
    );
  });

  it('includes the target unit', () => {
    expect(fixLabel({ type: 'switch_unit', params: { unit: 'm3' } }, t)).toBe('Set unit to m3');
  });

  it('counts the duplicates being renumbered', () => {
    expect(
      fixLabel({ type: 'merge_duplicate', params: { duplicate_position_ids: ['a', 'b'] } }, t),
    ).toBe('Renumber duplicate (2)');
  });

  it('labels the companion-line fix', () => {
    expect(fixLabel({ type: 'add_companion_line', params: { section_id: 's1' } }, t)).toBe(
      'Add a line to this section',
    );
  });
});

describe('toApplyFixBody', () => {
  it('returns null for a finding with no fix', () => {
    expect(toApplyFixBody(finding({ fix: null }))).toBeNull();
  });

  it('carries fix_type, position_id and params', () => {
    const body = toApplyFixBody(
      finding({
        position_id: 'p9',
        fix: { type: 'set_rate_to_median', params: { unit_rate: '12.50' } },
      }),
    );
    expect(body).toEqual({
      fix_type: 'set_rate_to_median',
      position_id: 'p9',
      params: { unit_rate: '12.50' },
    });
  });
});

describe('AUDIT_GROUP_ORDER', () => {
  it('matches the four backend finding groups', () => {
    expect([...AUDIT_GROUP_ORDER]).toEqual([
      'missing_items',
      'wrong_units',
      'duplicates',
      'price_outliers',
    ]);
  });
});

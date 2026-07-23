import { describe, expect, it } from 'vitest';
import {
  buildDeviationLegend,
  deviationHeadline,
  formatDeviationRms,
  DEVIATION_SEVERITY_HEX,
  type ScanDeviationItem,
  type ScanDeviationSummary,
  type DeviationSeverity,
} from '../deviationData';

/** Identity-ish translator: returns the defaultValue so assertions read the
 *  English copy, not the key. */
const t = (_k: string, opts?: { defaultValue?: string } & Record<string, unknown>) => {
  let s = opts?.defaultValue ?? _k;
  // Interpolate {{count}} the way i18next would, so count-bearing strings
  // assert meaningfully.
  if (opts && 'count' in opts) {
    s = s.replace('{{count}}', String(opts.count));
  }
  return s;
};

function item(over: Partial<ScanDeviationItem> & { severity: DeviationSeverity }): ScanDeviationItem {
  return {
    registration_id: Math.random().toString(36).slice(2),
    scan_id: 's',
    target_ref: 'm',
    accuracy_tier: 'survey',
    tier_tolerance_mm: '6',
    rms_error: '3',
    out_of_tolerance_count: 0,
    coverage_pct: '95',
    hole_area: null,
    confidence: null,
    deviation_map_uri: null,
    severity_color: DEVIATION_SEVERITY_HEX[over.severity],
    created_at: '2026-06-20T00:00:00Z',
    ...over,
  };
}

function summary(items: ScanDeviationItem[], worst: DeviationSeverity): ScanDeviationSummary {
  return {
    model_id: 'm',
    project_id: 'p',
    has_deviation: items.length > 0,
    worst_severity: worst,
    worst_severity_color: DEVIATION_SEVERITY_HEX[worst],
    items,
    total: items.length,
  };
}

describe('buildDeviationLegend', () => {
  it('returns no rows when there is no deviation data', () => {
    expect(buildDeviationLegend(null, t)).toEqual([]);
    expect(buildDeviationLegend(undefined, t)).toEqual([]);
    expect(buildDeviationLegend(summary([], 'unknown'), t)).toEqual([]);
  });

  it('counts each severity band and orders worst-first', () => {
    const rows = buildDeviationLegend(
      summary(
        [
          item({ severity: 'within' }),
          item({ severity: 'within' }),
          item({ severity: 'over' }),
          item({ severity: 'warning' }),
        ],
        'over',
      ),
      t,
    );
    // over, warning, within (no unknown band present)
    expect(rows.map((r) => r.severity)).toEqual(['over', 'warning', 'within']);
    expect(rows.map((r) => r.count)).toEqual([1, 1, 2]);
    expect(rows.find((r) => r.severity === 'within')?.label).toBe('Within tolerance');
  });

  it('drops bands with zero scans', () => {
    const rows = buildDeviationLegend(
      summary([item({ severity: 'within' })], 'within'),
      t,
    );
    expect(rows).toHaveLength(1);
    expect(rows[0]!.severity).toBe('within');
  });

  it('prefers the server-sent colour but falls back to the fixed palette', () => {
    const rows = buildDeviationLegend(
      summary(
        [
          item({ severity: 'over', severity_color: '#abcdef' }),
          item({ severity: 'warning', severity_color: '' }), // empty -> fallback
        ],
        'over',
      ),
      t,
    );
    expect(rows.find((r) => r.severity === 'over')?.hex).toBe('#abcdef');
    expect(rows.find((r) => r.severity === 'warning')?.hex).toBe(
      DEVIATION_SEVERITY_HEX.warning,
    );
  });
});

describe('deviationHeadline', () => {
  it('maps each worst severity to its headline', () => {
    expect(deviationHeadline(summary([item({ severity: 'over' })], 'over'), t)).toBe(
      'As-built scan deviates beyond tolerance',
    );
    expect(
      deviationHeadline(summary([item({ severity: 'warning' })], 'warning'), t),
    ).toBe('As-built scan has local deviations');
    expect(
      deviationHeadline(summary([item({ severity: 'within' })], 'within'), t),
    ).toBe('As-built scan within tolerance');
    expect(deviationHeadline(null, t)).toBe('Scan-vs-design deviation');
  });
});

describe('formatDeviationRms', () => {
  it('formats RMS against the tier tolerance, rounding to 1 dp', () => {
    expect(formatDeviationRms({ rms_error: '4.23', tier_tolerance_mm: '6' })).toBe(
      'RMS 4.2 mm / 6 mm',
    );
  });

  it('omits the tolerance when unknown', () => {
    expect(formatDeviationRms({ rms_error: '4', tier_tolerance_mm: null })).toBe(
      'RMS 4 mm',
    );
  });

  it('returns null when no RMS was measured', () => {
    expect(formatDeviationRms({ rms_error: null, tier_tolerance_mm: '6' })).toBeNull();
  });

  it('coerces the Decimal-string safely (never NaN)', () => {
    // A malformed wire value degrades to 0 via toNum, never crashes.
    expect(formatDeviationRms({ rms_error: 'oops', tier_tolerance_mm: '6' })).toBe(
      'RMS 0 mm / 6 mm',
    );
  });
});

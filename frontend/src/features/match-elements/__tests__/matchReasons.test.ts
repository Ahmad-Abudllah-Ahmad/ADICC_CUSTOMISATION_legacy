// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
//
// Unit suite for the review-worklist helpers. Pure functions, no DOM, no
// network - these pin the lane rules (which mirror the backend
// bulk_confirm gate), the plain-language reason mapping and the prior-pick
// correlation so the review UI can never silently drift from them.

import { describe, it, expect } from 'vitest';
import type { ConfidenceBand, GroupStatus } from '../api';
import {
  MATCH_LANE_ORDER,
  buildMatchReasons,
  confirmableKeys,
  groupSortKey,
  indexTemplatesBySignature,
  isConfirmable,
  isPriorPickCandidate,
  isResolvedStatus,
  laneForGroup,
  partitionLanes,
  priorConfirmReason,
  priorPickForSignature,
  reasoningText,
  STRONG_SEMANTIC_MIN,
  type LaneGroupInput,
} from '../matchReasons';

function grp(over: Partial<LaneGroupInput> & { group_key?: string } = {}): LaneGroupInput & {
  group_key: string;
} {
  // Default only when a key is absent - an explicit null (no candidate / no
  // numeric confidence yet) must survive, so `??` would wrongly swallow it.
  return {
    group_key: over.group_key ?? 'g',
    status: over.status ?? 'suggested',
    confidence_band: over.confidence_band ?? 'medium',
    confidence: over.confidence === undefined ? '0.65' : over.confidence,
    suggested_code: over.suggested_code === undefined ? 'CWICR-1' : over.suggested_code,
  };
}

describe('laneForGroup', () => {
  it('routes a high-confidence suggestion to the auto-confirmed lane', () => {
    expect(laneForGroup(grp({ confidence_band: 'high' }))).toBe('auto_confirmed');
  });

  it('routes a medium-confidence suggestion to quick-review', () => {
    expect(laneForGroup(grp({ confidence_band: 'medium' }))).toBe('quick_review');
  });

  it('routes low and none confidence to needs-you', () => {
    expect(laneForGroup(grp({ confidence_band: 'low' }))).toBe('needs_you');
    expect(laneForGroup(grp({ confidence_band: 'none' }))).toBe('needs_you');
  });

  it('routes a group with no candidate to needs-you regardless of band', () => {
    expect(
      laneForGroup(grp({ suggested_code: null, confidence_band: 'high' })),
    ).toBe('needs_you');
    expect(laneForGroup(grp({ status: 'unmatched', confidence_band: 'high' }))).toBe(
      'needs_you',
    );
  });

  it('treats tbd (deferred) as needs-you', () => {
    expect(laneForGroup(grp({ status: 'tbd' }))).toBe('needs_you');
  });

  it('parks every resolved status in the auto-confirmed lane even at low band', () => {
    for (const status of ['confirmed', 'applied', 'overridden', 'skipped'] as GroupStatus[]) {
      expect(laneForGroup(grp({ status, confidence_band: 'low' }))).toBe('auto_confirmed');
    }
  });
});

describe('isResolvedStatus / isConfirmable', () => {
  it('flags settled statuses as resolved', () => {
    expect(isResolvedStatus('confirmed')).toBe(true);
    expect(isResolvedStatus('applied')).toBe(true);
    expect(isResolvedStatus('overridden')).toBe(true);
    expect(isResolvedStatus('skipped')).toBe(true);
    expect(isResolvedStatus('suggested')).toBe(false);
    expect(isResolvedStatus('unmatched')).toBe(false);
    expect(isResolvedStatus('tbd')).toBe(false);
  });

  it('only a suggested group with a candidate is confirmable (backend gate)', () => {
    expect(isConfirmable(grp({ status: 'suggested', suggested_code: 'X' }))).toBe(true);
    expect(isConfirmable(grp({ status: 'suggested', suggested_code: null }))).toBe(false);
    expect(isConfirmable(grp({ status: 'confirmed', suggested_code: 'X' }))).toBe(false);
    expect(isConfirmable(grp({ status: 'unmatched', suggested_code: null }))).toBe(false);
  });
});

describe('groupSortKey', () => {
  it('orders by numeric confidence ascending (worst first)', () => {
    expect(groupSortKey(grp({ confidence: '0.30' }))).toBeLessThan(
      groupSortKey(grp({ confidence: '0.80' })),
    );
  });

  it('falls back to a band rank when the numeric confidence is missing', () => {
    expect(groupSortKey(grp({ confidence: null, confidence_band: 'low' }))).toBeLessThan(
      groupSortKey(grp({ confidence: null, confidence_band: 'high' })),
    );
  });

  it('sinks resolved groups below unresolved ones', () => {
    const resolved = groupSortKey(grp({ status: 'confirmed', confidence: '0.10' }));
    const openTop = groupSortKey(grp({ status: 'suggested', confidence: '0.95' }));
    expect(resolved).toBeGreaterThan(openTop);
  });
});

describe('partitionLanes', () => {
  it('splits groups into the three lanes, each sorted worst-first', () => {
    const groups = [
      grp({ group_key: 'hi', confidence_band: 'high', confidence: '0.90' }),
      grp({ group_key: 'med', confidence_band: 'medium', confidence: '0.65' }),
      grp({ group_key: 'lo1', confidence_band: 'low', confidence: '0.40' }),
      grp({ group_key: 'lo2', confidence_band: 'low', confidence: '0.20' }),
    ];
    const lanes = partitionLanes(groups);
    expect(lanes.auto_confirmed.map((g) => g.group_key)).toEqual(['hi']);
    expect(lanes.quick_review.map((g) => g.group_key)).toEqual(['med']);
    // Worst (0.20) first within the needs-you lane.
    expect(lanes.needs_you.map((g) => g.group_key)).toEqual(['lo2', 'lo1']);
  });

  it('does not mutate the input array', () => {
    const groups = [
      grp({ group_key: 'a', confidence: '0.9' }),
      grp({ group_key: 'b', confidence: '0.1' }),
    ];
    const before = groups.map((g) => g.group_key);
    partitionLanes(groups);
    expect(groups.map((g) => g.group_key)).toEqual(before);
  });

  it('exposes lanes in worst-first render order', () => {
    expect(MATCH_LANE_ORDER).toEqual(['needs_you', 'quick_review', 'auto_confirmed']);
  });
});

describe('confirmableKeys', () => {
  it('returns only the suggested-with-candidate group keys', () => {
    const laneGroups = [
      grp({ group_key: 'ok', status: 'suggested', suggested_code: 'X' }),
      grp({ group_key: 'done', status: 'confirmed', suggested_code: 'X' }),
      grp({ group_key: 'empty', status: 'suggested', suggested_code: null }),
    ];
    expect(confirmableKeys(laneGroups)).toEqual(['ok']);
  });
});

describe('buildMatchReasons', () => {
  it('maps the four headline boosts to plain sentences', () => {
    const reasons = buildMatchReasons({
      unit: 'm2',
      vector_score: 0.5,
      boosts_applied: {
        unit_match: 0.05,
        classifier_match: 0.15,
        soft_nominal_size_mm: 0.1,
        resources_token_set: 0.2,
      },
    });
    const ids = reasons.map((r) => r.id);
    expect(ids).toContain('unit');
    expect(ids).toContain('trade');
    expect(ids).toContain('size');
    expect(ids).toContain('terms');
    expect(reasons.every((r) => r.tone === 'positive')).toBe(true);
  });

  it('names the unit when one is present', () => {
    const [unitReason] = buildMatchReasons({
      unit: 'm3',
      boosts_applied: { unit_match: 0.05 },
    });
    expect(unitReason?.vars).toEqual({ unit: 'm3' });
    expect(unitReason?.defaultLabel).toContain('{{unit}}');
  });

  it('flags a unit mismatch as a negative reason', () => {
    const reasons = buildMatchReasons({ boosts_applied: { unit_mismatch: -0.1 } });
    expect(reasons).toHaveLength(1);
    expect(reasons[0]?.id).toBe('unit');
    expect(reasons[0]?.tone).toBe('negative');
  });

  it('shows only one trade reason when both classifier boosts fire', () => {
    const reasons = buildMatchReasons({
      boosts_applied: { classifier_match: 0.15, classifier_group_match: 0.08 },
    });
    expect(reasons.filter((r) => r.id === 'trade')).toHaveLength(1);
  });

  it('ignores zero-delta and unknown boost keys (no raw-key leak)', () => {
    const reasons = buildMatchReasons({
      boosts_applied: { unit_match: 0, soft_mystery_flag: 0.9, region_match: 0.05 },
    });
    expect(reasons.map((r) => r.id)).toEqual(['region']);
  });

  it('surfaces a strong semantic score as the term-overlap reason', () => {
    const reasons = buildMatchReasons({ vector_score: STRONG_SEMANTIC_MIN + 0.05 });
    expect(reasons.map((r) => r.id)).toContain('semantic');
  });

  it('does not add the semantic reason when a keyword boost already fired', () => {
    const reasons = buildMatchReasons({
      vector_score: 0.95,
      boosts_applied: { resources_token_set: 0.2 },
    });
    expect(reasons.map((r) => r.id)).toContain('terms');
    expect(reasons.map((r) => r.id)).not.toContain('semantic');
  });

  it('returns nothing for a bare candidate with no signals', () => {
    expect(buildMatchReasons({ vector_score: 0.1 })).toEqual([]);
  });
});

describe('priorConfirmReason / reasoningText', () => {
  it('carries the confirm count into the reason vars', () => {
    const r = priorConfirmReason(4);
    expect(r.id).toBe('prior');
    expect(r.vars).toEqual({ count: 4 });
  });

  it('returns trimmed reasoning text or null', () => {
    expect(reasoningText({ reasoning: '  picked the closer rate  ' })).toBe(
      'picked the closer rate',
    );
    expect(reasoningText({ reasoning: '   ' })).toBeNull();
    expect(reasoningText({ reasoning: null })).toBeNull();
    expect(reasoningText({})).toBeNull();
  });
});

describe('prior-pick correlation', () => {
  const templates = [
    { signature: 'sig-a', use_count: 5, last_used_at: '2026-06-01', cwicr_position_id: 'cost-1' },
    { signature: 'sig-b', use_count: 2, last_used_at: null, cwicr_position_id: 'cost-2' },
  ];

  it('finds the saved template for a group signature', () => {
    const idx = indexTemplatesBySignature(templates);
    expect(priorPickForSignature('sig-a', idx)?.cwicr_position_id).toBe('cost-1');
    expect(priorPickForSignature('sig-missing', idx)).toBeNull();
    expect(priorPickForSignature(null, idx)).toBeNull();
  });

  it('marks the candidate that was picked last time', () => {
    const prior = { cwicr_position_id: 'cost-1' };
    expect(isPriorPickCandidate('cost-1', prior)).toBe(true);
    expect(isPriorPickCandidate('cost-9', prior)).toBe(false);
    expect(isPriorPickCandidate(null, prior)).toBe(false);
    expect(isPriorPickCandidate('cost-1', null)).toBe(false);
  });

  it('first (most-used) row wins on a duplicate signature', () => {
    const dup = [
      { signature: 's', use_count: 9, last_used_at: null, cwicr_position_id: 'winner' },
      { signature: 's', use_count: 1, last_used_at: null, cwicr_position_id: 'loser' },
    ];
    const idx = indexTemplatesBySignature(dup);
    expect(priorPickForSignature('s', idx)?.cwicr_position_id).toBe('winner');
  });

  it('covers every confidence band in the lane maths', () => {
    const bands: ConfidenceBand[] = ['high', 'medium', 'low', 'none'];
    for (const band of bands) {
      expect(() => laneForGroup(grp({ confidence_band: band }))).not.toThrow();
    }
  });
});

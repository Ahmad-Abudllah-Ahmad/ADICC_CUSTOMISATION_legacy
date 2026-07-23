// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { describe, it, expect } from 'vitest';

import {
  toneForState,
  stateLabelKey,
  readinessPercent,
  hasActionableIssues,
  issueBreakdown,
  buildFederationViewerDeeplink,
  snapshotFileName,
  parseSnapshotPayload,
  snapshotMatchesFederation,
  diffSummaryCounts,
  diffHasChanges,
  formatDrift,
  type FederationHealth,
  type FederationSnapshot,
  type FederationDiff,
} from './federationHealth';

function makeHealth(over: Partial<FederationHealth> = {}): FederationHealth {
  return {
    federation_id: 'fed-1',
    member_count: 0,
    ready_count: 0,
    processing_count: 0,
    failed_count: 0,
    stale_count: 0,
    missing_count: 0,
    empty_count: 0,
    total_elements: 0,
    overall_state: 'no_members',
    score: 0,
    spread_days: null,
    members: [],
    ...over,
  };
}

function makeSnapshot(over: Partial<FederationSnapshot> = {}): FederationSnapshot {
  return {
    schema_version: '1',
    federation_id: 'fed-1',
    name: 'Coordination Set',
    captured_at: '2026-06-06T10:00:00Z',
    member_count: 0,
    total_elements: 0,
    members: [],
    ...over,
  };
}

describe('toneForState', () => {
  it('maps states to traffic-light tones', () => {
    expect(toneForState('ready')).toBe('green');
    expect(toneForState('stale')).toBe('amber');
    expect(toneForState('empty')).toBe('amber');
    expect(toneForState('processing')).toBe('amber');
    expect(toneForState('failed')).toBe('red');
    expect(toneForState('missing')).toBe('red');
    expect(toneForState('no_members')).toBe('neutral');
  });
});

describe('stateLabelKey', () => {
  it('prefixes with state_', () => {
    expect(stateLabelKey('ready')).toBe('state_ready');
    expect(stateLabelKey('no_members')).toBe('state_no_members');
  });
});

describe('readinessPercent', () => {
  it('converts a 0..1 score to an integer percent', () => {
    expect(readinessPercent(0)).toBe(0);
    expect(readinessPercent(0.5)).toBe(50);
    expect(readinessPercent(1)).toBe(100);
    expect(readinessPercent(0.333)).toBe(33);
  });
  it('clamps out-of-range and guards NaN', () => {
    expect(readinessPercent(1.5)).toBe(100);
    expect(readinessPercent(-1)).toBe(0);
    expect(readinessPercent(Number.NaN)).toBe(0);
  });
});

describe('hasActionableIssues', () => {
  it('false for undefined and all-ready sets', () => {
    expect(hasActionableIssues(undefined)).toBe(false);
    expect(
      hasActionableIssues(makeHealth({ member_count: 2, ready_count: 2, overall_state: 'ready' })),
    ).toBe(false);
  });
  it('true when any non-ready bucket is non-zero', () => {
    expect(hasActionableIssues(makeHealth({ failed_count: 1 }))).toBe(true);
    expect(hasActionableIssues(makeHealth({ stale_count: 1 }))).toBe(true);
    expect(hasActionableIssues(makeHealth({ processing_count: 1 }))).toBe(true);
    expect(hasActionableIssues(makeHealth({ empty_count: 1 }))).toBe(true);
    expect(hasActionableIssues(makeHealth({ missing_count: 1 }))).toBe(true);
  });
});

describe('issueBreakdown', () => {
  it('returns non-zero buckets worst-first, excluding ready', () => {
    const health = makeHealth({
      member_count: 5,
      ready_count: 2,
      failed_count: 1,
      missing_count: 1,
      stale_count: 1,
    });
    const result = issueBreakdown(health);
    expect(result).toEqual([
      { state: 'missing', count: 1 },
      { state: 'failed', count: 1 },
      { state: 'stale', count: 1 },
    ]);
  });
  it('empty for undefined / clean sets', () => {
    expect(issueBreakdown(undefined)).toEqual([]);
    expect(issueBreakdown(makeHealth({ ready_count: 3, member_count: 3 }))).toEqual([]);
  });
});

describe('buildFederationViewerDeeplink', () => {
  it('returns null for no members', () => {
    expect(buildFederationViewerDeeplink('fed-1', [])).toBeNull();
  });
  it('builds a primary-model deeplink with rest as models param', () => {
    const link = buildFederationViewerDeeplink('fed-1', ['m1', 'm2', 'm3']);
    expect(link).toBe('/bim/m1?federation=fed-1&models=m2%2Cm3');
  });
  it('omits the models param for a single member', () => {
    const link = buildFederationViewerDeeplink('fed-1', ['only']);
    expect(link).toBe('/bim/only?federation=fed-1');
  });
});

describe('snapshotFileName', () => {
  it('slugifies the name and appends the capture day', () => {
    expect(snapshotFileName(makeSnapshot({ name: 'Coordination Set' }))).toBe(
      'federation-coordination-set-2026-06-06.json',
    );
  });
  it('collapses punctuation and falls back when empty', () => {
    expect(snapshotFileName(makeSnapshot({ name: '  A/B — C!! ' }))).toBe(
      'federation-a-b-c-2026-06-06.json',
    );
    expect(
      snapshotFileName(makeSnapshot({ name: '', captured_at: '' })),
    ).toBe('federation-federation-snapshot.json');
  });
});

describe('parseSnapshotPayload', () => {
  it('accepts a well-formed snapshot', () => {
    const snap = makeSnapshot();
    expect(parseSnapshotPayload(snap)).toBe(snap);
  });
  it('rejects non-objects and missing keys with invalid_json_shape', () => {
    expect(() => parseSnapshotPayload(null)).toThrow('invalid_json_shape');
    expect(() => parseSnapshotPayload(42)).toThrow('invalid_json_shape');
    expect(() => parseSnapshotPayload({ federation_id: 'x' })).toThrow('invalid_json_shape');
    expect(() =>
      parseSnapshotPayload({ federation_id: 'x', captured_at: 'y', members: 'nope' }),
    ).toThrow('invalid_json_shape');
  });
  it('rejects unsupported schema versions', () => {
    expect(() =>
      parseSnapshotPayload({
        federation_id: 'x',
        captured_at: 'y',
        members: [],
        schema_version: '2',
      }),
    ).toThrow('schema_version_unsupported');
  });
});

describe('snapshotMatchesFederation', () => {
  it('matches by federation_id', () => {
    expect(snapshotMatchesFederation(makeSnapshot({ federation_id: 'a' }), 'a')).toBe(true);
    expect(snapshotMatchesFederation(makeSnapshot({ federation_id: 'a' }), 'b')).toBe(false);
  });
});

function makeDiff(over: Partial<FederationDiff> = {}): FederationDiff {
  return {
    federation_id: 'fed-1',
    old_captured_at: '2026-01-01T00:00:00Z',
    new_captured_at: '2026-02-01T00:00:00Z',
    added: [],
    removed: [],
    changed: [],
    unchanged: [],
    total_element_drift: 0,
    ...over,
  };
}

describe('diffSummaryCounts / diffHasChanges', () => {
  it('counts each bucket', () => {
    const diff = makeDiff({
      added: [{ bim_model_id: 'a', model_name: 'A', discipline: 'arch', element_count: 1 }],
      removed: [{ bim_model_id: 'b', model_name: 'B', discipline: 'mep', element_count: 2 }],
      changed: [
        {
          bim_model_id: 'c',
          model_name: 'C',
          discipline: 'struct',
          element_count_delta: 5,
          old_element_count: 5,
          new_element_count: 10,
        },
      ],
      unchanged: [{ bim_model_id: 'd', model_name: 'D', discipline: 'arch', element_count: 3 }],
      total_element_drift: 6,
    });
    expect(diffSummaryCounts(diff)).toEqual({
      added: 1,
      removed: 1,
      changed: 1,
      unchanged: 1,
      drift: 6,
    });
    expect(diffHasChanges(diff)).toBe(true);
  });
  it('diffHasChanges false for an all-unchanged diff with no drift', () => {
    const diff = makeDiff({
      unchanged: [{ bim_model_id: 'd', model_name: 'D', discipline: 'arch', element_count: 3 }],
    });
    expect(diffHasChanges(diff)).toBe(false);
  });
});

describe('formatDrift', () => {
  it('signs positive and leaves negative/zero', () => {
    expect(formatDrift(1240)).toBe('+1,240');
    expect(formatDrift(-37)).toBe('-37');
    expect(formatDrift(0)).toBe('0');
  });
});

// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Unit tests for the pure inbox helpers.
 *
 * Cover the ordering, severity normalisation, approval counting, title
 * resolution and "x ago" formatting that drive the unified inbox UI. All
 * pure - no React, no network. ``formatTimeAgo`` is fed a fixed ``now`` and
 * a passthrough ``t`` so the assertions are deterministic and locale-free.
 */
import { describe, it, expect } from 'vitest';
import {
  ALL_INBOX_FILTER,
  SEVERITY_RANK,
  countApprovals,
  distinctInboxProjects,
  distinctInboxSeverities,
  filterInboxItems,
  formatTimeAgo,
  isInboxFiltered,
  matchesInboxFilter,
  normalizeSeverity,
  resolveTitle,
  sortInboxItems,
} from '../inboxUtils';
import type { InboxItem } from '../api';

function item(over: Partial<InboxItem> = {}): InboxItem {
  return {
    id: 'x:1',
    kind: 'alert',
    source: 'notification',
    title: 'Something',
    severity: 'info',
    created_at: null,
    ...over,
  };
}

// Passthrough ``t`` that interpolates {{count}} so we can assert the unit.
const t = (key: string, opts?: Record<string, unknown>): string => {
  const def = (opts?.defaultValue as string) ?? key;
  if (opts && 'count' in opts) return def.replace('{{count}}', String(opts.count));
  return def;
};

describe('normalizeSeverity', () => {
  it('passes known severities through', () => {
    expect(normalizeSeverity('critical')).toBe('critical');
    expect(normalizeSeverity('warning')).toBe('warning');
    expect(normalizeSeverity('info')).toBe('info');
  });

  it('clamps unknown / null to info', () => {
    expect(normalizeSeverity('bogus')).toBe('info');
    expect(normalizeSeverity(null)).toBe('info');
    expect(normalizeSeverity(undefined)).toBe('info');
  });

  it('ranks critical > warning > info', () => {
    expect(SEVERITY_RANK.critical).toBeGreaterThan(SEVERITY_RANK.warning);
    expect(SEVERITY_RANK.warning).toBeGreaterThan(SEVERITY_RANK.info);
  });
});

describe('sortInboxItems', () => {
  it('orders newest first', () => {
    const out = sortInboxItems([
      item({ id: 'old', created_at: '2026-01-01T00:00:00+00:00' }),
      item({ id: 'new', created_at: '2026-06-01T00:00:00+00:00' }),
    ]);
    expect(out.map((i) => i.id)).toEqual(['new', 'old']);
  });

  it('sorts missing timestamps last', () => {
    const out = sortInboxItems([
      item({ id: 'none', created_at: null }),
      item({ id: 'dated', created_at: '2026-06-01T00:00:00+00:00' }),
    ]);
    expect(out.map((i) => i.id)).toEqual(['dated', 'none']);
  });

  it('breaks timestamp ties by severity', () => {
    const ts = '2026-06-01T00:00:00+00:00';
    const out = sortInboxItems([
      item({ id: 'info', created_at: ts, severity: 'info' }),
      item({ id: 'crit', created_at: ts, severity: 'critical' }),
      item({ id: 'warn', created_at: ts, severity: 'warning' }),
    ]);
    expect(out.map((i) => i.id)).toEqual(['crit', 'warn', 'info']);
  });

  it('is deterministic regardless of input order (id tiebreak)', () => {
    const ts = '2026-06-01T00:00:00+00:00';
    const a = sortInboxItems([
      item({ id: 'a', created_at: ts }),
      item({ id: 'b', created_at: ts }),
    ]);
    const b = sortInboxItems([
      item({ id: 'b', created_at: ts }),
      item({ id: 'a', created_at: ts }),
    ]);
    expect(a.map((i) => i.id)).toEqual(b.map((i) => i.id));
  });

  it('does not mutate the input array', () => {
    const input = [
      item({ id: '1', created_at: '2026-01-01T00:00:00+00:00' }),
      item({ id: '2', created_at: '2026-06-01T00:00:00+00:00' }),
    ];
    const before = input.map((i) => i.id);
    sortInboxItems(input);
    expect(input.map((i) => i.id)).toEqual(before);
  });
});

describe('countApprovals', () => {
  it('counts only approval-kind items', () => {
    const items = [
      item({ id: 'a', kind: 'approval' }),
      item({ id: 'b', kind: 'alert' }),
      item({ id: 'c', kind: 'approval' }),
    ];
    expect(countApprovals(items)).toBe(2);
  });

  it('returns 0 for an empty list', () => {
    expect(countApprovals([])).toBe(0);
  });
});

describe('resolveTitle', () => {
  it('prefers the i18n key with title as fallback', () => {
    expect(resolveTitle({ title_key: 'inbox.approval_file', title: 'Approve file' })).toEqual({
      key: 'inbox.approval_file',
      defaultValue: 'Approve file',
    });
  });

  it('uses the key itself as fallback when title is empty', () => {
    expect(resolveTitle({ title_key: 'inbox.x', title: null })).toEqual({
      key: 'inbox.x',
      defaultValue: 'inbox.x',
    });
  });

  it('renders a raw title via a stable passthrough key when no key', () => {
    expect(resolveTitle({ title_key: null, title: 'Hello' })).toEqual({
      key: 'inbox.item_title_raw',
      defaultValue: 'Hello',
    });
  });

  it('degrades to a generic label when both are empty', () => {
    expect(resolveTitle({ title_key: '', title: '' })).toEqual({
      key: 'inbox.item_untitled',
      defaultValue: 'Action required',
    });
  });

  it('treats whitespace-only values as empty', () => {
    expect(resolveTitle({ title_key: '   ', title: '  ' })).toEqual({
      key: 'inbox.item_untitled',
      defaultValue: 'Action required',
    });
  });
});

describe('formatTimeAgo', () => {
  const now = new Date('2026-06-01T12:00:00+00:00').getTime();

  it('returns empty string for missing / unparseable input', () => {
    expect(formatTimeAgo(null, t, now)).toBe('');
    expect(formatTimeAgo(undefined, t, now)).toBe('');
    expect(formatTimeAgo('not-a-date', t, now)).toBe('');
  });

  it('says "Just now" under a minute', () => {
    expect(formatTimeAgo('2026-06-01T11:59:30+00:00', t, now)).toBe('Just now');
  });

  it('formats minutes / hours / days', () => {
    expect(formatTimeAgo('2026-06-01T11:30:00+00:00', t, now)).toBe('30m ago');
    expect(formatTimeAgo('2026-06-01T09:00:00+00:00', t, now)).toBe('3h ago');
    expect(formatTimeAgo('2026-05-29T12:00:00+00:00', t, now)).toBe('3d ago');
  });
});

describe('matchesInboxFilter / filterInboxItems', () => {
  const items: InboxItem[] = [
    item({ id: 'a', kind: 'approval', project_id: 'p1', project_name: 'Alpha', severity: 'critical' }),
    item({ id: 'b', kind: 'alert', project_id: 'p1', project_name: 'Alpha', severity: 'warning' }),
    item({ id: 'c', kind: 'alert', project_id: 'p2', project_name: 'Beta', severity: 'info' }),
  ];

  it('the neutral filter matches everything', () => {
    expect(filterInboxItems(items, ALL_INBOX_FILTER).map((i) => i.id)).toEqual(['a', 'b', 'c']);
  });

  it('filters by kind', () => {
    expect(
      filterInboxItems(items, { ...ALL_INBOX_FILTER, kind: 'approval' }).map((i) => i.id),
    ).toEqual(['a']);
  });

  it('filters by project', () => {
    expect(
      filterInboxItems(items, { ...ALL_INBOX_FILTER, projectId: 'p1' }).map((i) => i.id),
    ).toEqual(['a', 'b']);
  });

  it('filters by severity', () => {
    expect(
      filterInboxItems(items, { ...ALL_INBOX_FILTER, severity: 'info' }).map((i) => i.id),
    ).toEqual(['c']);
  });

  it('combines axes with AND', () => {
    expect(matchesInboxFilter(items[1]!, { kind: 'alert', projectId: 'p1', severity: 'warning' })).toBe(
      true,
    );
    expect(
      filterInboxItems(items, { kind: 'alert', projectId: 'p1', severity: 'warning' }).map(
        (i) => i.id,
      ),
    ).toEqual(['b']);
  });

  it('treats a missing project_id as unmatched by a specific project', () => {
    expect(matchesInboxFilter(item({ id: 'x' }), { ...ALL_INBOX_FILTER, projectId: 'p1' })).toBe(
      false,
    );
  });
});

describe('isInboxFiltered', () => {
  it('is false for the neutral filter', () => {
    expect(isInboxFiltered(ALL_INBOX_FILTER)).toBe(false);
  });

  it('is true when any axis is narrowed', () => {
    expect(isInboxFiltered({ ...ALL_INBOX_FILTER, kind: 'alert' })).toBe(true);
    expect(isInboxFiltered({ ...ALL_INBOX_FILTER, projectId: 'p1' })).toBe(true);
    expect(isInboxFiltered({ ...ALL_INBOX_FILTER, severity: 'info' })).toBe(true);
  });
});

describe('distinctInboxProjects', () => {
  it('dedupes by id, sorts by name and skips project-less items', () => {
    const out = distinctInboxProjects([
      item({ id: '1', project_id: 'p2', project_name: 'Beta' }),
      item({ id: '2', project_id: 'p1', project_name: 'Alpha' }),
      item({ id: '3', project_id: 'p1', project_name: 'Alpha' }),
      item({ id: '4' }),
    ]);
    expect(out).toEqual([
      { id: 'p1', name: 'Alpha' },
      { id: 'p2', name: 'Beta' },
    ]);
  });

  it('falls back to the id when the name is missing', () => {
    const out = distinctInboxProjects([item({ id: '1', project_id: 'p9', project_name: null })]);
    expect(out).toEqual([{ id: 'p9', name: 'p9' }]);
  });
});

describe('distinctInboxSeverities', () => {
  it('returns present severities, most-severe first', () => {
    const out = distinctInboxSeverities([
      item({ id: '1', severity: 'info' }),
      item({ id: '2', severity: 'critical' }),
      item({ id: '3', severity: 'info' }),
    ]);
    expect(out).toEqual(['critical', 'info']);
  });
});

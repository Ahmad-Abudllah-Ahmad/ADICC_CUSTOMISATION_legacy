// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { describe, it, expect } from 'vitest';
import type { QueuedOp } from '@/shared/lib/offline';
import {
  deriveStatus,
  kindLabel,
  sortForReview,
  summariseQueue,
  groupByKind,
  formatRelativeTime,
  type SyncQueueItem,
} from './syncQueueSummary';

/** Build a QueuedOp with sensible defaults; override per test. */
function op(over: Partial<QueuedOp> = {}): QueuedOp {
  return {
    seq: 1,
    clientOpId: 'op-1',
    method: 'POST',
    path: '/v1/field-diary/entries/',
    body: { x: 1 },
    kind: 'field.diary.entry',
    queuedAt: 1_000,
    retries: 0,
    ...over,
  };
}

/** Build a decorated item directly (for sort/group tests). */
function item(over: Partial<SyncQueueItem> = {}): SyncQueueItem {
  return {
    clientOpId: 'i-1',
    kind: 'field.diary.entry',
    method: 'POST',
    path: '/v1/field-diary/entries/',
    queuedAt: 1_000,
    retries: 0,
    status: 'pending',
    ...over,
  };
}

describe('deriveStatus', () => {
  it('is pending when never attempted', () => {
    expect(deriveStatus({ retries: 0 })).toBe('pending');
  });
  it('is failing after one or more transient failures', () => {
    expect(deriveStatus({ retries: 1 })).toBe('failing');
    expect(deriveStatus({ retries: 5 })).toBe('failing');
  });
});

describe('kindLabel', () => {
  it('maps known field kinds to friendly labels', () => {
    expect(kindLabel('field.diary.entry')).toBe('Diary entry');
    expect(kindLabel('field.diary.activity')).toBe('Time entry');
    expect(kindLabel('field.crew.punch')).toBe('Crew punch');
    expect(kindLabel('field_report')).toBe('Field report');
    expect(kindLabel('daily_diary')).toBe('Daily diary');
  });

  it('humanises an unknown dotted kind from its last segment', () => {
    expect(kindLabel('field.photo.upload')).toBe('Upload');
    expect(kindLabel('punch_list_item')).toBe('Punch List Item');
  });

  it('never returns an empty string', () => {
    expect(kindLabel('')).toBe('');
    expect(kindLabel('x')).toBe('X');
  });
});

describe('summariseQueue', () => {
  it('returns an empty summary for no ops', () => {
    const s = summariseQueue([]);
    expect(s.isEmpty).toBe(true);
    expect(s.total).toBe(0);
    expect(s.pending).toBe(0);
    expect(s.failing).toBe(0);
    expect(s.items).toEqual([]);
  });

  it('counts pending vs failing correctly', () => {
    const s = summariseQueue([
      op({ clientOpId: 'a', retries: 0 }),
      op({ clientOpId: 'b', retries: 2 }),
      op({ clientOpId: 'c', retries: 0 }),
      op({ clientOpId: 'd', retries: 1 }),
    ]);
    expect(s.total).toBe(4);
    expect(s.failing).toBe(2);
    expect(s.pending).toBe(2);
    expect(s.isEmpty).toBe(false);
  });

  it('decorates each op with its derived status and carries the fields through', () => {
    const s = summariseQueue([
      op({ clientOpId: 'a', kind: 'field.crew.punch', method: 'PUT', path: '/v1/x/', queuedAt: 42, retries: 3 }),
    ]);
    const only = s.items[0];
    expect(only).toMatchObject({
      clientOpId: 'a',
      kind: 'field.crew.punch',
      method: 'PUT',
      path: '/v1/x/',
      queuedAt: 42,
      retries: 3,
      status: 'failing',
    });
  });

  it('orders failing ops before pending ops', () => {
    const s = summariseQueue([
      op({ clientOpId: 'pending-old', retries: 0, queuedAt: 10 }),
      op({ clientOpId: 'failing-new', retries: 1, queuedAt: 20 }),
    ]);
    expect(s.items.map((i) => i.clientOpId)).toEqual(['failing-new', 'pending-old']);
  });

  it('orders oldest-first within the same status (FIFO replay order)', () => {
    const s = summariseQueue([
      op({ clientOpId: 'p3', retries: 0, queuedAt: 300 }),
      op({ clientOpId: 'p1', retries: 0, queuedAt: 100 }),
      op({ clientOpId: 'p2', retries: 0, queuedAt: 200 }),
    ]);
    expect(s.items.map((i) => i.clientOpId)).toEqual(['p1', 'p2', 'p3']);
  });

  it('does not mutate the input array', () => {
    const ops = [op({ clientOpId: 'a', retries: 0 }), op({ clientOpId: 'b', retries: 1 })];
    const snapshot = ops.map((o) => o.clientOpId);
    summariseQueue(ops);
    expect(ops.map((o) => o.clientOpId)).toEqual(snapshot);
  });
});

describe('sortForReview', () => {
  it('breaks ties deterministically on clientOpId', () => {
    const sorted = sortForReview([
      item({ clientOpId: 'b', queuedAt: 100, status: 'pending' }),
      item({ clientOpId: 'a', queuedAt: 100, status: 'pending' }),
    ]);
    expect(sorted.map((i) => i.clientOpId)).toEqual(['a', 'b']);
  });
});

describe('groupByKind', () => {
  it('buckets items by kind with friendly labels and a failing tally', () => {
    const groups = groupByKind([
      item({ clientOpId: 'a', kind: 'field.diary.entry', status: 'pending', queuedAt: 10 }),
      item({ clientOpId: 'b', kind: 'field.crew.punch', status: 'failing', retries: 2, queuedAt: 20 }),
      item({ clientOpId: 'c', kind: 'field.crew.punch', status: 'pending', queuedAt: 30 }),
    ]);
    // crew.punch group leads because it contains the failing item (sort: failing first).
    expect(groups.map((g) => g.kind)).toEqual(['field.crew.punch', 'field.diary.entry']);
    const punch = groups[0]!;
    expect(punch.label).toBe('Crew punch');
    expect(punch.items).toHaveLength(2);
    expect(punch.failing).toBe(1);
  });
});

describe('formatRelativeTime', () => {
  const NOW = 1_000_000_000;
  it('shows "just now" within 45 seconds', () => {
    expect(formatRelativeTime(NOW - 5_000, NOW)).toBe('just now');
  });
  it('shows minutes', () => {
    expect(formatRelativeTime(NOW - 5 * 60_000, NOW)).toBe('5 min ago');
  });
  it('shows hours', () => {
    expect(formatRelativeTime(NOW - 3 * 3_600_000, NOW)).toBe('3 h ago');
  });
  it('shows days', () => {
    expect(formatRelativeTime(NOW - 2 * 86_400_000, NOW)).toBe('2 d ago');
  });
  it('clamps a future timestamp (clock skew) to "just now"', () => {
    expect(formatRelativeTime(NOW + 10_000, NOW)).toBe('just now');
  });
});

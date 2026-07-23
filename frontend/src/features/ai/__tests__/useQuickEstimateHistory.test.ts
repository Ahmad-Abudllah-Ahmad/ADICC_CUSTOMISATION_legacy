// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
// OpenConstructionERP — DataDrivenConstruction (DDC)
// Tests for the Quick-Estimate history hook + its storage helpers.
import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import {
  HISTORY_KEY_PREFIX,
  HISTORY_MAX,
  HISTORY_SCHEMA_VERSION,
  historyStorageKey,
  lruInsert,
  readHistory,
  useQuickEstimateHistory,
  writeHistory,
  type HistoryEntry,
} from '../useQuickEstimateHistory';
import { useAuthStore } from '@/stores/useAuthStore';

function entry(id: string, overrides: Partial<HistoryEntry> = {}): HistoryEntry {
  return {
    id,
    createdAt: '2026-05-20T12:00:00.000Z',
    prompt: 'Apartment building, 1200 m², Berlin',
    result: null,
    model: 'claude-sonnet',
    costUsd: 0,
    durationMs: 1234,
    status: 'ok',
    ...overrides,
  };
}

beforeEach(() => {
  window.localStorage.clear();
  // Reset the auth store before each test so user-keyed storage starts clean.
  useAuthStore.setState({
    accessToken: null,
    isAuthenticated: false,
    userEmail: null,
    userRole: null,
  });
});

describe('historyStorageKey', () => {
  it('builds a per-user key from the email and falls back to anonymous', () => {
    expect(historyStorageKey('alice@example.com')).toBe(
      `${HISTORY_KEY_PREFIX}alice@example.com`,
    );
    expect(historyStorageKey(null)).toBe(`${HISTORY_KEY_PREFIX}anonymous`);
    expect(historyStorageKey('   ')).toBe(`${HISTORY_KEY_PREFIX}anonymous`);
  });
});

describe('lruInsert', () => {
  it('prepends new entries and caps at HISTORY_MAX', () => {
    let list: HistoryEntry[] = [];
    for (let i = 0; i < HISTORY_MAX + 5; i++) {
      list = lruInsert(list, entry(`id-${i}`));
    }
    expect(list).toHaveLength(HISTORY_MAX);
    // Newest at front.
    expect(list[0]!.id).toBe(`id-${HISTORY_MAX + 4}`);
    // Oldest 5 should have been evicted.
    expect(list.find((e) => e.id === 'id-0')).toBeUndefined();
  });

  it('dedupes when re-appending the same id (moves to front)', () => {
    let list: HistoryEntry[] = [
      entry('a'),
      entry('b'),
      entry('c'),
    ];
    list = lruInsert(list, entry('b', { prompt: 'updated' }));
    expect(list.map((e) => e.id)).toEqual(['b', 'a', 'c']);
    expect(list[0]!.prompt).toBe('updated');
  });
});

describe('readHistory storage fallback', () => {
  const key = `${HISTORY_KEY_PREFIX}test`;

  it('returns [] when the value is unparseable JSON (corruption fallback)', () => {
    window.localStorage.setItem(key, '<<not json>>');
    expect(readHistory(key)).toEqual([]);
  });

  it('returns [] when the schema version does not match', () => {
    window.localStorage.setItem(
      key,
      JSON.stringify({ v: HISTORY_SCHEMA_VERSION + 99, entries: [entry('a')] }),
    );
    expect(readHistory(key)).toEqual([]);
  });

  it('returns [] when the envelope shape is wrong', () => {
    window.localStorage.setItem(key, JSON.stringify({ v: HISTORY_SCHEMA_VERSION, entries: 'not-an-array' }));
    expect(readHistory(key)).toEqual([]);
  });

  it('strips malformed entries but keeps valid ones', () => {
    window.localStorage.setItem(
      key,
      JSON.stringify({
        v: HISTORY_SCHEMA_VERSION,
        entries: [entry('good'), { bogus: true }, null, entry('alsoGood')],
      }),
    );
    const out = readHistory(key);
    expect(out.map((e) => e.id)).toEqual(['good', 'alsoGood']);
  });
});

describe('useQuickEstimateHistory', () => {
  beforeEach(() => {
    useAuthStore.setState({
      accessToken: 'token',
      isAuthenticated: true,
      userEmail: 'alice@example.com',
      userRole: 'estimator',
    });
  });

  it('appends entries and persists to localStorage', () => {
    const { result } = renderHook(() => useQuickEstimateHistory());

    act(() => {
      result.current.append(entry('e1', { prompt: 'first' }));
      result.current.append(entry('e2', { prompt: 'second' }));
    });

    // Newest-first.
    expect(result.current.history.map((e) => e.id)).toEqual(['e2', 'e1']);
    // Persisted.
    const stored = readHistory(historyStorageKey('alice@example.com'));
    expect(stored.map((e) => e.id)).toEqual(['e2', 'e1']);
  });

  it('enforces LRU eviction at HISTORY_MAX', () => {
    const { result } = renderHook(() => useQuickEstimateHistory());

    act(() => {
      for (let i = 0; i < HISTORY_MAX + 3; i++) {
        result.current.append(entry(`id-${i}`));
      }
    });

    expect(result.current.history).toHaveLength(HISTORY_MAX);
    // Oldest few should be gone.
    expect(result.current.history.find((e) => e.id === 'id-0')).toBeUndefined();
    expect(result.current.history.find((e) => e.id === 'id-1')).toBeUndefined();
    expect(result.current.history.find((e) => e.id === 'id-2')).toBeUndefined();
  });

  it('restore() returns the matching entry, undefined when missing', () => {
    const { result } = renderHook(() => useQuickEstimateHistory());

    act(() => {
      result.current.append(entry('saved', { prompt: 'restore-me' }));
    });

    expect(result.current.restore('saved')?.prompt).toBe('restore-me');
    expect(result.current.restore('nope')).toBeUndefined();
  });

  it('clear() wipes both state and persisted storage', () => {
    const { result } = renderHook(() => useQuickEstimateHistory());

    act(() => {
      result.current.append(entry('e1'));
      result.current.append(entry('e2'));
    });
    expect(result.current.history).toHaveLength(2);

    act(() => {
      result.current.clear();
    });

    expect(result.current.history).toEqual([]);
    expect(window.localStorage.getItem(historyStorageKey('alice@example.com'))).toBe(
      JSON.stringify({ v: HISTORY_SCHEMA_VERSION, entries: [] }),
    );
  });

  it('falls back gracefully when storage holds corrupt data on mount', () => {
    writeHistory(historyStorageKey('alice@example.com'), [entry('seeded')]);
    // Corrupt it.
    window.localStorage.setItem(historyStorageKey('alice@example.com'), '<corrupt>');

    const { result } = renderHook(() => useQuickEstimateHistory());
    // Corrupt payload → empty list, no throw.
    expect(result.current.history).toEqual([]);

    // We can still append after the fallback.
    act(() => {
      result.current.append(entry('fresh'));
    });
    expect(result.current.history.map((e) => e.id)).toEqual(['fresh']);
  });

  it('ignores history written under a different schema version', () => {
    // Pretend a future version wrote v999 entries; current hook must
    // discard them rather than mis-rendering.
    window.localStorage.setItem(
      historyStorageKey('alice@example.com'),
      JSON.stringify({ v: HISTORY_SCHEMA_VERSION + 7, entries: [entry('old')] }),
    );

    const { result } = renderHook(() => useQuickEstimateHistory());
    expect(result.current.history).toEqual([]);
  });
});

// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Tests for `clashFilterPersistence` — load/save/LRU/version-mismatch.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  EMPTY_FILTERS,
  FILTER_SCHEMA_VERSION,
  MAX_PROJECTS,
  PERSIST_DEBOUNCE_MS,
  coerceFilters,
  createDebouncedPersist,
  evictBeyondLimit,
  filterKey,
  loadFilters,
  lruKey,
  readLRUForTest,
  saveFilters,
  touchLRU,
  type ClashFilterState,
} from '../clashFilterPersistence';

const PROJECT_A = '00000000-0000-0000-0000-00000000000a';
const PROJECT_B = '00000000-0000-0000-0000-00000000000b';

function aFilters(): ClashFilterState {
  return {
    severity: ['critical', 'high'],
    status: ['new', 'reviewed'],
    discipline: ['Mechanical|Structural'],
    sortBy: 'severity',
  };
}

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  window.localStorage.clear();
  vi.useRealTimers();
});

describe('coerceFilters', () => {
  it('returns null on null / non-object input', () => {
    expect(coerceFilters(null)).toBeNull();
    expect(coerceFilters('hi')).toBeNull();
    expect(coerceFilters(42)).toBeNull();
  });

  it('returns null on a mismatched schema version', () => {
    expect(
      coerceFilters({ v: 999, filters: aFilters(), updatedAt: 0 }),
    ).toBeNull();
  });

  it('drops non-string entries from each array', () => {
    const out = coerceFilters({
      v: FILTER_SCHEMA_VERSION,
      filters: {
        // 42 is poison — must be filtered out, not crash the page.
        severity: ['critical', 42, null, 'low'],
        status: ['new'],
        discipline: [],
        sortBy: 'idx',
      },
      updatedAt: 0,
    });
    expect(out).toEqual({
      severity: ['critical', 'low'],
      status: ['new'],
      discipline: [],
      sortBy: 'idx',
    });
  });

  it('defaults `sortBy` to "idx" when empty / non-string', () => {
    const out = coerceFilters({
      v: FILTER_SCHEMA_VERSION,
      filters: { severity: [], status: [], discipline: [], sortBy: '' },
      updatedAt: 0,
    });
    expect(out?.sortBy).toBe('idx');
  });
});

describe('saveFilters / loadFilters - hydrate round-trip', () => {
  it('writes and reads back identical filter state', () => {
    const original = aFilters();
    saveFilters(PROJECT_A, original);
    const loaded = loadFilters(PROJECT_A);
    expect(loaded).toEqual(original);
  });

  it('returns EMPTY_FILTERS when no entry exists for the project', () => {
    const loaded = loadFilters(PROJECT_A);
    expect(loaded).toEqual(EMPTY_FILTERS);
  });

  it('round-trips empty severity / status / discipline arrays cleanly', () => {
    const empty: ClashFilterState = {
      severity: [],
      status: [],
      discipline: [],
      sortBy: 'discipline',
    };
    saveFilters(PROJECT_A, empty);
    expect(loadFilters(PROJECT_A)).toEqual(empty);
  });

  it('hydrate updates the LRU index (moves the project to the head)', () => {
    saveFilters(PROJECT_A, aFilters());
    saveFilters(PROJECT_B, aFilters());
    // After loadFilters(PROJECT_A), A is most-recently-used.
    loadFilters(PROJECT_A);
    expect(readLRUForTest()).toEqual([PROJECT_A, PROJECT_B]);
  });
});

describe('version mismatch fallback', () => {
  it('an entry with the wrong schema version is dropped + EMPTY returned', () => {
    // Hand-craft a "future" envelope at v=999. coerceFilters will reject
    // it and loadFilters must wipe the stale key so it's not re-tried.
    window.localStorage.setItem(
      filterKey(PROJECT_A),
      JSON.stringify({
        v: 999,
        filters: aFilters(),
        updatedAt: Date.now(),
      }),
    );
    const loaded = loadFilters(PROJECT_A);
    expect(loaded).toEqual(EMPTY_FILTERS);
    // The stale key is gone — a second load will not parse it again.
    expect(window.localStorage.getItem(filterKey(PROJECT_A))).toBeNull();
  });

  it('a corrupted (non-JSON) entry falls back to EMPTY without throwing', () => {
    window.localStorage.setItem(filterKey(PROJECT_A), '{{{ not json');
    expect(() => loadFilters(PROJECT_A)).not.toThrow();
    expect(loadFilters(PROJECT_A)).toEqual(EMPTY_FILTERS);
  });
});

describe('LRU eviction', () => {
  it('keeps only the MAX_PROJECTS newest project blobs', () => {
    // Save MAX_PROJECTS + 2 distinct projects. The oldest two are evicted.
    const ids: string[] = [];
    for (let i = 0; i < MAX_PROJECTS + 2; i++) {
      const id = `proj-${String(i).padStart(4, '0')}`;
      ids.push(id);
      saveFilters(id, aFilters());
    }
    const lru = readLRUForTest();
    expect(lru.length).toBe(MAX_PROJECTS);
    // First-saved (oldest) ids no longer in storage; their blobs gone too.
    const evicted = ids.slice(0, ids.length - MAX_PROJECTS);
    const kept = ids.slice(ids.length - MAX_PROJECTS);
    for (const id of evicted) {
      expect(window.localStorage.getItem(filterKey(id))).toBeNull();
      expect(lru).not.toContain(id);
    }
    for (const id of kept) {
      expect(window.localStorage.getItem(filterKey(id))).not.toBeNull();
    }
  });

  it('touchLRU promotes an existing project to the head without dups', () => {
    saveFilters(PROJECT_A, aFilters());
    saveFilters(PROJECT_B, aFilters());
    // Currently B is newest. Touching A moves it to the head.
    touchLRU(PROJECT_A);
    expect(readLRUForTest()).toEqual([PROJECT_A, PROJECT_B]);
    // Touching A again does not duplicate the entry.
    touchLRU(PROJECT_A);
    const lru = readLRUForTest();
    expect(lru.filter((x) => x === PROJECT_A).length).toBe(1);
  });

  it('evictBeyondLimit is a no-op when count <= MAX_PROJECTS', () => {
    saveFilters(PROJECT_A, aFilters());
    saveFilters(PROJECT_B, aFilters());
    evictBeyondLimit();
    expect(readLRUForTest()).toEqual([PROJECT_B, PROJECT_A]);
    expect(window.localStorage.getItem(filterKey(PROJECT_A))).not.toBeNull();
    expect(window.localStorage.getItem(filterKey(PROJECT_B))).not.toBeNull();
  });
});

describe('createDebouncedPersist', () => {
  it('coalesces rapid changes into one write after the debounce window', () => {
    vi.useFakeTimers();
    const dp = createDebouncedPersist();
    const filters = aFilters();
    dp.schedule(PROJECT_A, { ...filters, severity: ['low'] });
    dp.schedule(PROJECT_A, { ...filters, severity: ['medium'] });
    dp.schedule(PROJECT_A, { ...filters, severity: ['high'] });

    // Nothing has been written yet — the timer hasn't fired.
    expect(window.localStorage.getItem(filterKey(PROJECT_A))).toBeNull();

    vi.advanceTimersByTime(PERSIST_DEBOUNCE_MS + 1);

    const loaded = loadFilters(PROJECT_A);
    // Only the most-recent value survives — the prior two were coalesced.
    expect(loaded.severity).toEqual(['high']);
  });

  it('cancel() drops the pending write without persisting it', () => {
    vi.useFakeTimers();
    const dp = createDebouncedPersist();
    dp.schedule(PROJECT_A, aFilters());
    dp.cancel();
    vi.advanceTimersByTime(PERSIST_DEBOUNCE_MS + 1);
    expect(window.localStorage.getItem(filterKey(PROJECT_A))).toBeNull();
  });

  it('flush() persists immediately + clears the pending timer', () => {
    vi.useFakeTimers();
    const dp = createDebouncedPersist();
    dp.schedule(PROJECT_A, aFilters());
    dp.flush();
    expect(window.localStorage.getItem(filterKey(PROJECT_A))).not.toBeNull();
    // Advancing time after flush must not double-write.
    vi.advanceTimersByTime(PERSIST_DEBOUNCE_MS + 1);
    const loaded = loadFilters(PROJECT_A);
    expect(loaded).toEqual(aFilters());
  });
});

describe('lruKey is a stable constant', () => {
  it('exposes a stable key name so external migrations can target it', () => {
    expect(lruKey).toBe('clash_filters_lru_v1');
  });
});

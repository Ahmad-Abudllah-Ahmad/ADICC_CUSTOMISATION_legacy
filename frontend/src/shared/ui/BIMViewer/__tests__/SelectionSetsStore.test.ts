/** 
 * SelectionSetsStore unit tests — v3.13.0 W6.6.
 *
 * Covers the contract of the localStorage-backed selection-set store:
 *   - create / list / update / delete CRUD
 *   - per-model 50-cap throws a clear error
 *   - per-set 10000-element cap truncates and warns
 *   - subscriber notifications fire on every mutation
 *   - cross-tab sync re-notifies on a foreign ``storage`` event
 *   - name and note validation reject empty / over-long input
 */
import { beforeEach, describe, expect, it, vi, afterEach } from 'vitest';
import {
  SelectionSetsStore,
  selectionSetsStore,
  __test__,
} from '../SelectionSetsStore';

const MODEL = 'model-test';
const OTHER_MODEL = 'model-other';

function freshStore(): SelectionSetsStore {
  // Each test gets its own instance so subscriber bookkeeping doesn't leak
  // across cases. We still hammer the same singleton key in localStorage —
  // ``beforeEach`` clears it so the read path always starts empty.
  return new SelectionSetsStore();
}

describe('SelectionSetsStore', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('singleton is exported', () => {
    expect(selectionSetsStore).toBeInstanceOf(SelectionSetsStore);
  });

  it('list returns an empty array for an unseen model', () => {
    const store = freshStore();
    expect(store.list(MODEL)).toEqual([]);
  });

  it('create then list returns the new set', () => {
    const store = freshStore();
    const set = store.create(MODEL, 'Level 3 Columns', ['e1', 'e2', 'e3']);
    expect(set.id).toBeTruthy();
    expect(set.modelId).toBe(MODEL);
    expect(set.elementIds).toEqual(['e1', 'e2', 'e3']);
    expect(store.list(MODEL)).toHaveLength(1);
    expect(store.list(MODEL)[0]?.name).toBe('Level 3 Columns');
  });

  it('create deduplicates element ids in input order', () => {
    const store = freshStore();
    const set = store.create(MODEL, 'Walls', ['a', 'b', 'a', 'c', 'b']);
    expect(set.elementIds).toEqual(['a', 'b', 'c']);
  });

  it('create persists to localStorage under the canonical key', () => {
    const store = freshStore();
    store.create(MODEL, 'set-x', ['e1']);
    const raw = localStorage.getItem(__test__.STORAGE_KEY);
    expect(raw).toContain('set-x');
    expect(raw).toContain('e1');
  });

  it('update mutates the targeted set and bumps updatedAt', async () => {
    const store = freshStore();
    const set = store.create(MODEL, 'original', ['e1']);
    const originalUpdatedAt = set.updatedAt;
    // Force a slightly later clock so the ISO string changes.
    await new Promise((r) => setTimeout(r, 5));
    const updated = store.update(set.id, {
      name: 'renamed',
      color: '#ff0000',
      note: 'a note',
      elementIds: ['e2', 'e3'],
    });
    expect(updated.name).toBe('renamed');
    expect(updated.color).toBe('#ff0000');
    expect(updated.note).toBe('a note');
    expect(updated.elementIds).toEqual(['e2', 'e3']);
    expect(updated.createdAt).toBe(set.createdAt);
    expect(updated.updatedAt >= originalUpdatedAt).toBe(true);
  });

  it('update throws when the id is not found', () => {
    const store = freshStore();
    expect(() => store.update('nope', { name: 'x' })).toThrow(/not found/);
  });

  it('delete removes the set; list no longer contains it', () => {
    const store = freshStore();
    const a = store.create(MODEL, 'A', ['e1']);
    const b = store.create(MODEL, 'B', ['e2']);
    store.delete(a.id);
    const remaining = store.list(MODEL);
    expect(remaining.map((s) => s.id)).toEqual([b.id]);
  });

  it('delete is a silent no-op for unknown ids', () => {
    const store = freshStore();
    store.create(MODEL, 'A', ['e1']);
    expect(() => store.delete('not-a-real-id')).not.toThrow();
    expect(store.list(MODEL)).toHaveLength(1);
  });

  it('enforces the 50-sets-per-model cap', () => {
    const store = freshStore();
    for (let i = 0; i < __test__.MAX_SETS_PER_MODEL; i++) {
      store.create(MODEL, `set-${i}`, [`e${i}`]);
    }
    expect(store.list(MODEL)).toHaveLength(__test__.MAX_SETS_PER_MODEL);
    expect(() => store.create(MODEL, 'overflow', ['e-overflow'])).toThrow(/50/);
  });

  it('truncates element ids past the 10000 cap and warns', () => {
    const store = freshStore();
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const oversized: string[] = [];
    for (let i = 0; i < __test__.MAX_ELEMENT_IDS_PER_SET + 50; i++) {
      oversized.push(`e${i}`);
    }
    const set = store.create(MODEL, 'big', oversized);
    expect(set.elementIds).toHaveLength(__test__.MAX_ELEMENT_IDS_PER_SET);
    expect(warn).toHaveBeenCalled();
    const msg = warn.mock.calls[0]?.[0] as string;
    expect(msg).toContain('truncated');
  });

  it('validates name: empty trims to empty and throws', () => {
    const store = freshStore();
    expect(() => store.create(MODEL, '   ', ['e1'])).toThrow(/empty/);
  });

  it('validates name: max length 60', () => {
    const store = freshStore();
    const longName = 'a'.repeat(__test__.NAME_MAX + 1);
    expect(() => store.create(MODEL, longName, ['e1'])).toThrow(/60/);
  });

  it('validates note: rejects payload longer than 200 chars', () => {
    const store = freshStore();
    const longNote = 'n'.repeat(__test__.NOTE_MAX + 1);
    expect(() => store.create(MODEL, 'ok', ['e1'], { note: longNote })).toThrow(/200/);
  });

  it('namespaces sets per model', () => {
    const store = freshStore();
    store.create(MODEL, 'a', ['e1']);
    store.create(OTHER_MODEL, 'b', ['e2']);
    expect(store.list(MODEL)).toHaveLength(1);
    expect(store.list(OTHER_MODEL)).toHaveLength(1);
    expect(store.list(MODEL)[0]?.name).toBe('a');
    expect(store.list(OTHER_MODEL)[0]?.name).toBe('b');
  });

  it('subscribe is called on create / update / delete', () => {
    const store = freshStore();
    const cb = vi.fn();
    const unsubscribe = store.subscribe(cb);
    const s = store.create(MODEL, 'x', ['e1']);
    expect(cb).toHaveBeenCalledTimes(1);
    store.update(s.id, { name: 'y' });
    expect(cb).toHaveBeenCalledTimes(2);
    store.delete(s.id);
    expect(cb).toHaveBeenCalledTimes(3);
    unsubscribe();
    store.create(MODEL, 'z', ['e2']);
    expect(cb).toHaveBeenCalledTimes(3);
  });

  it('cross-tab: storage event triggers subscriber notifications', () => {
    const store = freshStore();
    const cb = vi.fn();
    store.subscribe(cb);
    // Simulate another tab writing to the same key.
    const evt = new StorageEvent('storage', {
      key: __test__.STORAGE_KEY,
      newValue: JSON.stringify({}),
    });
    window.dispatchEvent(evt);
    expect(cb).toHaveBeenCalledTimes(1);
  });

  it('cross-tab: ignores storage events for unrelated keys', () => {
    const store = freshStore();
    const cb = vi.fn();
    store.subscribe(cb);
    const evt = new StorageEvent('storage', {
      key: 'some-other-key',
      newValue: 'whatever',
    });
    window.dispatchEvent(evt);
    expect(cb).not.toHaveBeenCalled();
  });

  it('survives a corrupted localStorage payload', () => {
    localStorage.setItem(__test__.STORAGE_KEY, 'not-json');
    const store = freshStore();
    expect(store.list(MODEL)).toEqual([]);
    // And we should still be able to write a fresh set on top of it.
    const s = store.create(MODEL, 'fresh', ['e1']);
    expect(s.elementIds).toEqual(['e1']);
  });

  // ── Folders (B4) ─────────────────────────────────────────────────────

  it('create stores a trimmed folder label', () => {
    const store = freshStore();
    const set = store.create(MODEL, 'A', ['e1'], { folder: '  Fire safety  ' });
    expect(set.folder).toBe('Fire safety');
    expect(store.list(MODEL)[0]?.folder).toBe('Fire safety');
  });

  it('create treats a blank folder as ungrouped (undefined)', () => {
    const store = freshStore();
    const set = store.create(MODEL, 'A', ['e1'], { folder: '   ' });
    expect(set.folder).toBeUndefined();
  });

  it('create rejects a folder longer than the name cap', () => {
    const store = freshStore();
    const longFolder = 'f'.repeat(__test__.NAME_MAX + 1);
    expect(() =>
      store.create(MODEL, 'A', ['e1'], { folder: longFolder }),
    ).toThrow(/folder/i);
  });

  it('update can set, change and clear a folder', () => {
    const store = freshStore();
    const set = store.create(MODEL, 'A', ['e1']);
    expect(set.folder).toBeUndefined();
    const moved = store.update(set.id, { folder: 'Zone A' });
    expect(moved.folder).toBe('Zone A');
    const renamed = store.update(set.id, { folder: '  Zone B  ' });
    expect(renamed.folder).toBe('Zone B');
    const cleared = store.update(set.id, { folder: '' });
    expect(cleared.folder).toBeUndefined();
  });

  it('update leaves the folder untouched when the patch omits it', () => {
    const store = freshStore();
    const set = store.create(MODEL, 'A', ['e1'], { folder: 'Keep me' });
    const updated = store.update(set.id, { name: 'A renamed' });
    expect(updated.folder).toBe('Keep me');
  });

  it('update rejects a folder longer than the name cap', () => {
    const store = freshStore();
    const set = store.create(MODEL, 'A', ['e1']);
    const longFolder = 'f'.repeat(__test__.NAME_MAX + 1);
    expect(() => store.update(set.id, { folder: longFolder })).toThrow(/folder/i);
  });

  it('persists and reloads the folder across store instances', () => {
    const store = freshStore();
    store.create(MODEL, 'A', ['e1'], { folder: 'Level 3' });
    // A fresh instance reads the same localStorage key.
    const reloaded = freshStore();
    expect(reloaded.list(MODEL)[0]?.folder).toBe('Level 3');
  });
});

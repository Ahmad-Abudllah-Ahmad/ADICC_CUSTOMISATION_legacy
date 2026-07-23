// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/** 
 * SelectionSetsPanel UI tests — v3.13.0 W6.6.
 *
 * Renders the panel against a mocked SelectionManager (just an object with
 * the two methods the panel touches: ``getSelectedIds`` / ``selectByIds``)
 * and the real SelectionSetsStore singleton, with localStorage cleared
 * between cases. Each test asserts that the user-visible flow round-trips:
 *   - the create button enables only when something is selected
 *   - clicking Save with N ids → store gets a new set with those ids
 *   - Restore on a row → selectByIds called with exclusive=true
 *   - Delete row → confirm appears → confirm click removes the row
 *   - Rename inline: double-click → input → Enter → store.update fires
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import SelectionSetsPanel from '../SelectionSetsPanel';
import {
  selectionSetsStore,
  __test__,
} from '@/shared/ui/BIMViewer/SelectionSetsStore';
import type { SelectionManager } from '@/shared/ui/BIMViewer';

const MODEL_ID = 'model-abc';

function buildMockManager(initialIds: string[] = []): {
  manager: SelectionManager;
  getSelectedIds: ReturnType<typeof vi.fn>;
  selectByIds: ReturnType<typeof vi.fn>;
} {
  let ids = [...initialIds];
  const getSelectedIds = vi.fn(() => [...ids]);
  const selectByIds = vi.fn(
    (newIds: string[], options?: { exclusive?: boolean }) => {
      if (options?.exclusive === false) {
        const set = new Set(ids);
        for (const i of newIds) set.add(i);
        ids = Array.from(set);
      } else {
        ids = [...newIds];
      }
    },
  );
  const manager = {
    getSelectedIds,
    selectByIds,
  } as unknown as SelectionManager;
  return { manager, getSelectedIds, selectByIds };
}

describe('SelectionSetsPanel', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('renders empty state with no-selection hint', () => {
    const { manager } = buildMockManager([]);
    render(<SelectionSetsPanel modelId={MODEL_ID} selectionManager={manager} />);
    expect(screen.getByTestId('bim-selection-sets-panel')).toBeInTheDocument();
    expect(screen.getByTestId('bim-selection-sets-empty')).toBeInTheDocument();
    const saveBtn = screen.getByTestId('bim-selection-set-save-new');
    expect(saveBtn).toBeDisabled();
  });

  it('save-new is enabled once selection is non-empty', async () => {
    const { manager } = buildMockManager(['e1', 'e2', 'e3']);
    render(<SelectionSetsPanel modelId={MODEL_ID} selectionManager={manager} />);
    // The panel polls selection at 500ms — advance a tick by forcing a
    // re-read via clicking nothing and waiting one micro-task. We can't
    // easily fast-forward setInterval in JSDOM without modern fake timers,
    // but the initial useEffect runs once and primes the count.
    // The mock manager has 3 selected ids from the start, so the count
    // should be 3 already.
    const btn = screen.getByTestId('bim-selection-set-save-new');
    expect(btn).not.toBeDisabled();
  });

  it('Save-new flow creates a set with currently selected ids', async () => {
    const { manager, getSelectedIds } = buildMockManager(['e1', 'e2', 'e3']);
    render(<SelectionSetsPanel modelId={MODEL_ID} selectionManager={manager} />);
    fireEvent.click(screen.getByTestId('bim-selection-set-save-new'));
    const input = screen.getByTestId('bim-selection-set-name-input');
    fireEvent.change(input, { target: { value: 'Level 3 Columns' } });
    fireEvent.click(screen.getByTestId('bim-selection-set-create-confirm'));
    // The store should now have a single set with the mocked ids.
    const stored = selectionSetsStore.list(MODEL_ID);
    expect(stored).toHaveLength(1);
    expect(stored[0]?.name).toBe('Level 3 Columns');
    expect(stored[0]?.elementIds).toEqual(['e1', 'e2', 'e3']);
    expect(getSelectedIds).toHaveBeenCalled();
  });

  it('Restore button calls selectByIds with exclusive=true', () => {
    selectionSetsStore.create(MODEL_ID, 'cols', ['c1', 'c2']);
    const { manager, selectByIds } = buildMockManager([]);
    render(<SelectionSetsPanel modelId={MODEL_ID} selectionManager={manager} />);
    const stored = selectionSetsStore.list(MODEL_ID)[0]!;
    fireEvent.click(screen.getByTestId(`bim-selection-set-restore-${stored.id}`));
    expect(selectByIds).toHaveBeenCalledWith(['c1', 'c2'], { exclusive: true });
  });

  it('Add button calls selectByIds with exclusive=false', () => {
    selectionSetsStore.create(MODEL_ID, 'walls', ['w1', 'w2']);
    const { manager, selectByIds } = buildMockManager(['existing-1']);
    render(<SelectionSetsPanel modelId={MODEL_ID} selectionManager={manager} />);
    const stored = selectionSetsStore.list(MODEL_ID)[0]!;
    fireEvent.click(screen.getByTestId(`bim-selection-set-add-${stored.id}`));
    expect(selectByIds).toHaveBeenCalledWith(['w1', 'w2'], { exclusive: false });
  });

  it('Delete row shows confirm, then commit removes the set', () => {
    selectionSetsStore.create(MODEL_ID, 'tmp', ['e1']);
    const { manager } = buildMockManager([]);
    render(<SelectionSetsPanel modelId={MODEL_ID} selectionManager={manager} />);
    const stored = selectionSetsStore.list(MODEL_ID)[0]!;
    expect(
      screen.getByTestId(`bim-selection-set-row-${stored.id}`),
    ).toBeInTheDocument();
    // First click → confirm UI replaces the trash icon.
    fireEvent.click(screen.getByTestId(`bim-selection-set-delete-${stored.id}`));
    const confirm = screen.getByTestId(`bim-selection-set-delete-confirm-${stored.id}`);
    expect(confirm).toBeInTheDocument();
    // Second click → row removed.
    fireEvent.click(confirm);
    expect(selectionSetsStore.list(MODEL_ID)).toHaveLength(0);
    expect(
      screen.queryByTestId(`bim-selection-set-row-${stored.id}`),
    ).not.toBeInTheDocument();
  });

  it('Rename inline: double-click name → input → Enter commits store.update', () => {
    selectionSetsStore.create(MODEL_ID, 'old name', ['e1']);
    const { manager } = buildMockManager([]);
    render(<SelectionSetsPanel modelId={MODEL_ID} selectionManager={manager} />);
    const stored = selectionSetsStore.list(MODEL_ID)[0]!;
    const nameBtn = screen.getByTestId(`bim-selection-set-name-${stored.id}`);
    fireEvent.doubleClick(nameBtn);
    const input = screen.getByTestId(`bim-selection-set-rename-input-${stored.id}`);
    fireEvent.change(input, { target: { value: 'new name' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    const updated = selectionSetsStore.list(MODEL_ID)[0]!;
    expect(updated.name).toBe('new name');
  });

  it('Rename Esc cancels without mutating', () => {
    selectionSetsStore.create(MODEL_ID, 'keep-me', ['e1']);
    const { manager } = buildMockManager([]);
    render(<SelectionSetsPanel modelId={MODEL_ID} selectionManager={manager} />);
    const stored = selectionSetsStore.list(MODEL_ID)[0]!;
    fireEvent.doubleClick(screen.getByTestId(`bim-selection-set-name-${stored.id}`));
    const input = screen.getByTestId(`bim-selection-set-rename-input-${stored.id}`);
    fireEvent.change(input, { target: { value: 'scratch' } });
    fireEvent.keyDown(input, { key: 'Escape' });
    expect(selectionSetsStore.list(MODEL_ID)[0]?.name).toBe('keep-me');
  });

  it('No-model branch renders a hint and no list', () => {
    render(<SelectionSetsPanel modelId={null} selectionManager={null} />);
    expect(screen.getByTestId('bim-selection-sets-panel')).toBeInTheDocument();
    expect(
      screen.queryByTestId('bim-selection-set-save-new'),
    ).not.toBeInTheDocument();
  });

  it('Update button overwrites the set with the current selection', () => {
    selectionSetsStore.create(MODEL_ID, 'before', ['old-1', 'old-2']);
    const { manager } = buildMockManager(['new-1', 'new-2', 'new-3']);
    render(<SelectionSetsPanel modelId={MODEL_ID} selectionManager={manager} />);
    const stored = selectionSetsStore.list(MODEL_ID)[0]!;
    fireEvent.click(screen.getByTestId(`bim-selection-set-update-${stored.id}`));
    const after = selectionSetsStore.list(MODEL_ID)[0]!;
    expect(after.elementIds).toEqual(['new-1', 'new-2', 'new-3']);
  });

  // Silence the unused __test__ import warning so the symbol stays
  // available for ad-hoc debugging in this file.
  it('exposes test caps as constants for store interop', () => {
    expect(__test__.MAX_SETS_PER_MODEL).toBeGreaterThan(0);
  });

  // act() is imported to keep the React 18 happy-path available if a future
  // test needs to flush effects deterministically.
  it('act-wrapped re-render after store mutation refreshes list', () => {
    selectionSetsStore.create(MODEL_ID, 'a', ['e1']);
    const { manager } = buildMockManager([]);
    render(<SelectionSetsPanel modelId={MODEL_ID} selectionManager={manager} />);
    expect(screen.getAllByTestId(/^bim-selection-set-row-/)).toHaveLength(1);
    act(() => {
      selectionSetsStore.create(MODEL_ID, 'b', ['e2']);
    });
    expect(screen.getAllByTestId(/^bim-selection-set-row-/)).toHaveLength(2);
  });

  // ── Folders (B4) ─────────────────────────────────────────────────────

  it('groups sets under folder headers; ungrouped render directly', () => {
    selectionSetsStore.create(MODEL_ID, 'loose', ['e1']);
    selectionSetsStore.create(MODEL_ID, 'filed', ['e2'], { folder: 'Fire' });
    const { manager } = buildMockManager([]);
    render(<SelectionSetsPanel modelId={MODEL_ID} selectionManager={manager} />);
    // Folder header is present for the "Fire" bucket...
    expect(screen.getByTestId('bim-selection-set-folder-Fire')).toBeInTheDocument();
    // ...and the ungrouped bucket holds the loose set.
    expect(
      screen.getByTestId('bim-selection-sets-ungrouped'),
    ).toBeInTheDocument();
    // Both rows render.
    expect(screen.getAllByTestId(/^bim-selection-set-row-/)).toHaveLength(2);
  });

  it('collapsing a folder hides its rows', () => {
    const filed = selectionSetsStore.create(MODEL_ID, 'filed', ['e2'], {
      folder: 'Fire',
    });
    const { manager } = buildMockManager([]);
    render(<SelectionSetsPanel modelId={MODEL_ID} selectionManager={manager} />);
    expect(
      screen.getByTestId(`bim-selection-set-row-${filed.id}`),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('bim-selection-set-folder-toggle-Fire'));
    expect(
      screen.queryByTestId(`bim-selection-set-row-${filed.id}`),
    ).not.toBeInTheDocument();
  });

  it('Save-new flow stores the optional folder', () => {
    const { manager } = buildMockManager(['e1', 'e2']);
    render(<SelectionSetsPanel modelId={MODEL_ID} selectionManager={manager} />);
    fireEvent.click(screen.getByTestId('bim-selection-set-save-new'));
    fireEvent.change(screen.getByTestId('bim-selection-set-name-input'), {
      target: { value: 'Risers' },
    });
    fireEvent.change(screen.getByTestId('bim-selection-set-folder-input'), {
      target: { value: 'MEP' },
    });
    fireEvent.click(screen.getByTestId('bim-selection-set-create-confirm'));
    const stored = selectionSetsStore.list(MODEL_ID);
    expect(stored).toHaveLength(1);
    expect(stored[0]?.folder).toBe('MEP');
  });

  it('move-to-folder: folder button opens an editor that updates the set', () => {
    const set = selectionSetsStore.create(MODEL_ID, 'a', ['e1']);
    const { manager } = buildMockManager([]);
    render(<SelectionSetsPanel modelId={MODEL_ID} selectionManager={manager} />);
    fireEvent.click(
      screen.getByTestId(`bim-selection-set-folder-btn-${set.id}`),
    );
    const input = screen.getByTestId(
      `bim-selection-set-folder-edit-input-${set.id}`,
    );
    fireEvent.change(input, { target: { value: 'Zone A' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(selectionSetsStore.list(MODEL_ID)[0]?.folder).toBe('Zone A');
    // The row now lives under the new folder header.
    expect(
      screen.getByTestId('bim-selection-set-folder-Zone A'),
    ).toBeInTheDocument();
  });
});

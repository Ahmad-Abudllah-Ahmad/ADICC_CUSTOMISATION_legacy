// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Registry of COLLAPSED module info cards on the current page.
 *
 * Founder decision 2026-06-06: when a `DismissibleInfo` card is collapsed
 * (card click or X) it disappears from the page entirely - no leftover
 * "Module information" line in the content flow. Instead a small info icon
 * appears in the TOP APP BAR, right after the module name (project pill >
 * module icon + name > info icon). Clicking that icon re-expands the card.
 *
 * Mechanics: every DismissibleInfo registers itself here while collapsed
 * (key + an `expand` callback) and unregisters when expanded or unmounted,
 * so navigation naturally clears the registry. The Header renders the icon
 * whenever at least one entry exists and fires every entry's `expand` - the
 * canon is one info card per page, so this is a single-card toggle in
 * practice while staying correct for multi-card pages.
 */

import { create } from 'zustand';

export interface CollapsedModuleInfo {
  /** Stable identity - the DismissibleInfo localStorage key. */
  key: string;
  /** Re-expands the owning card (persists the expanded state). */
  expand: () => void;
}

interface ModuleInfoState {
  entries: CollapsedModuleInfo[];
  register: (entry: CollapsedModuleInfo) => void;
  unregister: (key: string) => void;
  /** Expand every collapsed card on the page (top-bar icon click). */
  expandAll: () => void;
}

export const useModuleInfoStore = create<ModuleInfoState>((set, get) => ({
  entries: [],
  register: (entry) =>
    set((s) => ({
      // Replace-on-rekey keeps StrictMode double-mounts and prop updates safe.
      entries: [...s.entries.filter((e) => e.key !== entry.key), entry],
    })),
  unregister: (key) => set((s) => ({ entries: s.entries.filter((e) => e.key !== key) })),
  expandAll: () => {
    // Snapshot first: expand() flips the card to expanded, which unregisters
    // the entry and mutates the array we are iterating.
    const snapshot = [...get().entries];
    snapshot.forEach((e) => e.expand());
  },
}));

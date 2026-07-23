// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * useDashboardFilters — Power BI-style cross-filter state for the BI dashboards page.
 *
 * Wave 4 / T11. A click on a tile/cell that defines a ``drill_path`` shoves
 * a ``{filter_field: filter_value}`` pair into this store, which the page
 * then forwards to ``POST /v1/bi-dashboards/{id}/evaluate`` so every widget
 * is re-evaluated against the new filter.
 *
 * Scoped per ``activeDashboardId`` so navigating to a different dashboard
 * starts with a clean filter slate — chips don't leak across boards.
 * Not persisted: filter state is intentionally session-only; refresh wipes
 * the chips and starts from the dashboard's static aggregate.
 */
import { create } from 'zustand';

export interface DashboardFiltersState {
  /** The dashboard the current filters belong to. null until something is clicked. */
  activeDashboardId: string | null;
  /** Key/value bag of active filters — matches the backend evaluate payload. */
  filters: Record<string, unknown>;

  /** Set the active dashboard. Clears filters when the id changes. */
  setActiveDashboard: (id: string | null) => void;
  /** Insert/overwrite a single filter pair. */
  setFilter: (key: string, value: unknown) => void;
  /** Remove a single filter pair (no-op if absent). */
  removeFilter: (key: string) => void;
  /** Wipe every filter for the active dashboard. */
  clearFilters: () => void;
}

export const useDashboardFilters = create<DashboardFiltersState>((set) => ({
  activeDashboardId: null,
  filters: {},

  setActiveDashboard: (id) =>
    set((s) => {
      if (s.activeDashboardId === id) return s;
      return { activeDashboardId: id, filters: {} };
    }),

  setFilter: (key, value) =>
    set((s) => ({
      filters: { ...s.filters, [key]: value },
    })),

  removeFilter: (key) =>
    set((s) => {
      if (!(key in s.filters)) return s;
      const next = { ...s.filters };
      delete next[key];
      return { filters: next };
    }),

  clearFilters: () => set({ filters: {} }),
}));

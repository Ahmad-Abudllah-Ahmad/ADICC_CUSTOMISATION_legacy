// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * useProjectDetailLayoutStore — user-controlled layout for /projects/:id.
 *
 * Mirrors the API surface of {@link useDashboardLayoutStore} so the two
 * customizers feel identical. The project-detail page mounts a fixed
 * header / tab-bar (page chrome — not customisable) and below it stacks
 * a series of independent content widgets (project info, map+weather,
 * health, BOQ list, RFI inbox, change-orders, daily diary, HSE incidents,
 * budget burn, photo strip, AI insights, etc).
 *
 * Persistence is local-only here — there is no companion server endpoint
 * yet (`/api/v1/users/me/project-detail-layout/` is not implemented). The
 * zustand ``persist`` middleware therefore keeps the value in
 * ``localStorage`` under ``oe.project-detail-layout``; the layout is
 * per-browser, which is good enough for v1. Adding a server-sync mirror
 * later is a drop-in change (copy the syncToServer / hydrate pattern
 * from the dashboard store).
 *
 * The persisted ``order`` is reconciled against the live widget registry
 * at render time via {@link reconcileOrder} (re-exported from
 * useDashboardLayoutStore), so introducing a new widget id in a later
 * release never corrupts a saved layout: unknown ids are dropped,
 * newly-introduced ids are slotted in at their registry index.
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface ProjectDetailLayoutState {
  /** Widget ids in display order. Empty until the user customises. */
  order: string[];
  /** Widget ids the user has hidden. */
  hidden: string[];

  setOrder: (ids: string[]) => void;
  toggleHidden: (id: string) => void;
  show: (id: string) => void;
  hide: (id: string) => void;
  /** Wipe all customisation — back to registry default order, nothing hidden. */
  reset: () => void;
}

export const useProjectDetailLayoutStore = create<ProjectDetailLayoutState>()(
  persist(
    (set) => ({
      order: [],
      hidden: [],

      setOrder: (ids) => set({ order: ids }),
      toggleHidden: (id) =>
        set((s) => ({
          hidden: s.hidden.includes(id)
            ? s.hidden.filter((x) => x !== id)
            : [...s.hidden, id],
        })),
      show: (id) => set((s) => ({ hidden: s.hidden.filter((x) => x !== id) })),
      hide: (id) =>
        set((s) => (s.hidden.includes(id) ? s : { hidden: [...s.hidden, id] })),
      reset: () => set({ order: [], hidden: [] }),
    }),
    {
      name: 'oe.project-detail-layout',
      partialize: (state) => ({ order: state.order, hidden: state.hidden }),
    },
  ),
);

/**
 * Merge a persisted order with the canonical registry order.
 *
 * - Saved ids that no longer exist in the registry are dropped.
 * - Registry ids missing from the saved order are inserted at their
 *   natural registry index (so a freshly-shipped widget shows up where
 *   the code intends, not jammed at the end).
 * - When the saved order is empty (never customised) the registry order
 *   is returned verbatim.
 *
 * Kept colocated with the store (instead of imported from the dashboard
 * one) so the two stores stay decoupled — a future refactor of the
 * dashboard reconcile logic shouldn't break project-detail.
 */
export function reconcileProjectOrder(
  saved: readonly string[],
  registry: readonly string[],
): string[] {
  if (saved.length === 0) return [...registry];

  const known = new Set(registry);
  const result = saved.filter((id) => known.has(id));
  const present = new Set(result);

  registry.forEach((id, idx) => {
    if (present.has(id)) return;
    const at = Math.min(idx, result.length);
    result.splice(at, 0, id);
    present.add(id);
  });

  return result;
}

// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * useDashboardLayoutStore — user-controlled dashboard widget layout.
 *
 * The dashboard is a stack of independent content widgets (KPI ribbon,
 * project cards, analytics, …). This store lets the user reorder them and
 * hide the ones they don't care about.
 *
 * Persistence strategy (2026-05-23):
 *   1. localStorage — written eagerly via zustand `persist` for an instant
 *      first-paint offline fallback.
 *   2. Server (`/api/v1/users/me/dashboard-layout/`) — fetched once on
 *      app boot via ``hydrateFromServer()``; subsequent mutations to
 *      ``order`` / ``hidden`` are debounced 500 ms and PUT back. The
 *      server-side row follows the user across browsers and devices, just
 *      like the sidebar visibility preferences.
 *
 * On boot the server value wins when it has any rows; otherwise the
 * localStorage value is kept (so a brand-new user with a previously
 * customised browser doesn't lose their layout the first time they sign
 * in). Network failures degrade silently — the offline fallback is enough.
 *
 * The persisted `order` is reconciled against the live widget registry at
 * render time via `reconcileOrder`, so adding a new widget in code (or
 * removing one) never corrupts a saved layout: unknown ids are dropped and
 * newly-introduced ids are appended in their registry position.
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { apiGet, apiPut } from '@/shared/lib/api';

interface DashboardLayoutState {
  /** Widget ids in display order. Empty until the user customises. */
  order: string[];
  /** Widget ids the user has hidden. */
  hidden: string[];
  /**
   * Per-widget grid column span on the 6-col dashboard grid, keyed by widget
   * id (2=third, 3=half, 4=two-thirds, 6=full). Missing = registry default.
   * localStorage-only; never synced to the server.
   */
  spans: Record<string, number>;

  setOrder: (ids: string[]) => void;
  setSpan: (id: string, span: number) => void;
  toggleHidden: (id: string) => void;
  show: (id: string) => void;
  hide: (id: string) => void;
  /** Wipe all customisation — back to registry default order, nothing hidden. */
  reset: () => void;

  /** Internal: true once we've successfully fetched server-side state. */
  hydrated: boolean;
  /** Internal: replace local state from server without re-PUTting it. */
  _setFromServer: (order: string[], hidden: string[]) => void;
}

interface ServerLayoutPayload {
  order: string[];
  hidden: string[];
}

/**
 * Widgets hidden out of the box. `weather_site` is an opt-in field widget
 * surfaced via dashboard Customize, not part of the default dashboard, so a
 * fresh layout ships with it hidden. It stays in the registry (and the
 * Customize manager) so the user can add it back in one click.
 */
const DEFAULT_HIDDEN: readonly string[] = ['weather_site'];

/**
 * Suppression flag so the server-driven hydration doesn't immediately
 * fire a PUT back. We flip it ON before calling ``_setFromServer`` and
 * OFF in a microtask, so the debounced syncer (registered via
 * ``zustand.subscribe`` below) sees ``suppressSync = true`` and skips
 * the request.
 */
let suppressSync = false;

export const useDashboardLayoutStore = create<DashboardLayoutState>()(
  persist(
    (set) => ({
      order: [],
      hidden: [...DEFAULT_HIDDEN],
      spans: {},
      hydrated: false,

      setOrder: (ids) => set({ order: ids }),
      setSpan: (id, span) => set((s) => ({ spans: { ...s.spans, [id]: span } })),
      toggleHidden: (id) =>
        set((s) => ({
          hidden: s.hidden.includes(id)
            ? s.hidden.filter((x) => x !== id)
            : [...s.hidden, id],
        })),
      show: (id) => set((s) => ({ hidden: s.hidden.filter((x) => x !== id) })),
      hide: (id) =>
        set((s) => (s.hidden.includes(id) ? s : { hidden: [...s.hidden, id] })),
      reset: () => set({ order: [], hidden: [...DEFAULT_HIDDEN], spans: {} }),

      _setFromServer: (order, hidden) => {
        suppressSync = true;
        set({ order, hidden, hydrated: true });
        // Release the suppression on the next microtask so that any user
        // mutation in the same tick still triggers a sync.
        queueMicrotask(() => {
          suppressSync = false;
        });
      },
    }),
    {
      name: 'oe.dashboard-layout',
      // v1 (2026-05-29): `weather_site` became opt-in. Existing users — who
      // never had it in `hidden` because it used to be visible by default —
      // get it folded into their hidden set so they stop seeing it too. We
      // only ADD `weather_site`; their order + any widgets they themselves
      // hid are preserved untouched, so a genuinely customised layout is not
      // wiped. They can re-add it from Customize.
      version: 1,
      migrate: (persisted, version) => {
        const state = (persisted ?? {}) as Partial<DashboardLayoutState>;
        const order = Array.isArray(state.order) ? state.order : [];
        const hidden = Array.isArray(state.hidden) ? state.hidden : [];
        const spans =
          state.spans && typeof state.spans === 'object'
            ? (state.spans as Record<string, number>)
            : {};
        if (version < 1) {
          const merged = hidden.includes('weather_site')
            ? hidden
            : [...hidden, 'weather_site'];
          return { ...state, order, hidden: merged, spans } as DashboardLayoutState;
        }
        return { ...state, order, hidden, spans } as DashboardLayoutState;
      },
      // ``hydrated`` is runtime-only state, never persist it to localStorage.
      partialize: (state) => ({ order: state.order, hidden: state.hidden, spans: state.spans }),
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
 */
export function reconcileOrder(
  saved: readonly string[],
  registry: readonly string[],
): string[] {
  if (saved.length === 0) return [...registry];

  const known = new Set(registry);
  const result = saved.filter((id) => known.has(id));
  const present = new Set(result);

  registry.forEach((id, idx) => {
    if (present.has(id)) return;
    // Insert at the registry index, clamped to the current length.
    const at = Math.min(idx, result.length);
    result.splice(at, 0, id);
    present.add(id);
  });

  return result;
}

/* ── Server hydration + debounced sync ─────────────────────────────────── */

let hydrationStarted = false;
let pendingTimer: ReturnType<typeof setTimeout> | null = null;
let lastSentPayload = '';

/**
 * One-time marker for the v1 `weather_site` fold against the server-side
 * layout (see `hydrateDashboardLayoutFromServer`). Stored in localStorage so
 * the fold runs at most once per browser — after which a deliberate re-add of
 * the weather widget via Customize is respected and never re-hidden.
 */
const WEATHER_FOLD_KEY = 'oe.dashboard-layout.weather-fold-v1';

function serverWeatherFoldDone(): boolean {
  try {
    return localStorage.getItem(WEATHER_FOLD_KEY) === '1';
  } catch {
    return false;
  }
}

function markServerWeatherFoldDone(): void {
  try {
    localStorage.setItem(WEATHER_FOLD_KEY, '1');
  } catch {
    /* storage unavailable — fold may re-run; harmless and idempotent. */
  }
}

async function syncToServer(state: DashboardLayoutState): Promise<void> {
  const payload: ServerLayoutPayload = {
    order: state.order,
    hidden: state.hidden,
  };
  const serialised = JSON.stringify(payload);
  if (serialised === lastSentPayload) return;
  try {
    await apiPut<ServerLayoutPayload, ServerLayoutPayload>(
      '/v1/users/me/dashboard-layout/',
      payload,
    );
    lastSentPayload = serialised;
  } catch {
    // Network failures degrade silently; localStorage already has the change.
  }
}

/**
 * Subscribe to store changes; debounce writes by 500 ms so a drag-and-drop
 * (which may fire many `setOrder` calls) collapses to one PUT.
 */
useDashboardLayoutStore.subscribe((state, prev) => {
  if (suppressSync) return;
  // Skip if nothing meaningful changed (e.g. ``hydrated`` flag flip).
  if (
    state.order === prev.order &&
    state.hidden === prev.hidden
  ) {
    return;
  }
  if (pendingTimer) clearTimeout(pendingTimer);
  pendingTimer = setTimeout(() => {
    pendingTimer = null;
    void syncToServer(useDashboardLayoutStore.getState());
  }, 500);
});

/**
 * Pull the server-side layout once at app boot.
 *
 * Behaviour:
 *   - If the server returns a non-empty layout, it overwrites the local
 *     state (server wins on initial load — this is what makes the layout
 *     follow the user across browsers).
 *   - If the server returns empty defaults but the user has a local
 *     customisation, the local one is preserved AND pushed up so future
 *     devices see it.
 *   - Network errors / 401 are silent — we keep the localStorage state.
 *
 * Idempotent: safe to call from multiple effects; only the first call
 * actually fires.
 */
export async function hydrateDashboardLayoutFromServer(): Promise<void> {
  if (hydrationStarted) return;
  hydrationStarted = true;

  try {
    const remote = await apiGet<ServerLayoutPayload>(
      '/v1/users/me/dashboard-layout/',
    );
    const remoteHasContent =
      (remote?.order?.length ?? 0) > 0 || (remote?.hidden?.length ?? 0) > 0;
    if (remoteHasContent) {
      const order = remote.order ?? [];
      let hidden = remote.hidden ?? [];
      // One-time v1 fold (2026-05-29): `weather_site` became opt-in. A
      // cross-device user whose server layout predates this change has it
      // visible (absent from `hidden`); fold it in once and push the
      // corrected layout back up. Guarded by a localStorage marker so a
      // later deliberate re-add via Customize is never re-hidden.
      let pushBack = false;
      if (!serverWeatherFoldDone() && !hidden.includes('weather_site')) {
        hidden = [...hidden, 'weather_site'];
        pushBack = true;
      }
      markServerWeatherFoldDone();
      useDashboardLayoutStore.getState()._setFromServer(order, hidden);
      lastSentPayload = JSON.stringify({ order, hidden });
      if (pushBack) {
        // Persist the corrected layout for the user's other devices. Bypass
        // the dedupe guard we just primed by clearing lastSentPayload.
        lastSentPayload = '';
        void syncToServer({ ...useDashboardLayoutStore.getState(), order, hidden });
      }
      return;
    }
    // Server is empty: the local default (already has `weather_site` hidden
    // via the persist migration) stands. Mark the v1 fold done so we never
    // retro-hide it on a later boot, and push the local layout up so this is
    // what the user's next browser sees.
    markServerWeatherFoldDone();
    const local = useDashboardLayoutStore.getState();
    if (local.order.length > 0 || local.hidden.length > 0) {
      void syncToServer(local);
    }
    useDashboardLayoutStore.setState({ hydrated: true });
  } catch {
    // Anonymous / offline — leave localStorage alone.
    useDashboardLayoutStore.setState({ hydrated: true });
  }
}

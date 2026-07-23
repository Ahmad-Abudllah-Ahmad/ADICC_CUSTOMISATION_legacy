// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
/**
 * Catalogue install store — survives navigation.
 *
 * Catalogue snapshots are 200–500 MB and the backend install endpoint runs
 * the download + Qdrant restore synchronously (30–120 s typical). Without
 * this store the user is pinned to /match-elements until the request
 * resolves, and a navigation away aborts the fetch.
 *
 * Mirrors `useBIMUploadStore` deliberately: the floating indicator
 * (`GlobalCatalogueInstallIndicator`) reads from this store, so the user
 * sees the same dock pattern they already know from BIM/DWG uploads.
 *
 * The backend doesn't expose progress events (single sync POST), so the
 * store fakes a smooth indeterminate-style progress bar locally — the
 * real signal is the toast + dock badge that appear on completion.
 */

import { create } from 'zustand';
import { useAuthStore } from '@/stores/useAuthStore';
import { extractErrorMessageFromBody } from '@/shared/lib/api';

/* ── Types ─────────────────────────────────────────────────────────────── */

export type CatalogueInstallStatus = 'downloading' | 'ready' | 'error';

export interface CatalogueInstallJob {
  /** Region id is unique per install — also used as the job id. */
  region: string;
  /** Display label, e.g. "AE · Dubai (AR)". */
  label: string;
  /** ISO-639-1 of the catalogue language; surfaces in the dock subtitle. */
  language: string;
  /** Estimated size in MB; UI shows it next to the bar. */
  sizeMb: number;
  status: CatalogueInstallStatus;
  /** 0–100, simulated ramp; the bar smoothly approaches 95% then waits
   *  for the real response to flip to ready/error. */
  progress: number;
  /** Free-form stage hint, e.g. "Downloading from HuggingFace…". */
  stage: string;
  errorMessage: string | null;
  startedAt: number;
  completedAt: number | null;
}

export interface StartInstallParams {
  region: string;
  label: string;
  language: string;
  sizeMb: number;
}

interface CatalogueInstallState {
  jobs: Map<string, CatalogueInstallJob>;

  startInstall: (
    params: StartInstallParams,
    callbacks?: {
      onSuccess?: (region: string) => void;
      onError?: (region: string, error: string) => void;
    },
  ) => void;
  dismissJob: (region: string) => void;
  clearCompleted: () => void;

  hasActive: () => boolean;
  activeJobs: () => CatalogueInstallJob[];
}

/* ── Internal: progress simulation ─────────────────────────────────────── */

const stageTimers = new Map<string, ReturnType<typeof setInterval>>();

function clearProgressTimer(region: string) {
  const t = stageTimers.get(region);
  if (t) {
    clearInterval(t);
    stageTimers.delete(region);
  }
}

/* ── Store ─────────────────────────────────────────────────────────────── */

export const useCatalogueInstallStore = create<CatalogueInstallState>(
  (set, get) => {
    function patchJob(region: string, patch: Partial<CatalogueInstallJob>) {
      set((state) => {
        const jobs = new Map(state.jobs);
        const existing = jobs.get(region);
        if (!existing) return state;
        jobs.set(region, { ...existing, ...patch });
        return { jobs };
      });
    }

    /** Ramp the bar from 5% → 95% over ~90 s while ALSO advancing the
     *  user-visible stage label. The backend install POST is monolithic
     *  (no streaming), so the FE has no real progress signal — but
     *  watching the bar pin at 95% with no stage change for 5+ minutes
     *  makes the user think it's frozen. We rotate the label through
     *  download / restore / index phases on a wall-clock heuristic so
     *  there's always *something* changing on screen.
     *
     *  Heuristic timings are tuned for a ~400 MB catalogue:
     *    0–20 s : downloading from HuggingFace
     *    20 s–2 m : restoring Qdrant snapshot
     *    2–6 m   : indexing vectors
     *    6 m+    : finalizing (the "this is normal, keep waiting" zone) */
    function startProgressTimer(region: string) {
      let pct = 5;
      const startedAt = Date.now();
      const stageFor = (elapsedMs: number): string => {
        const s = Math.floor(elapsedMs / 1000);
        if (s < 20) return 'catalogue_install.stage_downloading';
        if (s < 120) return 'catalogue_install.stage_restoring';
        if (s < 360) return 'catalogue_install.stage_indexing';
        return 'catalogue_install.stage_finalizing';
      };
      let lastStage = 'catalogue_install.stage_downloading';
      const tick = () => {
        const remaining = 95 - pct;
        if (remaining > 0.3) {
          const step = Math.max(0.2, remaining * 0.025);
          pct = Math.min(95, pct + step);
        }
        const nextStage = stageFor(Date.now() - startedAt);
        const patch: Partial<CatalogueInstallJob> = { progress: Math.round(pct) };
        if (nextStage !== lastStage) {
          patch.stage = nextStage;
          lastStage = nextStage;
        }
        patchJob(region, patch);
      };
      const timer = setInterval(tick, 600);
      stageTimers.set(region, timer);
    }

    async function executeInstall(
      region: string,
      callbacks?: {
        onSuccess?: (region: string) => void;
        onError?: (region: string, error: string) => void;
      },
    ) {
      startProgressTimer(region);
      try {
        const token = useAuthStore.getState().accessToken;
        const res = await fetch(
          `/api/v1/costs/catalogues-v3/${encodeURIComponent(region)}/install`,
          {
            method: 'POST',
            headers: token ? { Authorization: `Bearer ${token}` } : {},
          },
        );
        clearProgressTimer(region);
        if (!res.ok) {
          let detail = `HTTP ${res.status}`;
          try {
            const body = await res.json();
            detail = extractErrorMessageFromBody(body) ?? detail;
          } catch {
            // ignore
          }
          patchJob(region, {
            status: 'error',
            progress: 0,
            stage: 'catalogue_install.stage_failed',
            errorMessage: detail,
            completedAt: Date.now(),
          });
          callbacks?.onError?.(region, detail);
          return;
        }
        patchJob(region, {
          status: 'ready',
          progress: 100,
          stage: 'catalogue_install.stage_done',
          completedAt: Date.now(),
        });
        callbacks?.onSuccess?.(region);
      } catch (err) {
        clearProgressTimer(region);
        const msg = err instanceof Error ? err.message : String(err);
        patchJob(region, {
          status: 'error',
          progress: 0,
          stage: 'catalogue_install.stage_failed',
          errorMessage: msg,
          completedAt: Date.now(),
        });
        callbacks?.onError?.(region, msg);
      }
    }

    return {
      jobs: new Map(),

      startInstall: (params, callbacks) => {
        // Coalesce: if the same region is already in flight, do nothing.
        const existing = get().jobs.get(params.region);
        if (existing && existing.status === 'downloading') return;

        const job: CatalogueInstallJob = {
          region: params.region,
          label: params.label,
          language: params.language,
          sizeMb: params.sizeMb,
          status: 'downloading',
          progress: 5,
          stage: 'catalogue_install.stage_downloading',
          errorMessage: null,
          startedAt: Date.now(),
          completedAt: null,
        };

        set((state) => {
          const jobs = new Map(state.jobs);
          jobs.set(params.region, job);
          return { jobs };
        });

        void executeInstall(params.region, callbacks);
      },

      dismissJob: (region) => {
        clearProgressTimer(region);
        set((state) => {
          const jobs = new Map(state.jobs);
          jobs.delete(region);
          return { jobs };
        });
      },

      clearCompleted: () => {
        set((state) => {
          const jobs = new Map(state.jobs);
          for (const [id, job] of jobs) {
            if (job.status === 'ready' || job.status === 'error') {
              jobs.delete(id);
            }
          }
          return { jobs };
        });
      },

      hasActive: () => {
        for (const j of get().jobs.values()) {
          if (j.status === 'downloading') return true;
        }
        return false;
      },

      activeJobs: () => {
        const out: CatalogueInstallJob[] = [];
        for (const j of get().jobs.values()) {
          if (j.status === 'downloading') out.push(j);
        }
        return out;
      },
    };
  },
);

/* ── Zombie sweeper ────────────────────────────────────────────────────────
 *
 * If the install POST hangs (proxy disconnect, browser tab throttled)
 * the dock would otherwise sit on "Downloading" forever. After 10 min flip
 * abandoned jobs to error so the indicator clears and the user can retry. */
if (typeof window !== 'undefined') {
  const MAX_ACTIVE_MS = 10 * 60 * 1000;
  setInterval(() => {
    const state = useCatalogueInstallStore.getState();
    const now = Date.now();
    let dirty = false;
    const next = new Map(state.jobs);
    for (const [id, job] of next) {
      if (job.status !== 'downloading') continue;
      if (now - job.startedAt < MAX_ACTIVE_MS) continue;
      next.set(id, {
        ...job,
        status: 'error',
        progress: 0,
        stage: 'catalogue_install.stage_stalled',
        errorMessage:
          job.errorMessage ??
          'Install abandoned after 10 min - try again or check the backend log.',
        completedAt: now,
      });
      clearProgressTimer(id);
      dirty = true;
    }
    if (dirty) {
      useCatalogueInstallStore.setState({ jobs: next });
    }
  }, 60 * 1000);
}

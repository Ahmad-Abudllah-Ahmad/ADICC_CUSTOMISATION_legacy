// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Cases - progress store.
//
// A thin zustand store over the pure helpers in ./progress. It owns the
// per-run progress map plus the per-case sample-project selection, and persists
// both to localStorage so a half-finished case (and the project you were
// learning it on) survive reloads and a hop into a module and back. All real
// logic lives in ./progress (pure, tested); this layer only reads/writes and
// persists.
//
// It also owns two small pieces of view state for the Cases hub itself (not
// per-run progress): the "I work as..." company type the user picked, and
// which cases they pinned to which real project. Both are plain localStorage,
// no backend, same pattern as everything else in this file.

import { create } from 'zustand';
import type { CompanyType, PlaybookProgress, ProfessionalRole } from './types';
import {
  clampStepIndex,
  emptyProgress,
  runKey,
  toggleStep as toggleStepProgress,
} from './progress';

const RUNS_KEY = 'oe_cases_progress';
const SELECTED_KEY = 'oe_cases_selected';
const COMPANY_TYPE_KEY = 'oe_cases_company_type';
const ROLE_KEY = 'oe_cases_role';
const PIN_PROJECT_KEY = 'oe_cases_pin_project';
const PINS_KEY = 'oe_cases_pins';

/** Stable, frozen fallback used by selectors for a run that has no progress
 *  yet. Frozen so an accidental mutation throws instead of corrupting shared
 *  state; the pure helpers never mutate, they return new objects. */
export const EMPTY_PROGRESS: PlaybookProgress = Object.freeze(emptyProgress());

type RunMap = Record<string, PlaybookProgress>;
type SelectedMap = Record<string, string>;

function readRuns(): RunMap {
  try {
    const raw = localStorage.getItem(RUNS_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return {};
    const out: RunMap = {};
    for (const [k, value] of Object.entries(parsed as Record<string, unknown>)) {
      const v = value as Partial<PlaybookProgress> | null;
      if (v && Array.isArray(v.completedStepIds)) {
        out[k] = {
          completedStepIds: v.completedStepIds.filter(
            (id): id is string => typeof id === 'string',
          ),
          currentStepIndex: typeof v.currentStepIndex === 'number' ? v.currentStepIndex : 0,
        };
      }
    }
    return out;
  } catch {
    return {};
  }
}

function readSelected(): SelectedMap {
  try {
    const raw = localStorage.getItem(SELECTED_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return {};
    const out: SelectedMap = {};
    for (const [k, v] of Object.entries(parsed as Record<string, unknown>)) {
      if (typeof v === 'string') out[k] = v;
    }
    return out;
  } catch {
    return {};
  }
}

function persistRuns(runs: RunMap) {
  try {
    localStorage.setItem(RUNS_KEY, JSON.stringify(runs));
  } catch {
    /* localStorage unavailable (private mode / quota) - non-fatal. */
  }
}

function persistSelected(selected: SelectedMap) {
  try {
    localStorage.setItem(SELECTED_KEY, JSON.stringify(selected));
  } catch {
    /* non-fatal */
  }
}

const VALID_COMPANY_TYPES: readonly CompanyType[] = [
  'general-contractor',
  'subcontractor',
  'cost-consultant',
  'designer',
  'developer-client',
  'project-manager',
  'bim-consultant',
  'owner-operator',
];

function readCompanyType(): CompanyType | null {
  try {
    const raw = localStorage.getItem(COMPANY_TYPE_KEY);
    return raw && (VALID_COMPANY_TYPES as string[]).includes(raw) ? (raw as CompanyType) : null;
  } catch {
    return null;
  }
}

function persistCompanyType(value: CompanyType | null) {
  try {
    if (value) localStorage.setItem(COMPANY_TYPE_KEY, value);
    else localStorage.removeItem(COMPANY_TYPE_KEY);
  } catch {
    /* non-fatal */
  }
}

const VALID_ROLES: readonly ProfessionalRole[] = [
  'estimator',
  'quantity-surveyor',
  'site-manager',
  'project-manager',
  'bim-coordinator',
  'procurement-buyer',
  'planner',
  'hse-officer',
  'design-lead',
  'document-controller',
  'commercial-manager',
  'foreman',
];

function readRole(): ProfessionalRole | null {
  try {
    const raw = localStorage.getItem(ROLE_KEY);
    return raw && (VALID_ROLES as string[]).includes(raw) ? (raw as ProfessionalRole) : null;
  } catch {
    return null;
  }
}

function persistRole(value: ProfessionalRole | null) {
  try {
    if (value) localStorage.setItem(ROLE_KEY, value);
    else localStorage.removeItem(ROLE_KEY);
  } catch {
    /* non-fatal */
  }
}

function readPinProject(): string {
  try {
    return localStorage.getItem(PIN_PROJECT_KEY) ?? '';
  } catch {
    return '';
  }
}

function persistPinProject(projectId: string) {
  try {
    if (projectId) localStorage.setItem(PIN_PROJECT_KEY, projectId);
    else localStorage.removeItem(PIN_PROJECT_KEY);
  } catch {
    /* non-fatal */
  }
}

/** Case ids pinned per real project id (NOT a sample-project scope like
 *  `selected` above - this is the user's own "cases I use on this job" list). */
type PinsMap = Record<string, string[]>;

function readPins(): PinsMap {
  try {
    const raw = localStorage.getItem(PINS_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return {};
    const out: PinsMap = {};
    for (const [projectId, ids] of Object.entries(parsed as Record<string, unknown>)) {
      if (Array.isArray(ids)) {
        out[projectId] = ids.filter((id): id is string => typeof id === 'string');
      }
    }
    return out;
  } catch {
    return {};
  }
}

function persistPins(pins: PinsMap) {
  try {
    localStorage.setItem(PINS_KEY, JSON.stringify(pins));
  } catch {
    /* non-fatal */
  }
}

interface CasesState {
  /** Progress per run key (playbookId or `playbookId::projectId`). */
  runs: RunMap;
  /** Sample project chosen per playbook id (empty / absent = none). */
  selected: SelectedMap;
  /** The "I work as..." company type picked on the Cases hub (null = show
   *  every case, no company filter applied). Persists across visits. */
  companyType: CompanyType | null;
  /** The "Your role" professional role picked on the Cases hub (null = no role
   *  filter applied). Independent of `companyType`; both narrow the list.
   *  Persists across visits. */
  role: ProfessionalRole | null;
  /** The real project the user is pinning cases to on the Cases hub ('' =
   *  none picked). Independent of the per-case sample-project `selected`
   *  above - this is "which job am I building a case list for". */
  pinProjectId: string;
  /** Case ids pinned per real project id. */
  pins: PinsMap;
  /** Toggle a step's done flag for a run. */
  toggleStepDone: (playbookId: string, projectId: string | null, stepId: string) => void;
  /** Move the runner's focus to a step index (clamped to the step count). */
  setCurrentStep: (
    playbookId: string,
    projectId: string | null,
    index: number,
    total: number,
  ) => void;
  /** Clear all progress for a run. */
  reset: (playbookId: string, projectId?: string | null) => void;
  /** Set (or clear, with '') the sample project for a playbook. */
  setSelectedProject: (playbookId: string, projectId: string) => void;
  /** Set (or clear, with null) the "I work as..." company type filter. */
  setCompanyType: (companyType: CompanyType | null) => void;
  /** Set (or clear, with null) the "Your role" professional role filter. */
  setRole: (role: ProfessionalRole | null) => void;
  /** Set (or clear, with '') the project the pin picker is scoped to. */
  setPinProjectId: (projectId: string) => void;
  /** Pin or unpin a case for a project (no-op with an empty projectId). */
  togglePin: (projectId: string, playbookId: string) => void;
  /** True when the case is pinned to the given project. */
  isPinned: (projectId: string, playbookId: string) => boolean;
}

export const useCasesStore = create<CasesState>((set, get) => ({
  runs: readRuns(),
  selected: readSelected(),
  companyType: readCompanyType(),
  role: readRole(),
  pinProjectId: readPinProject(),
  pins: readPins(),

  toggleStepDone: (playbookId, projectId, stepId) => {
    const key = runKey(playbookId, projectId);
    const current = get().runs[key] ?? emptyProgress();
    const next = toggleStepProgress(current, stepId);
    const runs = { ...get().runs, [key]: next };
    persistRuns(runs);
    set({ runs });
  },

  setCurrentStep: (playbookId, projectId, index, total) => {
    const key = runKey(playbookId, projectId);
    const current = get().runs[key] ?? emptyProgress();
    const clamped = clampStepIndex(index, total);
    if (get().runs[key] && current.currentStepIndex === clamped) return;
    const runs = { ...get().runs, [key]: { ...current, currentStepIndex: clamped } };
    persistRuns(runs);
    set({ runs });
  },

  reset: (playbookId, projectId) => {
    const key = runKey(playbookId, projectId);
    if (!(key in get().runs)) return;
    const runs = { ...get().runs };
    delete runs[key];
    persistRuns(runs);
    set({ runs });
  },

  setSelectedProject: (playbookId, projectId) => {
    const selected = { ...get().selected };
    if (projectId) selected[playbookId] = projectId;
    else delete selected[playbookId];
    persistSelected(selected);
    set({ selected });
  },

  setCompanyType: (companyType) => {
    persistCompanyType(companyType);
    set({ companyType });
  },

  setRole: (role) => {
    persistRole(role);
    set({ role });
  },

  setPinProjectId: (projectId) => {
    persistPinProject(projectId);
    set({ pinProjectId: projectId });
  },

  togglePin: (projectId, playbookId) => {
    if (!projectId) return;
    const current = get().pins[projectId] ?? [];
    const has = current.includes(playbookId);
    const nextForProject = has
      ? current.filter((id) => id !== playbookId)
      : [...current, playbookId];
    const pins = { ...get().pins, [projectId]: nextForProject };
    persistPins(pins);
    set({ pins });
  },

  isPinned: (projectId, playbookId) => {
    if (!projectId) return false;
    return (get().pins[projectId] ?? []).includes(playbookId);
  },
}));

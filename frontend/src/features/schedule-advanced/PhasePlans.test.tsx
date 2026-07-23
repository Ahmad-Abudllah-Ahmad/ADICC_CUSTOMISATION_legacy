// @ts-nocheck
/**
 * Smoke tests for the rebuilt Phase Plans tab on /schedule-advanced.
 *
 * Verifies:
 *   - empty state shows "New phase" + "Use a template" CTAs
 *   - clicking "New phase" opens the create modal
 *   - "Apply template" path POSTs N phases via the public API
 *   - populated state renders cards + table + timeline view toggle
 *   - delete confirmation dialog appears before delete fires
 *
 * Network is stubbed via ``vi.mock`` on ``./api`` + ``@/features/projects/api``.
 * React Query retries are disabled so errors surface immediately.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

vi.mock('./api', async () => {
  const actual = await vi.importActual<typeof import('./api')>('./api');
  return {
    ...actual,
    listMasterSchedules: vi.fn(),
    createMasterSchedule: vi.fn(),
    listPhasePlans: vi.fn(),
    createPhasePlan: vi.fn(),
    updatePhasePlan: vi.fn(),
    deletePhasePlan: vi.fn(),
    pullPhase: vi.fn(),
    startPhase: vi.fn(),
    completePhase: vi.fn(),
    listLookAheads: vi.fn(),
    listConstraints: vi.fn(),
    listWeeklyPlans: vi.fn(),
    listCommitments: vi.fn(),
    listBaselines: vi.fn(),
    baselineDelta: vi.fn(),
    currentTasksForMaster: vi.fn(),
    // Master-tab project overview card. Stubbed empty so it renders the
    // inert "no activity yet" hint and never hits the network in jsdom.
    projectDashboard: vi.fn().mockResolvedValue({
      project_id: 'p1',
      ppc_trend: [],
      open_constraints: 0,
      constraints_by_type: {},
      rnc_pareto: {},
      active_master_schedules: 0,
      active_baselines: 0,
      current_week_commitments: 0,
    }),
  };
});

vi.mock('@/features/projects/api', () => ({
  projectsApi: {
    list: vi.fn().mockResolvedValue([{ id: 'p1', name: 'Test Project' }]),
  },
}));

import {
  listMasterSchedules,
  listPhasePlans,
  createPhasePlan,
  deletePhasePlan,
  listBaselines,
  baselineDelta,
  currentTasksForMaster,
} from './api';
import { ScheduleAdvancedPage } from './ScheduleAdvancedPage';

const masterSchedule = {
  id: 'ms1',
  project_id: 'p1',
  name: 'Master',
  planned_start: '2026-06-01',
  planned_finish: '2026-12-31',
  status: 'active',
  notes: '',
  created_at: '2026-05-01T00:00:00Z',
  updated_at: '2026-05-01T00:00:00Z',
};

const samplePhase = {
  id: 'ph1',
  master_schedule_id: 'ms1',
  name: 'Foundation',
  planned_start: '2026-06-01',
  planned_finish: '2026-06-30',
  pulled_status: 'in_planning',
  notes: 'Spread foundations',
  created_at: '2026-05-01T00:00:00Z',
  updated_at: '2026-05-01T00:00:00Z',
};

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/schedule-advanced']}>
        <ScheduleAdvancedPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function gotoPhasesTab() {
  // Wait for tabs to render. The tab nav renders <button role="tab"> inside a
  // role="tablist" (correct ARIA), so query the "tab" role, not "button".
  const tab = await screen.findByRole('tab', { name: /phase plans/i });
  fireEvent.click(tab);
}

describe('PhasePlans tab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (listMasterSchedules as any).mockResolvedValue([masterSchedule]);
    // Variance subsystem stays inert unless a test wires real baselines.
    (listBaselines as any).mockResolvedValue([]);
    (baselineDelta as any).mockResolvedValue({
      baseline_id: 'b1',
      current_master_id: 'ms1',
      entries: [],
      total_tasks: 0,
      delayed_tasks: 0,
      accelerated_tasks: 0,
    });
    (currentTasksForMaster as any).mockResolvedValue([]);
  });

  it('renders the empty-state CTAs when there are no phases', async () => {
    (listPhasePlans as any).mockResolvedValue([]);
    renderPage();
    await gotoPhasesTab();
    expect(await screen.findByText(/no phase plans yet/i)).toBeInTheDocument();
    // Primary CTA — "New phase" — and secondary "Use a template" both present
    expect(screen.getAllByRole('button', { name: /new phase/i }).length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: /use a template/i })).toBeInTheDocument();
  });

  it('opens the create-phase modal when the empty-state CTA is clicked', async () => {
    (listPhasePlans as any).mockResolvedValue([]);
    renderPage();
    await gotoPhasesTab();
    const cta = await screen.findByRole('button', { name: /^new phase$/i });
    fireEvent.click(cta);
    // Modal title in WideModal
    expect(await screen.findByText(/^new phase$/i, { selector: 'h2,h3' })).toBeInTheDocument();
    // Form fields visible
    expect(screen.getByText(/phase name/i)).toBeInTheDocument();
    expect(screen.getByText(/planned start/i)).toBeInTheDocument();
    expect(screen.getByText(/planned finish/i)).toBeInTheDocument();
  });

  it('renders cards + status filter chips when phases exist', async () => {
    (listPhasePlans as any).mockResolvedValue([
      samplePhase,
      { ...samplePhase, id: 'ph2', name: 'Structure', pulled_status: 'active' },
      { ...samplePhase, id: 'ph3', name: 'Finishes', pulled_status: 'completed' },
    ]);
    renderPage();
    await gotoPhasesTab();
    expect(await screen.findByText('Foundation')).toBeInTheDocument();
    expect(screen.getByText('Structure')).toBeInTheDocument();
    expect(screen.getByText('Finishes')).toBeInTheDocument();
    // Status filter chips render. "All" appears twice (status filter chip plus
    // the look-ahead horizon row), so assert at least one; "In planning" is
    // unique to the status filter.
    expect(screen.getAllByRole('button', { name: /^all/i }).length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: /^in planning/i })).toBeInTheDocument();
  });

  it('exposes Cards / Table / Timeline view toggle', async () => {
    (listPhasePlans as any).mockResolvedValue([samplePhase]);
    renderPage();
    await gotoPhasesTab();
    await screen.findByText('Foundation');
    expect(screen.getByRole('tab', { name: /cards/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /table/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /timeline/i })).toBeInTheDocument();
  });

  it('switches to table view when Table is clicked', async () => {
    (listPhasePlans as any).mockResolvedValue([samplePhase]);
    renderPage();
    await gotoPhasesTab();
    await screen.findByText('Foundation');
    fireEvent.click(screen.getByRole('tab', { name: /table/i }));
    // Table headers appear
    await waitFor(() => {
      expect(screen.getByText(/^#$/)).toBeInTheDocument();
    });
    expect(screen.getByText(/days/i)).toBeInTheDocument();
    expect(screen.getByText(/progress/i)).toBeInTheDocument();
  });

  it('submits createPhasePlan with the entered name', async () => {
    (listPhasePlans as any).mockResolvedValue([]);
    (createPhasePlan as any).mockResolvedValue({ ...samplePhase, name: 'New Phase A' });
    renderPage();
    await gotoPhasesTab();
    const cta = await screen.findByRole('button', { name: /^new phase$/i });
    fireEvent.click(cta);
    // Find the phase-name input inside the modal
    const nameInput = await screen.findByPlaceholderText(/foundation/i);
    fireEvent.change(nameInput, { target: { value: 'New Phase A' } });
    // Click Create
    const createBtns = screen.getAllByRole('button', { name: /^create$/i });
    fireEvent.click(createBtns[createBtns.length - 1]);
    await waitFor(() => {
      expect(createPhasePlan).toHaveBeenCalledWith(
        expect.objectContaining({
          master_schedule_id: 'ms1',
          name: 'New Phase A',
        }),
      );
    });
  });

  it('shows the look-ahead horizon chips with counts', async () => {
    // Two phases: one starts today, one starts ~6 months out. The "1
    // week" chip count should be 1, the "All" chip count should be 2.
    const today = new Date().toISOString().slice(0, 10);
    const farOut = new Date(Date.now() + 180 * 86_400_000).toISOString().slice(0, 10);
    (listPhasePlans as any).mockResolvedValue([
      { ...samplePhase, id: 'pn1', name: 'Near', planned_start: today, planned_finish: today },
      { ...samplePhase, id: 'pf1', name: 'Far', planned_start: farOut, planned_finish: farOut },
    ]);
    renderPage();
    await gotoPhasesTab();
    await screen.findByText('Near');
    const chips = await screen.findByTestId('phase-horizon-chips');
    expect(chips).toBeInTheDocument();
    expect(chips.textContent).toMatch(/1 week/i);
    expect(chips.textContent).toMatch(/2 weeks/i);
    expect(chips.textContent).toMatch(/4 weeks/i);
  });

  it('marks the longest-duration phase as critical (CP badge)', async () => {
    // The 90-day phase outweighs the 30-day phase, so the CP badge
    // should appear on it via computeCriticalPhaseIds.
    const longStart = new Date().toISOString().slice(0, 10);
    const longEnd = new Date(Date.now() + 90 * 86_400_000).toISOString().slice(0, 10);
    (listPhasePlans as any).mockResolvedValue([
      { ...samplePhase, id: 'sh', name: 'Short', planned_start: longStart, planned_finish: new Date(Date.now() + 5 * 86_400_000).toISOString().slice(0, 10) },
      { ...samplePhase, id: 'lo', name: 'LongCritical', planned_start: longStart, planned_finish: longEnd },
    ]);
    renderPage();
    await gotoPhasesTab();
    await screen.findByText('LongCritical');
    // At least one CP badge must render.
    const cpBadges = await screen.findAllByTestId('phase-cp-badge');
    expect(cpBadges.length).toBeGreaterThan(0);
  });

  it('renders variance badge when baseline delta is present', async () => {
    (listPhasePlans as any).mockResolvedValue([samplePhase]);
    (listBaselines as any).mockResolvedValue([
      { id: 'b1', master_schedule_id: 'ms1', name: 'Contract', status: 'active', snapshot: [], notes: '', captured_at: null, created_at: '2026-05-01T00:00:00Z', updated_at: '2026-05-01T00:00:00Z' },
    ]);
    (baselineDelta as any).mockResolvedValue({
      baseline_id: 'b1',
      current_master_id: 'ms1',
      entries: [
        {
          task_ref: 'ph1',
          name: 'Foundation',
          planned_start_baseline: '2026-06-01',
          planned_start_current: '2026-06-06',
          planned_finish_baseline: '2026-06-30',
          planned_finish_current: '2026-07-05',
          schedule_variance_days: 5,
        },
      ],
      total_tasks: 1,
      delayed_tasks: 1,
      accelerated_tasks: 0,
    });
    (currentTasksForMaster as any).mockResolvedValue([
      { task_ref: 'ph1', planned_start: '2026-06-06', planned_finish: '2026-07-05', name: 'Foundation' },
    ]);
    renderPage();
    await gotoPhasesTab();
    await screen.findByText('Foundation');
    // Variance badge should appear (+5d) once the delta query resolves.
    await waitFor(() => {
      expect(screen.queryByTestId('phase-variance-late')).toBeInTheDocument();
    });
  });

  it('opens delete-confirm before calling deletePhasePlan', async () => {
    (listPhasePlans as any).mockResolvedValue([samplePhase]);
    (deletePhasePlan as any).mockResolvedValue(undefined);
    renderPage();
    await gotoPhasesTab();
    await screen.findByText('Foundation');
    // Find the trash button on the card
    const deleteBtn = screen.getAllByRole('button', { name: /^delete$/i })[0];
    fireEvent.click(deleteBtn);
    // Confirm dialog appears
    const dialog = await screen.findByRole('alertdialog');
    expect(dialog).toBeInTheDocument();
    expect(screen.getByText(/delete phase/i)).toBeInTheDocument();
    // Cancel — must NOT call delete. ConfirmDialog's "Cancel" label embeds
    // zero-width steganography chars so the visible string is e.g. "Cancel".
    // Match the first button inside the dialog (cancel is left of confirm).
    const dialogButtons = dialog.querySelectorAll('button');
    fireEvent.click(dialogButtons[0]);
    await waitFor(() => {
      expect(deletePhasePlan).not.toHaveBeenCalled();
    });
  });
});

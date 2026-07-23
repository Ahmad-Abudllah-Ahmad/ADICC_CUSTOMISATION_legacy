// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Smoke tests for the Construction Control page.
//
// The API layer is stubbed via vi.mock('./api') so we can verify:
//   - the page heading renders,
//   - all five pillar tabs render,
//   - switching tabs swaps in each pillar section (and calls its list endpoint),
//   - a loaded inspection row appears for the active project.
//
// React Query runs with retry disabled so any error surfaces immediately.

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { useProjectContextStore } from '@/stores/useProjectContextStore';

// Automock the whole API: this page renders every pillar section, and the
// sections reference their create and action endpoints (createMaterial,
// createGate, createHandoverPackage and so on) at render through useMutation. A
// partial factory mock would omit those exports and crash the sections, so we
// automock and stub every export, then configure the list endpoints below.
vi.mock('./api');

import {
  listCriteria,
  listInspections,
  listMaterials,
  listTestResults,
  listAsBuilt,
  listGates,
  listHandoverPackages,
} from './api';
import { ConstructionControlPage } from './ConstructionControlPage';

const PROJECT_ID = 'proj-1';

const sampleInspection = {
  id: 'insp-1',
  project_id: PROJECT_ID,
  inspection_number: 'INS-001',
  inspection_type: 'wir',
  party_role: 'qc',
  intervention_point: null,
  title: 'Rebar inspection - Level 2 slab',
  description: null,
  location_description: 'Grid C4',
  activity_id: null,
  criterion_id: null,
  status: 'draft',
  result: null,
  measured_value: null,
  result_notes: null,
  raised_ncr_id: null,
  scheduled_at: null,
  performed_at: null,
  performed_by: null,
  created_by: null,
  metadata: {},
  created_at: '2026-06-23T00:00:00Z',
  updated_at: '2026-06-23T00:00:00Z',
  elements: [],
};

function setEmptyResolvers() {
  (listCriteria as ReturnType<typeof vi.fn>).mockResolvedValue([]);
  (listInspections as ReturnType<typeof vi.fn>).mockResolvedValue([]);
  (listMaterials as ReturnType<typeof vi.fn>).mockResolvedValue([]);
  (listTestResults as ReturnType<typeof vi.fn>).mockResolvedValue([]);
  (listAsBuilt as ReturnType<typeof vi.fn>).mockResolvedValue([]);
  (listGates as ReturnType<typeof vi.fn>).mockResolvedValue([]);
  (listHandoverPackages as ReturnType<typeof vi.fn>).mockResolvedValue([]);
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/construction-control']}>
        <ConstructionControlPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ConstructionControlPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setEmptyResolvers();
    useProjectContextStore.getState().setActiveProject(PROJECT_ID, 'Riverside HQ');
  });

  it('renders the page heading', () => {
    renderPage();
    expect(
      screen.getByRole('heading', { name: /Construction Control/i }),
    ).toBeInTheDocument();
  });

  it('shows the no-project empty state when no project is active', () => {
    useProjectContextStore.getState().clearProject();
    renderPage();
    expect(screen.getByText(/No project selected/i)).toBeInTheDocument();
    expect(listInspections).not.toHaveBeenCalled();
  });

  it('renders all five pillar tabs', () => {
    renderPage();
    expect(screen.getByTestId('cc-tab-inspections')).toBeInTheDocument();
    expect(screen.getByTestId('cc-tab-materials')).toBeInTheDocument();
    expect(screen.getByTestId('cc-tab-asbuilt')).toBeInTheDocument();
    expect(screen.getByTestId('cc-tab-gates')).toBeInTheDocument();
    expect(screen.getByTestId('cc-tab-handover')).toBeInTheDocument();
  });

  it('loads inspections for the active project on the default tab', async () => {
    (listInspections as ReturnType<typeof vi.fn>).mockResolvedValue([sampleInspection]);
    renderPage();
    await waitFor(() => expect(listInspections).toHaveBeenCalledWith(PROJECT_ID));
    expect(await screen.findByText('Rebar inspection - Level 2 slab')).toBeInTheDocument();
    expect(screen.getByText('INS-001')).toBeInTheDocument();
  });

  it('switches to the Materials tab and loads materials + tests', async () => {
    renderPage();
    fireEvent.click(screen.getByTestId('cc-tab-materials'));
    await waitFor(() => expect(listMaterials).toHaveBeenCalledWith(PROJECT_ID));
    // The materials section passes a filter options object as the second arg.
    expect(listTestResults).toHaveBeenCalledWith(PROJECT_ID, expect.anything());
    expect(
      await screen.findByText(/No material records yet/i),
    ).toBeInTheDocument();
  });

  it('switches to the Hold Points tab and loads gates', async () => {
    renderPage();
    fireEvent.click(screen.getByTestId('cc-tab-gates'));
    await waitFor(() => expect(listGates).toHaveBeenCalledWith(PROJECT_ID));
    expect(
      await screen.findByText(/No hold or witness points yet/i),
    ).toBeInTheDocument();
  });

  it('switches to the Handover tab and loads packages', async () => {
    renderPage();
    fireEvent.click(screen.getByTestId('cc-tab-handover'));
    await waitFor(() => expect(listHandoverPackages).toHaveBeenCalledWith(PROJECT_ID));
    expect(await screen.findByText(/No handover packages yet/i)).toBeInTheDocument();
  });
});

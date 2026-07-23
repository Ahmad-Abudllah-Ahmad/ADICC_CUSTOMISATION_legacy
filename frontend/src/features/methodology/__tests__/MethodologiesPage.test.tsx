// @ts-nocheck
// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Component tests for the methodologies hub: the templates gallery, the
// installed list, the install flow and the no-project guard. The API is fully
// mocked (no network); the active project comes from the shared store.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../api', () => ({
  toNum: (v: unknown) => (typeof v === 'number' ? v : Number(v) || 0),
  methodologyApi: {
    listTemplates: vi.fn(),
    list: vi.fn(),
    getActive: vi.fn(),
    installTemplate: vi.fn(),
  },
}));

import { methodologyApi } from '../api';
import { MethodologiesPage } from '../MethodologiesPage';
import { useProjectContextStore } from '@/stores/useProjectContextStore';

const TEMPLATES = [
  {
    slug: 'international',
    name: 'International (neutral)',
    description: 'Neutral flat methodology.',
    country_code: null,
    industry: null,
    currency: '',
    step_count: 3,
  },
  {
    slug: 'germany',
    name: 'Germany',
    description: 'German flat estimate.',
    country_code: 'DE',
    industry: null,
    currency: 'EUR',
    step_count: 3,
  },
  {
    slug: 'uzbekistan',
    name: 'Uzbekistan (cascading)',
    description: 'Uzbekistan cascading methodology.',
    country_code: 'UZ',
    industry: null,
    currency: 'UZS',
    step_count: 5,
  },
  {
    slug: 'railway_infrastructure',
    name: 'Railway infrastructure',
    description: 'Railway-infrastructure industry methodology.',
    country_code: null,
    industry: 'railway',
    currency: '',
    step_count: 4,
  },
];

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <MethodologiesPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe('MethodologiesPage', () => {
  beforeEach(() => {
    (methodologyApi.listTemplates as ReturnType<typeof vi.fn>).mockReset();
    (methodologyApi.list as ReturnType<typeof vi.fn>).mockReset();
    (methodologyApi.getActive as ReturnType<typeof vi.fn>).mockReset();
    (methodologyApi.installTemplate as ReturnType<typeof vi.fn>).mockReset();
    // Default happy-path stubs.
    (methodologyApi.listTemplates as ReturnType<typeof vi.fn>).mockResolvedValue(TEMPLATES);
    (methodologyApi.list as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    (methodologyApi.getActive as ReturnType<typeof vi.fn>).mockResolvedValue({
      project_id: 'proj-1',
      methodology_slug: 'international',
    });
    // Set an active project (real store, mocked localStorage).
    useProjectContextStore.getState().setActiveProject('proj-1', 'Test Project');
  });

  it('still shows the (project-agnostic) templates gallery when no project is active', async () => {
    useProjectContextStore.getState().clearProject();
    renderPage();
    // The gallery does not need a project - it must render so the page is never
    // blank; only the install/create actions are gated.
    expect(await screen.findByText('International (neutral)')).toBeInTheDocument();
    expect(screen.getByText('Germany')).toBeInTheDocument();
    // ...and the page still prompts the visitor to pick a project before installing.
    expect(screen.getByText('Select a project first')).toBeInTheDocument();
  });

  it('renders the templates gallery grouped, with all 10-style buckets', async () => {
    renderPage();
    // International default
    expect(await screen.findByText('International (neutral)')).toBeInTheDocument();
    // Country
    expect(screen.getByText('Germany')).toBeInTheDocument();
    // Cascading (Uzbekistan)
    expect(screen.getByText('Uzbekistan (cascading)')).toBeInTheDocument();
    // Industry pack
    expect(screen.getByText('Railway infrastructure')).toBeInTheDocument();
    // Group headers
    expect(screen.getByText('Neutral default')).toBeInTheDocument();
    expect(screen.getByText('Countries')).toBeInTheDocument();
    expect(screen.getByText('Industry packs')).toBeInTheDocument();
  });

  it('shows the empty-installed state when the project has no clones', async () => {
    renderPage();
    expect(await screen.findByText('No methodology installed yet')).toBeInTheDocument();
  });

  it('installs a template when its Install button is clicked', async () => {
    (methodologyApi.installTemplate as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: 'meth-de-1',
      slug: 'germany-proj1',
      name: 'Germany',
      scope: 'project',
      project_id: 'proj-1',
      is_builtin: false,
      is_editable: true,
    });

    renderPage();
    await screen.findByText('Germany');

    // There are several "Install" buttons (one per template). Click them all is
    // wrong; pick the first and assert the API was called with a template slug.
    const installButtons = screen.getAllByRole('button', { name: /Install/ });
    fireEvent.click(installButtons[0]);

    await waitFor(() => {
      expect(methodologyApi.installTemplate).toHaveBeenCalledTimes(1);
    });
    const arg = (methodologyApi.installTemplate as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(arg.project_id).toBe('proj-1');
    expect(typeof arg.template_slug).toBe('string');
    expect(arg.template_slug.length).toBeGreaterThan(0);
  });

  it('lists installed project methodologies and marks the active one', async () => {
    (methodologyApi.list as ReturnType<typeof vi.fn>).mockResolvedValue([
      {
        id: 'meth-1',
        slug: 'germany-proj1',
        scope: 'project',
        project_id: 'proj-1',
        country_code: 'DE',
        industry: null,
        name: 'Our Germany method',
        currency: 'EUR',
        is_builtin: false,
        is_editable: true,
      },
    ]);
    (methodologyApi.getActive as ReturnType<typeof vi.fn>).mockResolvedValue({
      project_id: 'proj-1',
      methodology_slug: 'germany-proj1',
    });

    renderPage();
    expect(await screen.findByText('Our Germany method')).toBeInTheDocument();
    // The active badge renders for the active methodology.
    expect(screen.getByText('Active')).toBeInTheDocument();
    // Editable methodologies offer an Edit action.
    expect(screen.getByRole('button', { name: /Edit/ })).toBeInTheDocument();
  });
});

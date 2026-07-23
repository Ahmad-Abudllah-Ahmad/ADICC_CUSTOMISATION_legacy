// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// SavedViewsRail unit tests.
//
// Covers:
//   1. Renders the saved-view rows returned by the API.
//   2. Shows the use_count badge.
//   3. Clicking a row navigates to /files with a serialised filter
//      and POSTs /use/ to bump the telemetry.
//   4. Context menu (right-click) opens with the expected actions.

import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

/* ── i18n stub ─────────────────────────────────────────────────────── */

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const fallback = (opts?.defaultValue as string) ?? key;
      return fallback.replace(/\{\{(\w+)\}\}/g, (_, name) =>
        opts && opts[name] !== undefined ? String(opts[name]) : `{{${name}}}`,
      );
    },
  }),
  // ``src/app/i18n.ts`` is pulled in transitively and calls
  // ``.use(initReactI18next)`` at module load — expose the noop plugin.
  initReactI18next: { type: '3rdParty', init: () => {} },
}));

/* ── react-router stub: keep MemoryRouter, mock useNavigate only ────── */

const navigateSpy = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => navigateSpy,
  };
});

/* ── API layer mock ────────────────────────────────────────────────── */

const useSavedViewApiMock = vi.fn<(...args: unknown[]) => Promise<unknown>>();
const fetchSavedViewsMock = vi.fn<(...args: unknown[]) => Promise<unknown>>();
const createSavedViewMock = vi.fn<(...args: unknown[]) => Promise<unknown>>();
const updateSavedViewMock = vi.fn<(...args: unknown[]) => Promise<unknown>>();
const deleteSavedViewMock = vi.fn<(...args: unknown[]) => Promise<unknown>>();
const duplicateSavedViewMock = vi.fn<(...args: unknown[]) => Promise<unknown>>();

vi.mock('../api', () => ({
  fetchSavedViews: (...args: unknown[]) => fetchSavedViewsMock(...args),
  createSavedView: (...args: unknown[]) => createSavedViewMock(...args),
  updateSavedView: (...args: unknown[]) => updateSavedViewMock(...args),
  deleteSavedView: (...args: unknown[]) => deleteSavedViewMock(...args),
  useSavedView: (...args: unknown[]) => useSavedViewApiMock(...args),
  duplicateSavedView: (...args: unknown[]) => duplicateSavedViewMock(...args),
}));

import { SavedViewsRail } from '../SavedViewsRail';
import type { SavedViewResponse } from '../types';

/* ── Fixtures ──────────────────────────────────────────────────────── */

const PROJECT_ID = 'proj-001';

function view(overrides: Partial<SavedViewResponse>): SavedViewResponse {
  return {
    id: 'view-1',
    user_id: 'user-1',
    project_id: PROJECT_ID,
    name: 'Drawings',
    icon: 'layout',
    filter_json: { kind: 'sheet', q: 'foundation' },
    sort_order: 0,
    is_pinned: false,
    is_shared: false,
    last_used_at: null,
    use_count: 0,
    created_at: '2026-05-19T00:00:00Z',
    updated_at: '2026-05-19T00:00:00Z',
    is_own: true,
    ...overrides,
  };
}

function renderRail(items: SavedViewResponse[]) {
  fetchSavedViewsMock.mockResolvedValue({ items, total: items.length });
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <SavedViewsRail projectId={PROJECT_ID} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  navigateSpy.mockReset();
  fetchSavedViewsMock.mockReset();
  useSavedViewApiMock.mockReset();
  useSavedViewApiMock.mockResolvedValue({ id: 'view-1', use_count: 1 });
  createSavedViewMock.mockReset();
  updateSavedViewMock.mockReset();
  deleteSavedViewMock.mockReset();
  duplicateSavedViewMock.mockReset();
});

afterEach(() => {
  cleanup();
});

/* ── Tests ─────────────────────────────────────────────────────────── */

describe('SavedViewsRail', () => {
  it('renders one row per saved view returned by the API', async () => {
    renderRail([
      view({ id: 'a', name: 'Drawings' }),
      view({ id: 'b', name: 'Photos', filter_json: { kind: 'photo' } }),
    ]);

    expect(await screen.findByText('Drawings')).toBeTruthy();
    expect(screen.getByText('Photos')).toBeTruthy();
    expect(screen.getByTestId('saved-view-row-a')).toBeTruthy();
    expect(screen.getByTestId('saved-view-row-b')).toBeTruthy();
  });

  it('renders the use_count badge when use_count > 0', async () => {
    renderRail([view({ id: 'busy', name: 'Busy view', use_count: 42 })]);
    const badge = await screen.findByTestId('saved-view-usecount-busy');
    expect(badge.textContent).toBe('42');
  });

  it('does not render a use_count badge when use_count is 0', async () => {
    renderRail([view({ id: 'fresh', name: 'Fresh view', use_count: 0 })]);
    await screen.findByText('Fresh view');
    expect(screen.queryByTestId('saved-view-usecount-fresh')).toBeNull();
  });

  it('clicking a row navigates with serialised filter and bumps use_count', async () => {
    renderRail([
      view({
        id: 'clk',
        name: 'Click me',
        filter_json: { kind: 'sheet', q: 'concrete', extension: 'pdf' },
      }),
    ]);

    const row = await screen.findByTestId('saved-view-row-clk');
    fireEvent.click(row);

    await waitFor(() => {
      expect(useSavedViewApiMock).toHaveBeenCalledWith('clk');
    });
    await waitFor(() => {
      expect(navigateSpy).toHaveBeenCalled();
    });
    const navTarget = navigateSpy.mock.calls[0]?.[0] as string;
    expect(navTarget).toContain('/files?');
    expect(navTarget).toContain('kind=sheet');
    expect(navTarget).toContain('q=concrete');
    expect(navTarget).toContain('extension=pdf');
  });

  it('right-click opens the context menu with action buttons', async () => {
    renderRail([view({ id: 'ctx', name: 'With menu' })]);
    const row = await screen.findByTestId('saved-view-row-ctx');
    fireEvent.contextMenu(row, { clientX: 10, clientY: 20 });

    expect(screen.getByTestId('saved-views-context-menu')).toBeTruthy();
    expect(screen.getByTestId('saved-view-action-rename')).toBeTruthy();
    expect(screen.getByTestId('saved-view-action-pin')).toBeTruthy();
    expect(screen.getByTestId('saved-view-action-share')).toBeTruthy();
    expect(screen.getByTestId('saved-view-action-duplicate')).toBeTruthy();
    expect(screen.getByTestId('saved-view-action-delete')).toBeTruthy();
  });

  it('clicking duplicate calls the duplicate mutation', async () => {
    duplicateSavedViewMock.mockResolvedValue(view({ id: 'dup', name: 'Drawings (copy)' }));
    renderRail([view({ id: 'orig', name: 'Drawings' })]);
    const row = await screen.findByTestId('saved-view-row-orig');
    fireEvent.contextMenu(row, { clientX: 10, clientY: 20 });
    fireEvent.click(screen.getByTestId('saved-view-action-duplicate'));

    await waitFor(() => {
      expect(duplicateSavedViewMock).toHaveBeenCalledWith('orig');
    });
  });

  it('disables write actions for views the caller does not own', async () => {
    renderRail([view({ id: 'shared', name: 'Shared by Alice', is_own: false, is_shared: true })]);
    const row = await screen.findByTestId('saved-view-row-shared');
    fireEvent.contextMenu(row, { clientX: 10, clientY: 20 });
    expect((screen.getByTestId('saved-view-action-rename') as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByTestId('saved-view-action-pin') as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByTestId('saved-view-action-share') as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByTestId('saved-view-action-delete') as HTMLButtonElement).disabled).toBe(true);
    // Duplicate is always allowed — copy lands in the user's own list.
    expect((screen.getByTestId('saved-view-action-duplicate') as HTMLButtonElement).disabled).toBe(false);
  });
});

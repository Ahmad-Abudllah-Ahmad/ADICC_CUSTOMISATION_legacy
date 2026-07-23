// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/** Unit tests for TrashPage.
 *
 * Mocks ``./api`` + the project context store so the page renders
 * deterministic data without a live backend. Verifies:
 *   1. Trash rows are rendered with restore + purge buttons.
 *   2. Clicking "Restore" fires ``restoreFromTrash`` with the row id.
 *   3. "Delete forever" requires a confirmation click before the
 *      purge mutation fires.
 *   4. Empty list → EmptyState rendered.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import type React from 'react';

vi.mock('../api', () => {
  return {
    listTrash: vi.fn(),
    trashStats: vi.fn(),
    softDelete: vi.fn(),
    restoreFromTrash: vi.fn(),
    purgeFromTrash: vi.fn(),
    fileTrashKeys: {
      list: 'file-trash-list',
      stats: 'file-trash-stats',
    },
  };
});

vi.mock('@/stores/useToastStore', () => {
  const addToast = vi.fn();
  return {
    useToastStore: Object.assign(
      (selector: (s: { addToast: typeof addToast }) => unknown) => selector({ addToast }),
      { getState: () => ({ addToast }) },
    ),
    __addToast: addToast,
  };
});

const projectContextState = {
  activeProjectId: 'proj-001' as string | null,
  activeProjectName: 'Test Project' as string | null,
};

vi.mock('@/stores/useProjectContextStore', () => {
  type Selector = (s: typeof projectContextState) => unknown;
  return {
    useProjectContextStore: ((selector: Selector) => selector(projectContextState)) as unknown,
  };
});

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const fallback = (opts?.defaultValue as string) ?? key;
      return fallback.replace(/\{\{(\w+)\}\}/g, (_, name) =>
        opts && opts[name] !== undefined ? String(opts[name]) : `{{${name}}}`,
      );
    },
  }),
  // ``i18n.ts`` is dragged in via ErrorBoundary → @/shared/ui chain;
  // it imports ``initReactI18next`` so the mock must expose it.
  initReactI18next: { type: '3rdParty', init: () => {} },
  Trans: ({ children }: { children?: React.ReactNode }) => children,
}));

import * as api from '../api';
import { TrashPage } from '../TrashPage';
import type { TrashItem, TrashStats } from '../types';

const listMock = api.listTrash as unknown as ReturnType<typeof vi.fn>;
const statsMock = api.trashStats as unknown as ReturnType<typeof vi.fn>;
const restoreMock = api.restoreFromTrash as unknown as ReturnType<typeof vi.fn>;
const purgeMock = api.purgeFromTrash as unknown as ReturnType<typeof vi.fn>;

function makeItem(id: string, overrides: Partial<TrashItem> = {}): TrashItem {
  return {
    id,
    project_id: 'proj-001',
    original_kind: 'document',
    original_id: `orig-${id}`,
    canonical_name: `file-${id}.pdf`,
    payload_json: { name: `file-${id}.pdf`, file_size: 4096 },
    trashed_at: '2026-05-19T12:00:00Z',
    trashed_by_id: null,
    retention_days: 30,
    restored_at: null,
    restored_by_id: null,
    purged_at: null,
    restore_token: `tok-${id}`,
    file_size: 4096,
    created_at: '2026-05-19T12:00:00Z',
    updated_at: '2026-05-19T12:00:00Z',
    ...overrides,
  };
}

function defaultStats(): TrashStats {
  return {
    project_id: 'proj-001',
    count: 0,
    total_bytes: 0,
    oldest_trashed_at: null,
    newest_trashed_at: null,
  };
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <TrashPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  listMock.mockReset();
  statsMock.mockReset();
  restoreMock.mockReset();
  purgeMock.mockReset();
  projectContextState.activeProjectId = 'proj-001';
  projectContextState.activeProjectName = 'Test Project';
  cleanup();
});

describe('TrashPage', () => {
  it('renders rows with restore + purge buttons', async () => {
    listMock.mockResolvedValue({
      items: [
        makeItem('a', { canonical_name: 'plans.pdf' }),
        makeItem('b', { canonical_name: 'photo.jpg', original_kind: 'photo' }),
      ],
      total: 2,
      limit: 50,
      offset: 0,
    });
    statsMock.mockResolvedValue({ ...defaultStats(), count: 2, total_bytes: 8192 });

    renderPage();

    await screen.findByText('plans.pdf');
    expect(screen.getByText('photo.jpg')).toBeTruthy();
    expect(screen.getByTestId('trash-restore-a')).toBeTruthy();
    expect(screen.getByTestId('trash-purge-a')).toBeTruthy();
  });

  it('fires restore mutation with the row id on click', async () => {
    listMock.mockResolvedValue({
      items: [makeItem('a')],
      total: 1,
      limit: 50,
      offset: 0,
    });
    statsMock.mockResolvedValue({ ...defaultStats(), count: 1, total_bytes: 4096 });
    restoreMock.mockResolvedValue(makeItem('a', { restored_at: '2026-05-19T13:00:00Z' }));

    renderPage();

    const restoreBtn = await screen.findByTestId('trash-restore-a');
    fireEvent.click(restoreBtn);

    await waitFor(() => {
      expect(restoreMock).toHaveBeenCalledWith('a');
    });
  });

  it('purge requires confirmation click before firing', async () => {
    listMock.mockResolvedValue({
      items: [makeItem('a')],
      total: 1,
      limit: 50,
      offset: 0,
    });
    statsMock.mockResolvedValue({ ...defaultStats(), count: 1, total_bytes: 4096 });
    purgeMock.mockResolvedValue(undefined);

    renderPage();

    // First click reveals the confirm button — does not fire mutation.
    const purgeBtn = await screen.findByTestId('trash-purge-a');
    fireEvent.click(purgeBtn);
    expect(purgeMock).not.toHaveBeenCalled();

    const confirm = await screen.findByTestId('trash-purge-confirm-a');
    fireEvent.click(confirm);

    await waitFor(() => {
      expect(purgeMock).toHaveBeenCalledWith('a', 'tok-a');
    });
  });

  it('renders the empty state when there are no trash rows', async () => {
    listMock.mockResolvedValue({
      items: [],
      total: 0,
      limit: 50,
      offset: 0,
    });
    statsMock.mockResolvedValue(defaultStats());

    renderPage();

    await screen.findByText(/Recycle Bin is empty/i);
  });

  it('renders the no-project state when no active project is set', async () => {
    projectContextState.activeProjectId = null;
    projectContextState.activeProjectName = null;
    listMock.mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 });
    statsMock.mockResolvedValue(defaultStats());

    renderPage();
    await screen.findByText(/Select a project first/i);
  });
});

// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

// Resolve a project id from the context store without a real store.
vi.mock('@/stores/useProjectContextStore', () => ({
  useProjectContextStore: (sel: (s: { activeProjectId: string }) => unknown) => sel({ activeProjectId: 'p-1' }),
}));

// Mock the feature api so no network happens.
vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    listConnectorSources: vi.fn(),
    createConnectorSource: vi.fn(),
    syncConnectorSource: vi.fn(),
  };
});

vi.mock('@/shared/lib/api', () => ({
  apiGet: vi.fn().mockResolvedValue([]),
  apiPost: vi.fn(),
  getErrorMessage: (e: unknown) => String(e),
}));

import { listConnectorSources, createConnectorSource, syncConnectorSource } from '../api';
import { ConnectorsPage } from '../ConnectorsPage';

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/connectors']}>
        <ConnectorsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listConnectorSources).mockResolvedValue([
    {
      id: 'src-1',
      project_id: 'p-1',
      kind: 'watched_folder',
      name: 'Site drop',
      root_path: '/data/inbound/site-a',
      enabled: true,
      last_synced_at: '2026-06-25T10:00:00Z',
      last_result: { created: 2, duplicate: 0, already_known: 1, total: 3, at: '2026-06-25T10:00:00Z' },
      created_at: '2026-06-25T09:00:00Z',
      updated_at: '2026-06-25T10:00:00Z',
    },
  ]);
  vi.mocked(createConnectorSource).mockResolvedValue({ id: 'src-2' } as never);
  vi.mocked(syncConnectorSource).mockResolvedValue({
    source_id: 'src-1',
    created: 1,
    duplicate: 0,
    already_known: 3,
    total: 4,
    created_document_ids: ['d-9'],
  });
});

describe('ConnectorsPage', () => {
  it('renders the title, the add form, and a registered source with its last sync', async () => {
    renderPage();
    expect(screen.getByRole('heading', { name: /Document Connectors/i })).toBeInTheDocument();
    expect(screen.getByText(/Add a watched folder/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('Site drop')).toBeInTheDocument();
    });
    expect(screen.getByText('/data/inbound/site-a')).toBeInTheDocument();
    expect(screen.getByText(/2 new, 0 duplicate, 1 already in/i)).toBeInTheDocument();
  });

  it('syncs a source when Sync now is clicked', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Site drop')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: /Sync now/i }));
    await waitFor(() => {
      expect(syncConnectorSource).toHaveBeenCalledWith('src-1');
    });
  });
});

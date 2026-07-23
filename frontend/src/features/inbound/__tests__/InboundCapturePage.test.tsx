// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

// Resolve a project id from the context store without a real store.
vi.mock('@/stores/useProjectContextStore', () => ({
  useProjectContextStore: (sel: (s: { activeProjectId: string }) => unknown) =>
    sel({ activeProjectId: 'p-1' }),
}));

vi.mock('../api', () => ({
  listCapturedMessages: vi.fn(),
}));

vi.mock('@/features/connectors/api', () => ({
  listConnectorSources: vi.fn(),
}));

vi.mock('@/shared/lib/api', () => ({
  apiGet: vi.fn().mockResolvedValue([]),
  getErrorMessage: (e: unknown) => String(e),
}));

import { listCapturedMessages } from '../api';
import { listConnectorSources } from '@/features/connectors/api';
import { InboundCapturePage } from '../InboundCapturePage';

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/inbound']}>
        <InboundCapturePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listCapturedMessages).mockResolvedValue({
    total: 1,
    items: [
      {
        correspondence_id: 'c-1',
        project_id: 'p-1',
        reference_number: 'COR-007',
        channel: 'email',
        external_message_id: 'msg-1',
        idempotency_key: 'k-1',
        direction: 'incoming',
        sender: 'site@example.com',
        recipients: ['pm@example.com'],
        sent_at: '2026-06-25T10:00:00Z',
        subject: 'Variation to access gate',
        body: 'Please advise.',
        in_reply_to: null,
        attachments: [{ filename: 'a.pdf', content_type: 'application/pdf', size_bytes: 10, storage_hint: null }],
        raw_refs: [],
        deduplicated: false,
      },
    ],
  });
  vi.mocked(listConnectorSources).mockResolvedValue([
    {
      id: 'src-1',
      project_id: 'p-1',
      kind: 'watched_folder',
      name: 'Site drop',
      root_path: '/data/inbound/site-a',
      enabled: true,
      last_synced_at: null,
      last_result: null,
      created_at: '2026-06-25T09:00:00Z',
      updated_at: '2026-06-25T09:00:00Z',
    },
  ]);
});

describe('InboundCapturePage', () => {
  it('renders captured messages and configured sources for the active project', async () => {
    renderPage();
    expect(screen.getByRole('heading', { name: /Inbound Capture/i })).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('COR-007')).toBeInTheDocument();
    });
    expect(screen.getByText(/Variation to access gate/i)).toBeInTheDocument();
    // The configured source is shown alongside the captured messages.
    expect(screen.getByText('Site drop')).toBeInTheDocument();
    expect(screen.getByText('/data/inbound/site-a')).toBeInTheDocument();
  });

  it('shows an empty state when nothing has been captured', async () => {
    vi.mocked(listCapturedMessages).mockResolvedValue({ total: 0, items: [] });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/Nothing captured yet/i)).toBeInTheDocument();
    });
  });
});

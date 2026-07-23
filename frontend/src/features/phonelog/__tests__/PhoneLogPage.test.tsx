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
    listPhoneLogs: vi.fn(),
    createPhoneLog: vi.fn(),
  };
});

vi.mock('@/shared/lib/api', () => ({
  apiGet: vi.fn().mockResolvedValue([]),
  apiPost: vi.fn(),
  getErrorMessage: (e: unknown) => String(e),
}));

import { listPhoneLogs, createPhoneLog } from '../api';
import { PhoneLogPage } from '../PhoneLogPage';

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/phone-log']}>
        <PhoneLogPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listPhoneLogs).mockResolvedValue([
    {
      id: 'pl-1',
      project_id: 'p-1',
      direction: 'inbound',
      channel: 'phone',
      parties: ['You', 'Acme site office'],
      occurred_at: '2026-06-25T09:00:00',
      duration_seconds: 300,
      transcript: 'Please change the door schedule.',
      summary: 'Change the door schedule',
      instructions: ['Please change the door schedule'],
      word_count: 5,
      audio_storage_key: '',
      status: 'logged',
      created_by: 'u-1',
      metadata: {},
      created_at: '2026-06-25T09:05:00Z',
      updated_at: '2026-06-25T09:05:00Z',
    },
  ]);
  vi.mocked(createPhoneLog).mockResolvedValue({ id: 'pl-2' } as never);
});

describe('PhoneLogPage', () => {
  it('renders the title, capture form, and the recent call from the log', async () => {
    renderPage();
    expect(screen.getByRole('heading', { name: /Phone Log/i })).toBeInTheDocument();
    expect(screen.getByText(/Capture a call/i)).toBeInTheDocument();
    // The mocked recent call renders, including its parties and its extracted instruction.
    await waitFor(() => {
      expect(screen.getByText(/Acme site office/i)).toBeInTheDocument();
    });
    expect(screen.getByText('Change the door schedule')).toBeInTheDocument();
    expect(screen.getByText(/Instructions captured/i)).toBeInTheDocument();
  });

  it('logs a call with the typed transcript and the chosen direction and channel', async () => {
    renderPage();
    fireEvent.change(screen.getByLabelText(/What was said/i), {
      target: { value: 'Please confirm the rebar spacing.' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Log the call/i }));
    await waitFor(() => {
      expect(createPhoneLog).toHaveBeenCalledWith(
        expect.objectContaining({
          project_id: 'p-1',
          transcript: 'Please confirm the rebar spacing.',
          direction: 'inbound',
          channel: 'phone',
        }),
      );
    });
  });
});

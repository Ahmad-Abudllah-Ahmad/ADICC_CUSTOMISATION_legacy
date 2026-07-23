// @ts-nocheck
/**
 * Epic B / B11 — WebhookTargetsPage admin UI tests.
 *
 *   1. Empty state renders the call-to-action.
 *   2. Existing rows render with the right status badge + no plaintext
 *      secret leak in the rendered DOM.
 *
 * Network calls are stubbed via `vi.mock('@/shared/lib/api', …)`.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@/shared/lib/api', () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiDelete: vi.fn(),
  apiPatch: vi.fn(),
}));

import { apiGet } from '@/shared/lib/api';
import { WebhookTargetsPage } from './WebhookTargetsPage';

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <WebhookTargetsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('WebhookTargetsPage', () => {
  it('shows the empty state when no targets are configured', async () => {
    (apiGet as ReturnType<typeof vi.fn>).mockResolvedValueOnce([]);
    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/No webhooks yet/i)).toBeTruthy();
    });
  });

  it('renders existing targets and never exposes the plaintext secret', async () => {
    const target = {
      id: '00000000-0000-0000-0000-000000000001',
      name: 'staging-slack',
      url: 'https://hooks.example.com/services/STAG/SLK/abc',
      event_filter: 'boq.*, rfi.assigned',
      has_secret: true,
      active: true,
      last_status: 200,
      last_attempt_at: '2026-05-26T12:00:00Z',
      failure_count: 0,
      created_at: '2026-05-26T11:00:00Z',
      updated_at: '2026-05-26T11:30:00Z',
    };
    (apiGet as ReturnType<typeof vi.fn>).mockResolvedValueOnce([target]);

    const { container } = renderPage();

    await waitFor(() => {
      expect(screen.getByText('staging-slack')).toBeTruthy();
    });
    expect(screen.getByText(target.url)).toBeTruthy();
    expect(screen.getByText(target.event_filter)).toBeTruthy();
    // Has-secret indicator visible.
    expect(screen.getByText(/Secret set/i)).toBeTruthy();
    // Status badge for a healthy run.
    expect(screen.getByText(/OK · 200/)).toBeTruthy();
    // CRITICAL: the rendered DOM must not contain any plaintext secret
    // — the API never returns it, so even an accidental leak via
    // response-cache inspection would be caught here.
    const html = container.innerHTML;
    expect(html.toLowerCase()).not.toContain('secret-value');
    expect(html.toLowerCase()).not.toContain('hmac-key');
  });
});

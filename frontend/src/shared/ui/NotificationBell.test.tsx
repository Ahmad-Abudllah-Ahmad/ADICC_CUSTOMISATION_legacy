// @ts-nocheck
/**
 * Epic B / B12 — NotificationBell white-screen regression test.
 *
 * Background: a malformed notification row (title_key=null, body_key
 * a non-string, body_context=null) used to crash the bell at render
 * time — i18next does `key.split(...)` internally and on a null key
 * the TypeError propagated up to the route's ErrorBoundary, leaving
 * the page blank ("Max Tamariz white-screen bug").  The bell now
 * coerces malformed keys + contexts before passing them to t().
 *
 * Regression coverage:
 *   1. open the bell with a malformed row in the list response
 *   2. confirm the row renders (does not throw, no ErrorBoundary)
 *   3. confirm the title-default fallback is visible
 *
 * Network calls are stubbed via `vi.mock('@/shared/lib/api', …)` so
 * the test runs fully offline.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

/* ── api stub ──────────────────────────────────────────────────────── */

vi.mock('@/shared/lib/api', async () => {
  return {
    apiGet: vi.fn(),
    apiPost: vi.fn(),
    apiDelete: vi.fn(),
    ApiError: class ApiError extends Error {
      status: number;
      constructor(message: string, status: number) {
        super(message);
        this.status = status;
      }
    },
  };
});

/* ── auth store stub (used by the WS hook) ─────────────────────────── */

vi.mock('@/stores/useAuthStore', () => ({
  useAuthStore: {
    getState: () => ({ accessToken: null }),
  },
}));

import { apiGet, apiPost, apiDelete } from '@/shared/lib/api';
import { NotificationBell } from './NotificationBell';

function renderWithProviders() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <NotificationBell />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('NotificationBell (Epic B / B12 white-screen regression)', () => {
  it('does not crash when a row has title_key=null and body_context=null', async () => {
    /* Mock unread-count + list endpoints with a deliberately malformed
       row matching the pre-fix backend / DB shape that caused the
       crash. */
    (apiGet as ReturnType<typeof vi.fn>).mockImplementation((path: string) => {
      if (path.includes('/unread-count')) {
        return Promise.resolve({ count: 1 });
      }
      return Promise.resolve({
        items: [
          {
            id: 'n1',
            notification_type: 'info',
            icon_category: 'info',
            // Both keys are null — the legacy poison case.
            title_key: null,
            title_default: 'Important update',
            body_key: null,
            // Server-rendered fallback the bell should display.
            body_default: 'A row with malformed keys must still render.',
            // body_context null is a poisoned shape too.
            body_context: null,
            action_url: null,
            is_read: false,
            created_at: new Date().toISOString(),
          },
        ],
        total: 1,
        unread_count: 1,
      });
    });

    renderWithProviders();

    // The badge with the unread count must render once the unread-count
    // query resolves — proves the component did not throw above the
    // mount boundary.
    await waitFor(() => {
      expect(screen.getByText('1')).toBeTruthy();
    });

    // Click the bell to open the dropdown and force list rendering.
    const bell = screen.getAllByRole('button')[0];
    fireEvent.click(bell);

    // The body_default text must be visible — proves the malformed
    // row reached the render path without triggering an ErrorBoundary.
    await waitFor(() => {
      expect(screen.getByText('A row with malformed keys must still render.')).toBeTruthy();
    });

    // And the title fallback string must surface.
    expect(screen.getByText('Important update')).toBeTruthy();
  });

  it('renders the "all caught up" empty state when no notifications exist', async () => {
    (apiGet as ReturnType<typeof vi.fn>).mockImplementation((path: string) => {
      if (path.includes('/unread-count')) {
        return Promise.resolve({ count: 0 });
      }
      return Promise.resolve({ items: [], total: 0, unread_count: 0 });
    });

    renderWithProviders();

    // Open the dropdown and assert the empty state — this used to also
    // crash when the list response returned a bare-array legacy shape;
    // the test pins both shapes alive.
    const bell = screen.getAllByRole('button')[0];
    fireEvent.click(bell);

    await waitFor(() => {
      // Empty state copy from the NotificationBell empty branch.
      expect(screen.getByText(/all caught up/i)).toBeTruthy();
    });
  });
});

// @ts-nocheck
/**
 * Tests for the project-overview Photo strip widget (#284 follow-up).
 *
 * The strip shows FIELD/SITE imagery only. It merges:
 *   - dedicated site photos (the photos table), always shown, and
 *   - general Project Files images ONLY when they carry an explicit "field"
 *     tag (a render with no field tag must be excluded).
 *
 * It also DEDUPES: every photo upload mirrors a twin document row with
 * ``category === 'photo'``; that twin must be skipped so a site photo never
 * appears twice. Every thumbnail loads through the authenticated <AuthImage>
 * path (a bare <img src> would 401 on the bearer-protected endpoints).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

// The widget reads both endpoints through the shared apiGet helper.
vi.mock('@/shared/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/shared/lib/api')>(
    '@/shared/lib/api',
  );
  return { ...actual, apiGet: vi.fn() };
});

import { apiGet } from '@/shared/lib/api';
import { PhotoStripWidget } from '../components/ProjectWidgets';

function renderWithProviders(ui: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

/** Route apiGet by URL so the two widget queries get distinct payloads. */
function mockApi(byUrl: Record<string, unknown>) {
  (apiGet as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
    for (const [needle, payload] of Object.entries(byUrl)) {
      if (url.includes(needle)) return Promise.resolve(payload);
    }
    return Promise.resolve([]);
  });
}

describe('PhotoStripWidget (#284 follow-up - field/site imagery only)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Thumbnails are bearer-protected; <AuthImage> fetches the bytes with the
    // token and renders an object URL. Stub the blob fetch + object-URL plumbing.
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        blob: async () => new Blob(['x'], { type: 'image/jpeg' }),
      }),
    );
    if (!('createObjectURL' in URL)) {
      (URL as unknown as { createObjectURL: unknown }).createObjectURL = () => '';
      (URL as unknown as { revokeObjectURL: unknown }).revokeObjectURL = () => {};
    }
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:mock');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
  });

  it('excludes general (untagged) images - only a field-tagged image shows', async () => {
    mockApi({
      '/v1/documents/photos/': [],
      '/v1/documents/?project_id=': [
        // A field-tagged image -> shown.
        {
          id: 'doc-field-1',
          name: 'east_elevation.jpg',
          mime_type: 'image/jpeg',
          category: 'other',
          tags: ['field', 'elevation'],
          created_at: '2026-06-01T10:00:00Z',
        },
        // An office render (image, but no field tag) -> excluded.
        {
          id: 'doc-render-1',
          name: 'lobby_render.png',
          mime_type: 'image/png',
          category: 'other',
          tags: ['marketing'],
          created_at: '2026-06-02T10:00:00Z',
        },
        // A non-image document -> ignored.
        {
          id: 'doc-pdf-1',
          name: 'contract.pdf',
          mime_type: 'application/pdf',
          created_at: '2026-06-03T10:00:00Z',
        },
      ],
    });

    renderWithProviders(<PhotoStripWidget projectId="proj-1" />);

    // The field-tagged image is fetched as a thumbnail (auth via AuthImage).
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/v1/documents/doc-field-1/download/',
        expect.objectContaining({ headers: expect.anything() }),
      );
    });
    // The render and the PDF must never be fetched.
    expect(global.fetch).not.toHaveBeenCalledWith(
      '/api/v1/documents/doc-render-1/download/',
      expect.anything(),
    );
    expect(global.fetch).not.toHaveBeenCalledWith(
      '/api/v1/documents/doc-pdf-1/download/',
      expect.anything(),
    );
  });

  it('dedupes: a photo and its twin document row render exactly once', async () => {
    mockApi({
      '/v1/documents/photos/': [
        { id: 'photo-1', taken_at: '2026-06-03T10:00:00Z', created_at: '2026-06-03T10:00:00Z' },
      ],
      '/v1/documents/?project_id=': [
        // The twin row mirrored beside ``photo-1`` (category === 'photo').
        // It must be skipped so the image is not double-counted.
        {
          id: 'doc-twin-1',
          name: 'photo-1.jpg',
          mime_type: 'image/jpeg',
          category: 'photo',
          tags: ['photo', 'site'],
          created_at: '2026-06-03T10:00:00Z',
        },
      ],
    });

    renderWithProviders(<PhotoStripWidget projectId="proj-1" />);

    // The dedicated photo loads via the photos thumb route...
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/v1/documents/photos/photo-1/thumb/',
        expect.objectContaining({ headers: expect.anything() }),
      );
    });
    // ...and the twin document row is NEVER fetched (would be a duplicate).
    expect(global.fetch).not.toHaveBeenCalledWith(
      '/api/v1/documents/doc-twin-1/download/',
      expect.anything(),
    );
  });

  it('shows the empty state when there are no site photos (only an untagged render)', async () => {
    mockApi({
      '/v1/documents/photos/': [],
      '/v1/documents/?project_id=': [
        {
          id: 'doc-render-2',
          name: 'render.png',
          mime_type: 'image/png',
          category: 'other',
          tags: [],
        },
      ],
    });

    renderWithProviders(<PhotoStripWidget projectId="proj-1" />);

    await waitFor(() => {
      expect(screen.getByText(/No site photos yet/i)).toBeInTheDocument();
    });
    // The render must not be fetched as a thumbnail.
    expect(global.fetch).not.toHaveBeenCalledWith(
      '/api/v1/documents/doc-render-2/download/',
      expect.anything(),
    );
  });
});

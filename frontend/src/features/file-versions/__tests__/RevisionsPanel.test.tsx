// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/** Unit tests for the RevisionsPanel and StaleVersionPill components.
 *
 *  Covers the two frontend Epic C deliverables:
 *
 *   1. ``RevisionsPanel`` renders the chain, exposes "Make current"
 *      and "Upload new revision" actions, fires the restore mutation.
 *   2. ``StaleVersionPill`` renders the "Drawn on V01 · current is V02"
 *      label when the pinned version is not the chain head, AND stays
 *      hidden when the pinned version IS the head (or pinned is NULL).
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../api', () => ({
  listVersions: vi.fn(),
  restoreVersion: vi.fn(),
  fileVersionKeys: { list: 'file-versions-list', detail: 'file-versions-detail' },
}));

vi.mock('@/stores/useToastStore', () => {
  const addToast = vi.fn();
  return {
    useToastStore: Object.assign(
      (selector: (s: { addToast: typeof addToast }) => unknown) =>
        selector({ addToast }),
      { getState: () => ({ addToast }) },
    ),
    __addToast: addToast,
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
  // ``src/app/i18n.ts`` is pulled in transitively and calls
  // ``.use(initReactI18next)`` at module load — expose the noop plugin.
  initReactI18next: { type: '3rdParty', init: () => {} },
}));

import * as api from '../api';
import { RevisionsPanel } from '../RevisionsPanel';
import { StaleVersionPill } from '../StaleVersionPill';
import type { FileVersionResponse } from '../types';

const listMock = api.listVersions as unknown as ReturnType<typeof vi.fn>;
const restoreMock = api.restoreVersion as unknown as ReturnType<typeof vi.fn>;

function makeVersion(
  overrides: Partial<FileVersionResponse> & { id: string; version_number: number },
): FileVersionResponse {
  return {
    project_id: 'proj-001',
    file_kind: 'document',
    file_id: 'file-001',
    canonical_name: 'plans.pdf',
    previous_version_id: null,
    is_current: false,
    superseded_at: null,
    superseded_by_id: null,
    notes: null,
    uploaded_by_id: null,
    uploaded_at: '2026-05-25T12:00:00Z',
    file_size: 1024,
    checksum: null,
    created_at: '2026-05-25T12:00:00Z',
    updated_at: '2026-05-25T12:00:00Z',
    ...overrides,
  };
}

function renderWithClient(node: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

beforeEach(() => {
  listMock.mockReset();
  restoreMock.mockReset();
  cleanup();
});

describe('RevisionsPanel', () => {
  it('renders the chain newest-first and fires restore on click', async () => {
    listMock.mockResolvedValue([
      makeVersion({ id: 'v3', version_number: 3, is_current: true, notes: 'rev C' }),
      makeVersion({ id: 'v2', version_number: 2, notes: 'rev B' }),
      makeVersion({ id: 'v1', version_number: 1 }),
    ]);
    restoreMock.mockResolvedValue(
      makeVersion({ id: 'v1', version_number: 1, is_current: true }),
    );

    const onRestored = vi.fn();
    renderWithClient(
      <RevisionsPanel
        fileId="file-001"
        kind="document"
        canUploadNewRevision
        onUploadNew={vi.fn()}
        onRestored={onRestored}
      />,
    );

    await screen.findByTestId('revisions-list');

    // All three rows are rendered.
    expect(screen.getByTestId('revisions-row-3')).toBeTruthy();
    expect(screen.getByTestId('revisions-row-2')).toBeTruthy();
    expect(screen.getByTestId('revisions-row-1')).toBeTruthy();

    // Current row has no restore button; historical rows do.
    expect(screen.queryByTestId('revisions-restore-3')).toBeNull();
    expect(screen.getByTestId('revisions-restore-2')).toBeTruthy();
    expect(screen.getByTestId('revisions-restore-1')).toBeTruthy();

    // Upload-new CTA is rendered when permission flag is on.
    expect(screen.getByTestId('revisions-upload-new')).toBeTruthy();

    // Click "Make current" on V01 → restore mutation fires.
    await act(async () => {
      fireEvent.click(screen.getByTestId('revisions-restore-1'));
    });

    await waitFor(() => {
      expect(restoreMock).toHaveBeenCalledWith('v1');
    });
    await waitFor(() => {
      expect(onRestored).toHaveBeenCalledWith('v1');
    });
  });

  it('hides the upload CTA when canUploadNewRevision is false', async () => {
    listMock.mockResolvedValue([
      makeVersion({ id: 'v1', version_number: 1, is_current: true }),
    ]);
    renderWithClient(
      <RevisionsPanel fileId="file-001" kind="document" />,
    );
    await screen.findByTestId('revisions-list');
    expect(screen.queryByTestId('revisions-upload-new')).toBeNull();
  });

  it('shows the empty state when the chain is empty', async () => {
    listMock.mockResolvedValue([]);
    renderWithClient(
      <RevisionsPanel fileId="file-001" kind="document" />,
    );
    await waitFor(() => {
      expect(
        screen.getByText(/No revisions yet/),
      ).toBeTruthy();
    });
  });
});

describe('StaleVersionPill', () => {
  it('renders "Drawn on V01 · current is V02" when pinned is stale', async () => {
    listMock.mockResolvedValue([
      makeVersion({ id: 'v2', version_number: 2, is_current: true }),
      makeVersion({ id: 'v1', version_number: 1 }),
    ]);
    renderWithClient(
      <StaleVersionPill fileId="file-001" kind="document" pinnedVersionId="v1" />,
    );
    await waitFor(() => {
      const pill = screen.getByTestId('stale-version-pill');
      expect(pill).toBeTruthy();
      expect(pill.textContent ?? '').toMatch(/V01/);
      expect(pill.textContent ?? '').toMatch(/V02/);
    });
  });

  it('renders nothing when pinned version IS the chain head', async () => {
    listMock.mockResolvedValue([
      makeVersion({ id: 'v2', version_number: 2, is_current: true }),
      makeVersion({ id: 'v1', version_number: 1 }),
    ]);
    const { container } = renderWithClient(
      <StaleVersionPill fileId="file-001" kind="document" pinnedVersionId="v2" />,
    );
    await waitFor(() => {
      // No pill — the wrapper component returns null.
      expect(container.querySelector('[data-testid="stale-version-pill"]')).toBeNull();
    });
  });

  it('renders nothing when pinned version is NULL (legacy markup)', async () => {
    listMock.mockResolvedValue([
      makeVersion({ id: 'v2', version_number: 2, is_current: true }),
    ]);
    const { container } = renderWithClient(
      <StaleVersionPill fileId="file-001" kind="document" pinnedVersionId={null} />,
    );
    expect(container.querySelector('[data-testid="stale-version-pill"]')).toBeNull();
  });
});

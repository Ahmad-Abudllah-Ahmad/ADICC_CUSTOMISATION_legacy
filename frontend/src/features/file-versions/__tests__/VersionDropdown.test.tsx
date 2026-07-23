// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/** Unit tests for VersionDropdown.
 *
 * Mocks the ``./api`` module so we don't hit the network. Verifies:
 *   1. The chain is rendered, current row badged "Current".
 *   2. Clicking "Make current" on a historical row fires the restore
 *      mutation with the right id.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { act, render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../api', () => {
  return {
    listVersions: vi.fn(),
    restoreVersion: vi.fn(),
    fileVersionKeys: { list: 'file-versions-list', detail: 'file-versions-detail' },
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
import { VersionDropdown } from '../VersionDropdown';
import type { FileVersionResponse } from '../types';

const listMock = api.listVersions as unknown as ReturnType<typeof vi.fn>;
const restoreMock = api.restoreVersion as unknown as ReturnType<typeof vi.fn>;

function makeVersion(
  overrides: Partial<FileVersionResponse> & { version_number: number; id: string },
): FileVersionResponse {
  const base: FileVersionResponse = {
    id: overrides.id,
    project_id: 'proj-001',
    file_kind: 'document',
    file_id: 'file-001',
    version_number: overrides.version_number,
    canonical_name: 'plans.pdf',
    previous_version_id: null,
    is_current: false,
    superseded_at: null,
    superseded_by_id: null,
    notes: null,
    uploaded_by_id: null,
    uploaded_at: '2026-05-19T12:00:00Z',
    file_size: 4096,
    checksum: null,
    created_at: '2026-05-19T12:00:00Z',
    updated_at: '2026-05-19T12:00:00Z',
  };
  return { ...base, ...overrides };
}

function renderDropdown(props: { fileId?: string; kind?: 'document' } = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <VersionDropdown
        fileId={props.fileId ?? 'file-001'}
        kind={props.kind ?? 'document'}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  listMock.mockReset();
  restoreMock.mockReset();
  cleanup();
});

describe('VersionDropdown', () => {
  it('renders the chain with the current row badged', async () => {
    listMock.mockResolvedValue([
      makeVersion({ id: 'v3', version_number: 3, is_current: true, notes: 'rev C' }),
      makeVersion({ id: 'v2', version_number: 2, notes: 'rev B' }),
      makeVersion({ id: 'v1', version_number: 1 }),
    ]);

    renderDropdown();

    // Wait for the chain to load AND the button to be enabled (data
    // present + isLoading flipped to false). Without this gate the
    // first click can fire while ``isLoading`` is still true, which
    // the button rejects via the disabled flag — the click is a no-op
    // and the dropdown never opens.
    const btn = await screen.findByTestId('version-dropdown-button');
    await waitFor(() => {
      expect(btn.hasAttribute('disabled')).toBe(false);
    });
    expect(btn.textContent ?? '').toMatch(/V03/);

    await act(async () => {
      fireEvent.click(btn);
    });

    // All three rows are rendered in the listbox.
    await screen.findByTestId('version-row-3');
    expect(screen.getByTestId('version-row-3')).toBeTruthy();
    expect(screen.getByTestId('version-row-2')).toBeTruthy();
    expect(screen.getByTestId('version-row-1')).toBeTruthy();

    // The current row has no restore button.
    expect(screen.queryByTestId('version-restore-3')).toBeNull();
    // Historical rows expose "Make current".
    expect(screen.getByTestId('version-restore-2')).toBeTruthy();
    expect(screen.getByTestId('version-restore-1')).toBeTruthy();
  });

  it('calls restoreVersion when "Make current" is clicked', async () => {
    listMock.mockResolvedValue([
      makeVersion({ id: 'v2', version_number: 2, is_current: true }),
      makeVersion({ id: 'v1', version_number: 1 }),
    ]);
    restoreMock.mockResolvedValue(
      makeVersion({ id: 'v1', version_number: 1, is_current: true }),
    );

    const onChange = vi.fn();
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    render(
      <QueryClientProvider client={client}>
        <VersionDropdown fileId="file-001" kind="document" onChange={onChange} />
      </QueryClientProvider>,
    );

    const btn = await screen.findByTestId('version-dropdown-button');
    await waitFor(() => {
      expect(btn.hasAttribute('disabled')).toBe(false);
    });
    await act(async () => {
      fireEvent.click(btn);
    });
    const restoreBtn = await screen.findByTestId('version-restore-1');
    await act(async () => {
      fireEvent.click(restoreBtn);
    });

    await waitFor(() => {
      expect(restoreMock).toHaveBeenCalledWith('v1');
    });
    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith('v1');
    });
  });

  it('shows "No history" when the chain is empty', async () => {
    listMock.mockResolvedValue([]);
    renderDropdown();

    const btn = await screen.findByTestId('version-dropdown-button');
    expect(btn.textContent ?? '').toMatch(/No history/);
  });

  it('renders the load-failed badge on API error', async () => {
    listMock.mockRejectedValue(new Error('boom'));
    renderDropdown();
    await waitFor(() => {
      expect(screen.getByText(/Versions unavailable/)).toBeTruthy();
    });
  });
});

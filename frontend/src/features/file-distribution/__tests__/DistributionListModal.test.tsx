// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// DistributionListModal unit tests.
//
// Covers:
//   1. Renders overview with one row per list returned by API.
//   2. "New list" button toggles the create form.
//   3. Submitting create calls the create mutation.
//   4. Opening a list shows its members; "Add member" calls the
//      add-member mutation.
//   5. Members can be removed via the X button.

import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

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

/* ── API mocks ─────────────────────────────────────────────────────── */

const fetchListsMock = vi.fn<(...args: unknown[]) => Promise<unknown>>();
const createListMock = vi.fn<(...args: unknown[]) => Promise<unknown>>();
const updateListMock = vi.fn<(...args: unknown[]) => Promise<unknown>>();
const deleteListMock = vi.fn<(...args: unknown[]) => Promise<unknown>>();
const addMemberMock = vi.fn<(...args: unknown[]) => Promise<unknown>>();
const removeMemberMock = vi.fn<(...args: unknown[]) => Promise<unknown>>();

vi.mock('../api', () => ({
  fetchDistributionLists: (...args: unknown[]) => fetchListsMock(...args),
  createDistributionList: (...args: unknown[]) => createListMock(...args),
  updateDistributionList: (...args: unknown[]) => updateListMock(...args),
  deleteDistributionList: (...args: unknown[]) => deleteListMock(...args),
  addDistributionMember: (...args: unknown[]) => addMemberMock(...args),
  removeDistributionMember: (...args: unknown[]) => removeMemberMock(...args),
  // Hooks pull the remaining api functions too — supply harmless stubs:
  globalFileSearch: vi.fn(),
  fetchSubscriptions: vi.fn(),
  createSubscription: vi.fn(),
  deleteSubscription: vi.fn(),
}));

import { DistributionListModal } from '../DistributionListModal';
import type { DistributionList } from '../types';

/* ── Fixtures ──────────────────────────────────────────────────────── */

const PROJECT_ID = 'proj-001';

function listFixture(overrides: Partial<DistributionList> = {}): DistributionList {
  return {
    id: 'list-1',
    owner_id: 'user-1',
    project_id: PROJECT_ID,
    name: 'Structural Review',
    description: null,
    is_shared: false,
    members: [],
    created_at: '2026-05-19T00:00:00Z',
    updated_at: '2026-05-19T00:00:00Z',
    is_own: true,
    ...overrides,
  };
}

function renderModal(items: DistributionList[], initialListId: string | null = null) {
  fetchListsMock.mockResolvedValue({ items, total: items.length });
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <DistributionListModal
        open
        onClose={() => undefined}
        projectId={PROJECT_ID}
        initialListId={initialListId}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  fetchListsMock.mockReset();
  createListMock.mockReset();
  updateListMock.mockReset();
  deleteListMock.mockReset();
  addMemberMock.mockReset();
  removeMemberMock.mockReset();
});

afterEach(() => {
  cleanup();
});

/* ── Tests ─────────────────────────────────────────────────────────── */

describe('DistributionListModal', () => {
  it('renders overview with one row per list', async () => {
    renderModal([
      listFixture({ id: 'a', name: 'Structural Review' }),
      listFixture({ id: 'b', name: 'MEP Coordination' }),
    ]);
    expect(await screen.findByText('Structural Review')).toBeTruthy();
    expect(screen.getByText('MEP Coordination')).toBeTruthy();
    expect(screen.getByTestId('distribution-open-a')).toBeTruthy();
    expect(screen.getByTestId('distribution-open-b')).toBeTruthy();
  });

  it('shows the "New list" CTA and reveals an inline create form on click', async () => {
    renderModal([]);
    const cta = await screen.findByTestId('distribution-new-list-button');
    fireEvent.click(cta);
    expect(screen.getByTestId('distribution-new-list-name')).toBeTruthy();
  });

  it('submitting the create form calls createDistributionList', async () => {
    createListMock.mockResolvedValue(
      listFixture({ id: 'fresh', name: 'Brand New' }),
    );
    renderModal([]);
    fireEvent.click(await screen.findByTestId('distribution-new-list-button'));
    const nameInput = screen.getByTestId('distribution-new-list-name') as HTMLInputElement;
    fireEvent.change(nameInput, { target: { value: 'Brand New' } });
    fireEvent.click(screen.getByText('Create'));
    await waitFor(() => {
      expect(createListMock).toHaveBeenCalled();
    });
    expect(createListMock.mock.calls[0]?.[0]).toMatchObject({
      name: 'Brand New',
      project_id: PROJECT_ID,
    });
  });

  it('opening a list shows the members + add-member form', async () => {
    renderModal(
      [
        listFixture({
          id: 'list-1',
          name: 'Structural Review',
          members: [
            {
              id: 'm-1',
              list_id: 'list-1',
              email: 'lena@example.com',
              display_name: 'Lena Schmidt',
              role: 'for_review',
              created_at: '2026-05-19T00:00:00Z',
            },
          ],
        }),
      ],
      'list-1',
    );
    await screen.findByTestId('distribution-list-detail');
    expect(screen.getByText('Lena Schmidt')).toBeTruthy();
    expect(screen.getByText('lena@example.com')).toBeTruthy();
    expect(screen.getByTestId('distribution-new-member-email')).toBeTruthy();
  });

  it('add-member submit calls addDistributionMember', async () => {
    addMemberMock.mockResolvedValue({
      id: 'm-2',
      list_id: 'list-1',
      email: 'raj@example.com',
      display_name: null,
      role: 'fyi',
      created_at: '2026-05-19T00:00:00Z',
    });
    renderModal(
      [listFixture({ id: 'list-1', name: 'Structural Review' })],
      'list-1',
    );
    await screen.findByTestId('distribution-list-detail');
    const emailInput = screen.getByTestId('distribution-new-member-email') as HTMLInputElement;
    fireEvent.change(emailInput, { target: { value: 'raj@example.com' } });
    fireEvent.click(screen.getByTestId('distribution-add-member'));
    await waitFor(() => {
      expect(addMemberMock).toHaveBeenCalled();
    });
    expect(addMemberMock.mock.calls[0]?.[0]).toBe('list-1');
    expect(addMemberMock.mock.calls[0]?.[1]).toMatchObject({
      email: 'raj@example.com',
    });
  });

  it('clicking remove-member calls removeDistributionMember', async () => {
    removeMemberMock.mockResolvedValue(undefined);
    renderModal(
      [
        listFixture({
          id: 'list-1',
          members: [
            {
              id: 'm-1',
              list_id: 'list-1',
              email: 'lena@example.com',
              display_name: null,
              role: null,
              created_at: '2026-05-19T00:00:00Z',
            },
          ],
        }),
      ],
      'list-1',
    );
    await screen.findByTestId('distribution-list-detail');
    fireEvent.click(screen.getByTestId('distribution-remove-member-m-1'));
    await waitFor(() => {
      expect(removeMemberMock).toHaveBeenCalledWith('list-1', 'm-1');
    });
  });
});

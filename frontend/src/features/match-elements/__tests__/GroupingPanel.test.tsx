// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Stage-5 ("Grouping") panel — Phase-0 preset-bar contract.
//
// Clicking the "Level + IFC class" preset MUST PATCH the session with
// ``group_by: ["level", "ifc_class"]``. The matcher pipeline keys its
// rebuild_groups call off this field, so the FE preset contract is the
// difference between the user's intent ("group by level then class") and
// the server's default (ifc_class + type_name). Pin it here.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  render,
  screen,
  cleanup,
  fireEvent,
  waitFor,
} from '@testing-library/react';
import { QueryClient, QueryClientProvider, useMutation, useQuery } from '@tanstack/react-query';

// Mock the api surface BEFORE importing the panel so its updateSession
// import binds to the spy.
vi.mock('../api', () => ({
  matchElementsApi: {
    updateSession: vi.fn().mockResolvedValue({
      id: 'sess-1',
      group_by: ['level', 'ifc_class'],
    }),
    listAttributes: vi.fn().mockResolvedValue([
      { key: 'ifc_class', sample_values: [] },
      { key: 'type_name', sample_values: [] },
      { key: 'level', sample_values: [] },
      { key: 'material', sample_values: [] },
    ]),
  },
}));

// Toast store noop — the panel only calls addToast on error, but the
// component imports it on every render.
vi.mock('@/stores/useToastStore', () => ({
  useToastStore: (selector: (state: { addToast: () => void }) => unknown) =>
    selector({ addToast: () => {} }),
}));

import { matchElementsApi } from '../api';
import { GroupingPanel } from '../GroupingPanel';

const updateSessionSpy = matchElementsApi.updateSession as ReturnType<typeof vi.fn>;

function renderPanel() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  // The panel expects a UseQueryResult + UseMutationResult. We construct
  // them inside a wrapper component so React Query owns their identity.
  function Wrapper() {
    const groupsQ = useQuery({
      queryKey: ['match-groups', 'sess-1'],
      queryFn: async () => ({
        session_id: 'sess-1',
        total: 0,
        groups: [],
        summary: {},
        confidence_high_threshold: 0.85,
        confidence_medium_threshold: 0.6,
      }),
    });
    const updateSessionM = useMutation({
      mutationFn: async (_id: string) => ({ id: 'sess-1' }),
    });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return <GroupingPanel sessionId="sess-1" groupsQ={groupsQ as any} updateSessionM={updateSessionM as any} />;
  }

  return render(
    <QueryClientProvider client={client}>
      <Wrapper />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  updateSessionSpy.mockClear();
});

afterEach(() => {
  cleanup();
});

describe('GroupingPanel - Phase 0 preset contract', () => {
  it('writes group_by ["level", "ifc_class"] when the Level + IFC class preset is clicked', async () => {
    renderPanel();

    const presetBtn = await screen.findByTestId('grouping-preset-level_ifc');
    fireEvent.click(presetBtn);

    await waitFor(() => {
      expect(updateSessionSpy).toHaveBeenCalledWith('sess-1', {
        group_by: ['level', 'ifc_class'],
      });
    });
  });
});


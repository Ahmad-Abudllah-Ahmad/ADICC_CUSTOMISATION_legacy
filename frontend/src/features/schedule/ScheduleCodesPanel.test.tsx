// @ts-nocheck
/**
 * Smoke tests for the activity codes / UDFs / saved layouts panel (T2.3).
 *
 * Network is stubbed via ``vi.mock`` on the schedule ``./api`` module (the
 * panel calls ``scheduleApi.*``). React Query retries are disabled so empty /
 * error states surface immediately. We assert the panel heading, the three
 * tabs, and that each tab's list / empty state renders.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

vi.mock('./api', async () => {
  const actual = await vi.importActual<typeof import('./api')>('./api');
  return {
    // Keep the pure helpers + constants real; stub the network surface.
    buildLayoutSpec: actual.buildLayoutSpec,
    GROUP_NONE_KEY: actual.GROUP_NONE_KEY,
    scheduleApi: {
      listCodeDictionaries: vi.fn(),
      createCodeDictionary: vi.fn(),
      deleteCodeDictionary: vi.fn(),
      listLibraryDictionaries: vi.fn(),
      importLibraryDictionary: vi.fn(),
      listCodeValues: vi.fn(),
      createCodeValue: vi.fn(),
      deleteCodeValue: vi.fn(),
      listUdfs: vi.fn(),
      createUdf: vi.fn(),
      deleteUdf: vi.fn(),
      listLayouts: vi.fn(),
      createLayout: vi.fn(),
      deleteLayout: vi.fn(),
      groupedActivities: vi.fn(),
    },
  };
});

import { scheduleApi } from './api';
import { ScheduleCodesPanel } from './ScheduleCodesPanel';

const DICTS = [
  {
    id: 'dict-1',
    project_id: 'p1',
    is_library: false,
    name: 'Area',
    description: 'Project areas',
    color_band: true,
    sort_order: 0,
  },
];

const VALUES = [
  {
    id: 'val-1',
    dictionary_id: 'dict-1',
    parent_id: null,
    code: 'A1',
    label: 'Block A',
    color: '#2563eb',
    depth: 0,
    sort_order: 0,
  },
];

const UDFS = [
  {
    id: 'udf-1',
    project_id: 'p1',
    key: 'cost_code',
    label: 'Cost code',
    value_type: 'text',
    enum_values: [],
    sort_order: 0,
  },
];

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ScheduleCodesPanel scheduleId="s1" projectId="p1" />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ScheduleCodesPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Sensible defaults; individual tests override as needed.
    (scheduleApi.listCodeDictionaries as any).mockResolvedValue([]);
    (scheduleApi.listUdfs as any).mockResolvedValue([]);
    (scheduleApi.listLayouts as any).mockResolvedValue([]);
    (scheduleApi.listCodeValues as any).mockResolvedValue([]);
    (scheduleApi.listLibraryDictionaries as any).mockResolvedValue([]);
  });

  it('renders the panel heading and the three tabs', async () => {
    renderPanel();
    expect(await screen.findByTestId('schedule-codes-panel')).toBeInTheDocument();
    expect(screen.getByText(/Activity codes, fields & layouts/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Dictionaries & values/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /User-defined fields/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Grouped view/i })).toBeInTheDocument();
  });

  it('lists code dictionaries on the dictionaries tab', async () => {
    (scheduleApi.listCodeDictionaries as any).mockResolvedValue(DICTS);
    renderPanel();
    const list = await screen.findByTestId('codes-dictionary-list');
    expect(list.textContent).toMatch(/Area/);
  });

  it('shows the empty state when there are no dictionaries', async () => {
    (scheduleApi.listCodeDictionaries as any).mockResolvedValue([]);
    renderPanel();
    expect(await screen.findByText(/No code dictionaries yet/i)).toBeInTheDocument();
  });

  it('selecting a dictionary loads and lists its values', async () => {
    (scheduleApi.listCodeDictionaries as any).mockResolvedValue(DICTS);
    (scheduleApi.listCodeValues as any).mockResolvedValue(VALUES);
    renderPanel();

    fireEvent.click(await screen.findByText(/Area/));

    const values = await screen.findByTestId('codes-value-list');
    expect(values.textContent).toMatch(/A1/);
    await waitFor(() => {
      expect(scheduleApi.listCodeValues).toHaveBeenCalledWith('dict-1');
    });
  });

  it('lists user-defined fields on the UDFs tab', async () => {
    (scheduleApi.listUdfs as any).mockResolvedValue(UDFS);
    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: /User-defined fields/i }));

    const list = await screen.findByTestId('codes-udf-list');
    expect(list.textContent).toMatch(/cost_code/);
  });

  it('shows the grouped-view empty prompt and saved-layouts list', async () => {
    (scheduleApi.listCodeDictionaries as any).mockResolvedValue(DICTS);
    (scheduleApi.listLayouts as any).mockResolvedValue([]);
    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: /Grouped view/i }));

    // The grid prompts to run a grouped view, and the saved-layouts empty
    // state renders (the layouts query resolves asynchronously).
    expect(await screen.findByText(/Run a grouped view/i)).toBeInTheDocument();
    expect(await screen.findByText(/No saved layouts yet/i)).toBeInTheDocument();
  });
});

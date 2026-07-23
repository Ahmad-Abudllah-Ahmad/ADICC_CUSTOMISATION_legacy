// @ts-nocheck
/**
 * SmartViewPresetsTab — install-cards UI tests.
 *
 * Covers:
 *   • Loading skeleton on initial fetch
 *   • Renders all 6 catalogue cards
 *   • Install click POSTs the right body and toasts on success
 *   • Error state when the catalogue fetch fails
 */
import {
  describe,
  it,
  expect,
  beforeAll,
  beforeEach,
  afterEach,
  afterAll,
  vi,
} from 'vitest';
import {
  render,
  screen,
  fireEvent,
  cleanup,
  act,
  waitFor,
} from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { SmartViewPresetsTab } from '../SmartViewPresetsTab';

const USER_ID = '00000000-0000-0000-0000-000000000001';

const PRESETS = [
  {
    preset_id: 'walls_by_fire_rating',
    category: 'structure',
    name: 'Walls by fire rating',
    description: 'Colour walls by FireRating.',
    rule_count: 1,
  },
  {
    preset_id: 'mep_by_discipline',
    category: 'mep',
    name: 'MEP by discipline',
    description: 'Colour MEP by discipline.',
    rule_count: 3,
  },
  {
    preset_id: 'structural_concrete_c30',
    category: 'structure',
    name: 'Structural concrete C30/37+',
    description: 'Highlight structural concrete.',
    rule_count: 3,
  },
  {
    preset_id: 'doors_fire_rated',
    category: 'doors',
    name: 'Fire-rated doors',
    description: 'Highlight fire-rated doors.',
    rule_count: 2,
  },
  {
    preset_id: 'exterior_walls',
    category: 'envelope',
    name: 'Exterior walls only',
    description: 'Show exterior walls.',
    rule_count: 2,
  },
  {
    preset_id: 'spaces_by_zone',
    category: 'spaces',
    name: 'Spaces by zone',
    description: 'Colour spaces by zone.',
    rule_count: 1,
  },
];

let lastInstallPresetId: string | null = null;
let lastInstallBody: Record<string, unknown> | null = null;
let presetListShouldError = false;

const server = setupServer(
  http.get('*/api/v1/smart-views/presets', () => {
    if (presetListShouldError)
      return new HttpResponse(null, { status: 500 });
    return HttpResponse.json(PRESETS);
  }),
  http.post(
    '*/api/v1/smart-views/presets/:presetId/install',
    async ({ params, request }) => {
      lastInstallPresetId = params.presetId as string;
      lastInstallBody = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json(
        {
          id: `inst-${lastInstallPresetId}`,
          scope_type: lastInstallBody.scope_type,
          scope_id: lastInstallBody.scope_id,
          name: 'Installed',
          description: null,
          rules: [],
          default_action: 'show_all',
          color_legend: null,
          created_by: USER_ID,
          created_at: '2026-05-21T00:00:00Z',
          updated_at: '2026-05-21T00:00:00Z',
          share_token: null,
        },
        { status: 201 },
      );
    },
  ),
);

beforeAll(() => {
  server.listen({ onUnhandledRequest: 'warn' });
  const mswFetch = globalThis.fetch;
  globalThis.fetch = ((input, init) => {
    if (init && 'signal' in init) {
      const { signal: _signal, ...rest } = init;
      return mswFetch(input, rest);
    }
    return mswFetch(input, init);
  }) as typeof fetch;
});
beforeEach(() => {
  lastInstallPresetId = null;
  lastInstallBody = null;
  presetListShouldError = false;
});
afterEach(() => {
  server.resetHandlers();
  cleanup();
});
afterAll(() => server.close());

function renderTab(onInstalled?: () => void) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SmartViewPresetsTab
        scopeType="user"
        scopeId={USER_ID}
        onInstalled={onInstalled}
      />
    </QueryClientProvider>,
  );
}

describe('SmartViewPresetsTab', () => {
  it('shows a loading skeleton before the catalogue arrives', async () => {
    renderTab();
    expect(
      screen.getByTestId('smart-view-presets-loading'),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId('smart-view-presets')).toBeInTheDocument();
    });
  });

  it('renders all 6 catalogue cards', async () => {
    renderTab();
    await waitFor(() => {
      expect(screen.getByTestId('smart-view-presets')).toBeInTheDocument();
    });
    for (const p of PRESETS) {
      expect(
        screen.getByTestId(`smart-view-preset-${p.preset_id}`),
      ).toBeInTheDocument();
    }
    // Install buttons too.
    expect(
      screen.getAllByRole('button', { name: /install/i }).length,
    ).toBeGreaterThanOrEqual(6);
  });

  it('install click POSTs the preset id + scope and fires onInstalled', async () => {
    const onInstalled = vi.fn();
    renderTab(onInstalled);
    await waitFor(() => {
      expect(
        screen.getByTestId('smart-view-preset-walls_by_fire_rating'),
      ).toBeInTheDocument();
    });
    await act(async () => {
      fireEvent.click(
        screen.getByTestId(
          'smart-view-preset-install-walls_by_fire_rating',
        ),
      );
    });
    await waitFor(() => expect(lastInstallPresetId).toBe('walls_by_fire_rating'));
    expect(lastInstallBody).toEqual({
      scope_type: 'user',
      scope_id: USER_ID,
    });
    await waitFor(() => expect(onInstalled).toHaveBeenCalled());
  });

  it('renders an error state if the catalogue fetch fails', async () => {
    presetListShouldError = true;
    renderTab();
    await waitFor(() => {
      expect(
        screen.getByTestId('smart-view-presets-error'),
      ).toBeInTheDocument();
    });
  });
});

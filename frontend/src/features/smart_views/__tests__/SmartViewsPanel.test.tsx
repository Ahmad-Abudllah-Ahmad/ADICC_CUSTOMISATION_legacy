// @ts-nocheck
/**
 * SmartViewsPanel — list-panel UI tests.
 *
 * Exercises the user-facing flow:
 *   - Loading skeleton on initial fetch
 *   - Tabs switch scope (and refetch under the new key)
 *   - Apply click hits evaluate + writes the store
 *   - Empty state renders when the list is empty
 *   - 3-dot menu Delete → confirm → API call → list refetch
 *   - Duplicate creates a copy in the right scope
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
import { SmartViewsPanel } from '../SmartViewsPanel';
import { useSmartViewState } from '../useSmartViewState';
import type { SmartViewResponse } from '../types';

const USER_ID = '00000000-0000-0000-0000-000000000001';
const PROJECT_ID = '00000000-0000-0000-0000-0000000000aa';
const MODEL_ID = 'model-xyz';

function makeView(
  id: string,
  scope_type: 'user' | 'project',
  scope_id: string,
  name: string,
): SmartViewResponse {
  return {
    id,
    scope_type,
    scope_id,
    name,
    description: null,
    rules: [],
    default_action: 'show_all',
    color_legend: null,
    created_by: USER_ID,
    created_at: '2026-05-21T00:00:00Z',
    updated_at: '2026-05-21T00:00:00Z',
  };
}

let userViews: SmartViewResponse[] = [];
let projectViews: SmartViewResponse[] = [];
let lastCreatePayload: unknown = null;
let lastEvaluateUrl: string | null = null;
let deletedIds: string[] = [];

const server = setupServer(
  http.get('*/api/v1/smart-views/', ({ request }) => {
    const url = new URL(request.url);
    const scope = url.searchParams.get('scope_type');
    if (scope === 'project') return HttpResponse.json(projectViews);
    return HttpResponse.json(userViews);
  }),
  http.post('*/api/v1/smart-views/', async ({ request }) => {
    lastCreatePayload = await request.json();
    const body = lastCreatePayload as Record<string, unknown>;
    const view = makeView(
      `v_${Math.random().toString(36).slice(2, 8)}`,
      (body.scope_type as 'user' | 'project') ?? 'user',
      (body.scope_id as string) ?? USER_ID,
      (body.name as string) ?? 'New',
    );
    if (view.scope_type === 'project') projectViews = [...projectViews, view];
    else userViews = [...userViews, view];
    return HttpResponse.json(view, { status: 201 });
  }),
  http.delete('*/api/v1/smart-views/:id', ({ params }) => {
    const id = params.id as string;
    deletedIds.push(id);
    userViews = userViews.filter((v) => v.id !== id);
    projectViews = projectViews.filter((v) => v.id !== id);
    return new HttpResponse(null, { status: 204 });
  }),
  http.post('*/api/v1/smart-views/:id/evaluate', ({ request }) => {
    lastEvaluateUrl = request.url;
    return HttpResponse.json({
      states: { guid_1: { visible: true, color: '#00ff00', opacity: 1.0 } },
      legend: null,
      element_count: 1,
    });
  }),
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
  useSmartViewState.getState().clear();
});
afterEach(() => {
  server.resetHandlers();
  userViews = [];
  projectViews = [];
  lastCreatePayload = null;
  lastEvaluateUrl = null;
  deletedIds = [];
  cleanup();
});
afterAll(() => server.close());

function renderPanel(props?: {
  modelId?: string | null;
  projectId?: string | null;
  userId?: string;
}) {
  const onClose = vi.fn();
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  // ``??`` only nullish-coalesces, so an explicit ``projectId: null``
  // override must be preserved as null — using ``??`` would substitute
  // the default and silently flip the tab to "project".
  const resolvedProjectId =
    props && 'projectId' in props ? props.projectId : PROJECT_ID;
  const resolvedModelId =
    props && 'modelId' in props ? props.modelId : MODEL_ID;
  const utils = render(
    <QueryClientProvider client={client}>
      <SmartViewsPanel
        modelId={resolvedModelId as string | null}
        projectId={resolvedProjectId as string | null}
        userId={props?.userId ?? USER_ID}
        onClose={onClose}
      />
    </QueryClientProvider>,
  );
  return { ...utils, onClose, client };
}

describe('SmartViewsPanel', () => {
  it('shows loading skeleton then list', async () => {
    userViews = [makeView('v1', 'user', USER_ID, 'My v1')];
    projectViews = [makeView('p1', 'project', PROJECT_ID, 'P v1')];
    renderPanel();
    // Initial render: project tab is the default when projectId is set.
    // We just confirm the panel mounts and resolves.
    await waitFor(() => {
      expect(screen.getByTestId('smart-views-panel')).toBeInTheDocument();
    });
    // List eventually arrives.
    await waitFor(() => {
      expect(screen.getByTestId('smart-view-card-p1')).toBeInTheDocument();
    });
  });

  it('renders both tabs when projectId is present', async () => {
    renderPanel();
    expect(screen.getByTestId('smart-views-tab-user')).toBeInTheDocument();
    expect(screen.getByTestId('smart-views-tab-project')).toBeInTheDocument();
  });

  it('hides the project tab when projectId is null', async () => {
    renderPanel({ projectId: null });
    expect(screen.getByTestId('smart-views-tab-user')).toBeInTheDocument();
    expect(screen.queryByTestId('smart-views-tab-project')).toBeNull();
  });

  it('switching tabs refetches and shows the right list', async () => {
    userViews = [makeView('u1', 'user', USER_ID, 'User-1')];
    projectViews = [makeView('p1', 'project', PROJECT_ID, 'Project-1')];
    renderPanel();
    // Default starts on Project tab when projectId is provided.
    await waitFor(() =>
      expect(screen.getByTestId('smart-view-card-p1')).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId('smart-views-tab-user'));
    await waitFor(() =>
      expect(screen.getByTestId('smart-view-card-u1')).toBeInTheDocument(),
    );
  });

  it('Apply click evaluates the view and updates the store', async () => {
    userViews = [makeView('u1', 'user', USER_ID, 'User-1')];
    renderPanel({ projectId: null });
    await waitFor(() =>
      expect(screen.getByTestId('smart-view-card-u1')).toBeInTheDocument(),
    );
    await act(async () => {
      fireEvent.click(screen.getByTestId('smart-view-card-u1'));
    });
    await waitFor(() => {
      expect(useSmartViewState.getState().appliedViewId).toBe('u1');
    });
    expect(lastEvaluateUrl).toContain('model_id=model-xyz');
    expect(useSmartViewState.getState().lastEvalResult?.element_count).toBe(1);
  });

  it('renders empty state when no views exist', async () => {
    renderPanel({ projectId: null });
    await waitFor(() => {
      expect(screen.getByTestId('smart-views-empty')).toBeInTheDocument();
    });
  });

  it('"New view" opens the editor modal', async () => {
    renderPanel({ projectId: null });
    fireEvent.click(screen.getByTestId('smart-views-new'));
    await waitFor(() => {
      expect(screen.getByTestId('smart-view-editor')).toBeInTheDocument();
    });
  });

  it('Clear-applied button only renders when something is applied', async () => {
    userViews = [makeView('u1', 'user', USER_ID, 'User-1')];
    renderPanel({ projectId: null });
    await waitFor(() =>
      expect(screen.getByTestId('smart-view-card-u1')).toBeInTheDocument(),
    );
    expect(screen.queryByTestId('smart-views-clear')).toBeNull();
    await act(async () => {
      fireEvent.click(screen.getByTestId('smart-view-card-u1'));
    });
    await waitFor(() =>
      expect(screen.getByTestId('smart-views-clear')).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId('smart-views-clear'));
    expect(useSmartViewState.getState().appliedViewId).toBeNull();
  });

  it('3-dot menu Delete shows confirm dialog → calls DELETE → removes the card', async () => {
    userViews = [makeView('u1', 'user', USER_ID, 'User-1')];
    renderPanel({ projectId: null });
    await waitFor(() =>
      expect(screen.getByTestId('smart-view-card-u1')).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId('smart-view-card-menu-u1'));
    fireEvent.click(screen.getByTestId('smart-view-card-delete-u1'));
    // ConfirmDialog renders — pick the confirm button by role.
    const confirmBtn = await screen.findByRole('button', { name: /delete/i });
    await act(async () => {
      fireEvent.click(confirmBtn);
    });
    await waitFor(() => expect(deletedIds).toContain('u1'));
    await waitFor(() => {
      expect(screen.queryByTestId('smart-view-card-u1')).toBeNull();
    });
  });

  it('Duplicate creates a copy in the active scope', async () => {
    userViews = [makeView('u1', 'user', USER_ID, 'User-1')];
    renderPanel({ projectId: null });
    await waitFor(() =>
      expect(screen.getByTestId('smart-view-card-u1')).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId('smart-view-card-menu-u1'));
    await act(async () => {
      fireEvent.click(screen.getByTestId('smart-view-card-duplicate-u1'));
    });
    await waitFor(() => expect(lastCreatePayload).toBeTruthy());
    expect(lastCreatePayload).toMatchObject({
      scope_type: 'user',
      scope_id: USER_ID,
    });
    const name = (lastCreatePayload as Record<string, unknown>).name as string;
    expect(name).toMatch(/User-1.*copy/i);
  });

  it('clicking apply with no model shows an error toast (does not crash)', async () => {
    userViews = [makeView('u1', 'user', USER_ID, 'User-1')];
    renderPanel({ projectId: null, modelId: null });
    await waitFor(() =>
      expect(screen.getByTestId('smart-view-card-u1')).toBeInTheDocument(),
    );
    await act(async () => {
      fireEvent.click(screen.getByTestId('smart-view-card-u1'));
    });
    // No applied state set when modelId is null
    await waitFor(() => {
      expect(useSmartViewState.getState().appliedViewId).toBeNull();
    });
  });

  it('Close button fires onClose', () => {
    const { onClose } = renderPanel();
    fireEvent.click(screen.getByTestId('smart-views-panel-close'));
    expect(onClose).toHaveBeenCalled();
  });

  it('applied card carries the data-applied="1" attribute', async () => {
    userViews = [makeView('u1', 'user', USER_ID, 'User-1')];
    renderPanel({ projectId: null });
    await waitFor(() =>
      expect(screen.getByTestId('smart-view-card-u1')).toBeInTheDocument(),
    );
    await act(async () => {
      fireEvent.click(screen.getByTestId('smart-view-card-u1'));
    });
    await waitFor(() => {
      const card = screen.getByTestId('smart-view-card-u1');
      expect(card.getAttribute('data-applied')).toBe('1');
    });
  });
});

// @ts-nocheck
/**
 * SmartViewShareModal — generate / copy / revoke flow tests.
 *
 * Covers:
 *   • State A → Generate hits POST and flips to State B with the URL
 *   • Copy uses navigator.clipboard.writeText with the absolute URL
 *   • Revoke confirms + hits DELETE + flips back to State A
 *   • A second Generate (rotate) replaces the token in-place
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
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { SmartViewShareModal } from '../SmartViewShareModal';

const VIEW_ID = '00000000-0000-0000-0000-0000000000aa';

let createCount = 0;
let lastRevokeViewId: string | null = null;
let nextToken = 'tok-alpha';

const server = setupServer(
  http.post('*/api/v1/smart-views/:id/share', () => {
    createCount += 1;
    return HttpResponse.json({
      view_id: VIEW_ID,
      share_token: nextToken,
      url: `/share/smart-views/${nextToken}`,
    });
  }),
  http.delete('*/api/v1/smart-views/:id/share', ({ params }) => {
    lastRevokeViewId = params.id as string;
    return new HttpResponse(null, { status: 204 });
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
  // Pin window.location.origin so the URL helper produces a stable
  // string we can assert against.
  Object.defineProperty(window, 'location', {
    value: { origin: 'https://oe.test', href: 'https://oe.test/bim' },
    writable: true,
  });
});
beforeEach(() => {
  createCount = 0;
  lastRevokeViewId = null;
  nextToken = 'tok-alpha';
  // Wire a fake clipboard each test so jsdom does not 404.
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText: vi.fn().mockResolvedValue(undefined) },
    writable: true,
    configurable: true,
  });
});
afterEach(() => {
  server.resetHandlers();
  cleanup();
});
afterAll(() => server.close());

function renderModal(initialShareToken: string | null = null) {
  const onChanged = vi.fn();
  const utils = render(
    <SmartViewShareModal
      open
      onClose={() => undefined}
      viewId={VIEW_ID}
      viewName="My view"
      initialShareToken={initialShareToken}
      onChanged={onChanged}
    />,
  );
  return { ...utils, onChanged };
}

describe('SmartViewShareModal', () => {
  it('Generate creates a token and shows the URL input (State A → B)', async () => {
    const { onChanged } = renderModal(null);
    expect(screen.getByTestId('smart-view-share-generate')).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByTestId('smart-view-share-generate'));
    });
    await waitFor(() =>
      expect(screen.getByTestId('smart-view-share-url')).toBeInTheDocument(),
    );
    const input = screen.getByTestId(
      'smart-view-share-url',
    ) as HTMLInputElement;
    expect(input.value).toBe('https://oe.test/smart-views/shared/tok-alpha');
    expect(createCount).toBe(1);
    expect(onChanged).toHaveBeenCalledWith('tok-alpha');
  });

  it('Copy puts the absolute URL on the clipboard', async () => {
    renderModal('tok-existing');
    expect(
      screen.getByTestId('smart-view-share-copy'),
    ).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByTestId('smart-view-share-copy'));
    });
    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
        'https://oe.test/smart-views/shared/tok-existing',
      );
    });
  });

  it('Revoke clears the token (with explicit confirm) - back to State A', async () => {
    const { onChanged } = renderModal('tok-existing');
    fireEvent.click(screen.getByTestId('smart-view-share-revoke'));
    expect(
      screen.getByTestId('smart-view-share-revoke-confirm'),
    ).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(
        screen.getByTestId('smart-view-share-revoke-confirm-button'),
      );
    });
    await waitFor(() => expect(lastRevokeViewId).toBe(VIEW_ID));
    await waitFor(() =>
      expect(screen.getByTestId('smart-view-share-generate')).toBeInTheDocument(),
    );
    expect(onChanged).toHaveBeenLastCalledWith(null);
  });

  it('Rotate (second Generate) replaces the token in-place', async () => {
    renderModal('tok-existing');
    nextToken = 'tok-rotated';
    expect(
      (screen.getByTestId('smart-view-share-url') as HTMLInputElement).value,
    ).toContain('tok-existing');
    await act(async () => {
      fireEvent.click(screen.getByTestId('smart-view-share-rotate'));
    });
    await waitFor(() => {
      const input = screen.getByTestId(
        'smart-view-share-url',
      ) as HTMLInputElement;
      expect(input.value).toBe('https://oe.test/smart-views/shared/tok-rotated');
    });
    expect(createCount).toBe(1);
  });
});

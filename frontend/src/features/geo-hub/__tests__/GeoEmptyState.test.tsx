// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
/**
 * GeoEmptyState tests - focused on the #284 manual-anchor fix.
 *
 * Reporter (Tigercatman): the no-anchor "Set anchor manually" action
 * redirected to the project page instead of letting them place a pin on the
 * map. The fix: when the page passes ``onPlaceManually``, the manual CTA is
 * an in-map placement button (NOT a navigate-away link).
 *
 * Coverage:
 *   1. no_anchor + onPlaceManually → renders a "Place a pin on the map"
 *      button that fires the callback and does NOT navigate.
 *   2. no_anchor WITHOUT onPlaceManually → keeps the legacy settings link
 *      (the documented fallback), so older callers still work.
 *   3. The auto-anchor button is unaffected and still calls the geocoder.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Capture the navigate spy so we can assert the manual CTA does NOT route.
// ``src/test/setup.ts`` already stubs react-router-dom; we re-stub here only
// to expose a stable spy (and keep MemoryRouter for <Link>).
const navigateSpy = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual =
    await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => navigateSpy,
    useParams: () => ({}),
    useSearchParams: () => [new URLSearchParams(), vi.fn()],
  };
});

// Mock the geo api so the auto-anchor button never hits a real endpoint.
vi.mock('../api', () => ({
  autoAnchorFromAddress: vi.fn(async () => ({
    anchor: { id: 'a1' },
    precision: 'address',
    source: 'nominatim',
    display_name: 'Somewhere',
  })),
}));

import { autoAnchorFromAddress } from '../api';
import { GeoEmptyState } from '../GeoEmptyState';

const PROJECT = '11111111-2222-3333-4444-555555555555';

function renderEmpty(ui: React.ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('GeoEmptyState - manual anchoring (#284)', () => {
  it('no_anchor with onPlaceManually fires the callback and does not navigate', async () => {
    const onPlaceManually = vi.fn();
    renderEmpty(
      <GeoEmptyState
        kind="no_anchor"
        projectId={PROJECT}
        onPlaceManually={onPlaceManually}
      />,
    );

    const btn = screen.getByTestId('geo-empty-place-manually');
    await userEvent.click(btn);

    expect(onPlaceManually).toHaveBeenCalledTimes(1);
    // The bug was a redirect to the project page - assert we never route.
    expect(navigateSpy).not.toHaveBeenCalled();
    // And no settings link is rendered in the in-map flow.
    expect(
      screen.queryByRole('link', { name: /set anchor manually/i }),
    ).toBeNull();
  });

  it('no_anchor without onPlaceManually keeps the legacy settings link', () => {
    renderEmpty(<GeoEmptyState kind="no_anchor" projectId={PROJECT} />);

    // No in-map placement button.
    expect(screen.queryByTestId('geo-empty-place-manually')).toBeNull();
    // Fallback link points at project settings (the legacy manual path).
    const link = screen.getByRole('link', { name: /set anchor manually/i });
    expect(link).toHaveAttribute('href', `/projects/${PROJECT}/settings`);
  });

  it('auto-anchor button still geocodes from the project address', async () => {
    renderEmpty(
      <GeoEmptyState
        kind="no_anchor"
        projectId={PROJECT}
        onPlaceManually={vi.fn()}
      />,
    );

    await userEvent.click(screen.getByTestId('geo-empty-auto-anchor'));

    await waitFor(() =>
      expect(autoAnchorFromAddress).toHaveBeenCalledWith(PROJECT),
    );
  });
});

describe('GeoEmptyState - dismiss to a pill (#284 masked-map fix)', () => {
  it('no_anchor card can be tucked away to a corner pill and brought back', async () => {
    renderEmpty(<GeoEmptyState kind="no_anchor" projectId={PROJECT} />);

    // The full card is shown with a dismiss control.
    const dismiss = screen.getByTestId('geo-empty-dismiss');
    expect(dismiss).toBeInTheDocument();

    await userEvent.click(dismiss);

    // Card gone, pill shown (the map is no longer masked).
    expect(screen.queryByTestId('geo-empty-auto-anchor')).toBeNull();
    const pill = screen.getByTestId('geo-empty-pill');
    expect(pill).toBeInTheDocument();

    // Restoring brings the full prompt back.
    await userEvent.click(pill);
    expect(screen.getByTestId('geo-empty-dismiss')).toBeInTheDocument();
    expect(screen.queryByTestId('geo-empty-pill')).toBeNull();
  });

  it('non-anchor states are NOT dismissible (always show their card)', () => {
    renderEmpty(<GeoEmptyState kind="no_tilesets" projectId={PROJECT} />);
    // no_tilesets must keep its guidance card - no dismiss affordance.
    expect(screen.queryByTestId('geo-empty-dismiss')).toBeNull();
    expect(screen.queryByTestId('geo-empty-pill')).toBeNull();
  });
});

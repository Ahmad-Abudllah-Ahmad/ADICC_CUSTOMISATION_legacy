// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// P0-2 — When no catalogues are installed, the wizard MUST render a
// clear "Install a catalogue first" banner with an actionable CTA, and
// the Step 2 → Step 3 gate (``catalogueId !== null``) MUST stay blocked
// until the user actually installs one.
//
// Symptom before the fix: ``installed.length === 0`` meant the
// auto-select effect never fired → ``selected`` stayed null → Next
// stayed disabled but the user had no obvious recovery path other than
// a buried hint pointing at "the floating dock" that doesn't render
// until the first install kicks off. The new banner surfaces the dead-
// end + scrolls to the install list.

import { useState } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  render,
  screen,
  cleanup,
  waitFor,
} from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// auth store mock — CatalogueStep reads the access token to attach to
// the catalogues-v3 fetch. We don't need a real token, just a no-op.
vi.mock('@/stores/useAuthStore', () => ({
  useAuthStore: {
    getState: () => ({ accessToken: null }),
  },
}));

// Toast store noop — install button click paths trigger toasts. The
// wizard reads via the zero-arg ``useToastStore()`` shape *and* the
// selector form ``useToastStore(s => s.addToast)``, so support both.
vi.mock('@/stores/useToastStore', () => {
  const state = { addToast: () => {} };
  const hook = (selector?: (s: typeof state) => unknown) =>
    typeof selector === 'function' ? selector(state) : state;
  return { useToastStore: hook };
});

// Catalogue install store — minimal stub: empty job map + a noop
// startInstall. The banner contract doesn't depend on actually starting
// an install; we're verifying the gate + the CTA presence.
vi.mock('@/stores/useCatalogueInstallStore', () => {
  const state = {
    jobs: new Map<string, unknown>(),
    startInstall: () => {},
  };
  const hook = (selector?: (s: typeof state) => unknown) =>
    typeof selector === 'function' ? selector(state) : state;
  return { useCatalogueInstallStore: hook };
});

import { CatalogueStep } from '../MatchWizard';

function renderStep(opts: {
  catalogues: Array<{
    region: string;
    install_status: 'loaded' | 'available' | 'installing' | 'coming_soon';
    country_iso?: string;
    city?: string;
    language?: string;
    currency?: string;
    size_mb?: number;
  }>;
  onPick?: (region: string | null) => void;
}) {
  // Spy on fetch so the useQuery call returns our fixture payload.
  const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(
    async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/catalogues-v3')) {
        return new Response(JSON.stringify(opts.catalogues), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      return new Response('{}', { status: 404 });
    },
  );

  const onPick = opts.onPick ?? (() => {});
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  // Drive the wizard's "canNext" gate in isolation: a tiny wrapper that
  // mirrors MatchWizard.canNext for step 2 (``catalogueId !== null``).
  // We assert against this wrapper's data-blocked attribute below.
  function Wrapper() {
    const [selected, setSelected] = useState<string | null>(null);
    const blocked = selected === null;
    return (
      <div data-testid="gate-mirror" data-blocked={blocked ? 'true' : 'false'}>
        <CatalogueStep
          projectRegion="DE-BW"
          selected={selected}
          onPick={(region) => {
            setSelected(region);
            onPick(region);
          }}
        />
      </div>
    );
  }

  const result = render(
    <QueryClientProvider client={client}>
      <Wrapper />
    </QueryClientProvider>,
  );
  return { ...result, fetchSpy };
}

beforeEach(() => {
  // jest-dom matchers + vi.spyOn restore
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('CatalogueStep - P0-2 no-catalogue gate regression', () => {
  it('renders the "Install a catalogue first" banner when installed list is empty', async () => {
    renderStep({
      catalogues: [
        {
          region: 'DE-Stuttgart',
          install_status: 'available',
          country_iso: 'DE',
          city: 'Stuttgart',
          language: 'de',
          currency: 'EUR',
          size_mb: 220,
        },
      ],
    });

    // Banner has a stable test id so the contract doesn't depend on
    // exact copy — locales can drift, the gate cannot.
    const banner = await screen.findByTestId('no-catalogue-banner');
    expect(banner).toBeTruthy();

    // The CTA button MUST be present + enabled (available > 0).
    const cta = screen.getByTestId('no-catalogue-install-cta');
    expect(cta).toBeTruthy();
    expect((cta as HTMLButtonElement).disabled).toBe(false);
  });

  it('keeps the Step 2 → 3 gate BLOCKED until at least one catalogue is installed', async () => {
    renderStep({
      catalogues: [
        // Only "available" rows — nothing loaded yet.
        { region: 'DE-Stuttgart', install_status: 'available', country_iso: 'DE', city: 'Stuttgart', language: 'de', currency: 'EUR', size_mb: 220 },
        { region: 'GB-London', install_status: 'available', country_iso: 'GB', city: 'London', language: 'en', currency: 'GBP', size_mb: 180 },
      ],
    });

    // Banner appears (proves the empty-installed branch ran).
    await screen.findByTestId('no-catalogue-banner');

    // The gate mirror reflects the wizard's ``catalogueId === null``
    // check. With no installed catalogues + no auto-select fired, the
    // gate MUST stay blocked. Wait one tick so the auto-select effect
    // has a chance to fire (it must NOT — that's the regression).
    await waitFor(() => {
      const mirror = screen.getByTestId('gate-mirror');
      expect(mirror.getAttribute('data-blocked')).toBe('true');
    });
  });

  it('unblocks the gate once a catalogue flips to install_status=loaded', async () => {
    // Positive-path counterpart: when at least one catalogue is loaded,
    // the auto-select effect picks it and the gate opens. This is the
    // contract the bug fix must preserve.
    renderStep({
      catalogues: [
        {
          region: 'DE-Berlin',
          install_status: 'loaded',
          country_iso: 'DE',
          city: 'Berlin',
          language: 'de',
          currency: 'EUR',
          size_mb: 250,
        },
      ],
    });

    // The banner MUST NOT render when at least one is installed.
    await waitFor(() => {
      expect(screen.queryByTestId('no-catalogue-banner')).toBeNull();
    });

    // Auto-select fires → gate opens.
    await waitFor(() => {
      const mirror = screen.getByTestId('gate-mirror');
      expect(mirror.getAttribute('data-blocked')).toBe('false');
    });
  });
});

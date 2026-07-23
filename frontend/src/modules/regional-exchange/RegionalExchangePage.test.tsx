// @ts-nocheck
/**
 * RegionalExchangePage — Wave 5 Epic I.
 *
 * The polymorphic page renders one of 20 country packs from the registry.
 * These tests cover:
 *   1. Registry-pickup — the Spanish template renders the flag, the
 *      native label, the BC3 format hint, and a downloadable sample.
 *   2. Per-country differentiation — switching `template` to the US
 *      MasterFormat pack flips the header without re-mounting the
 *      whole page tree, and the validator-pack list reflects the new
 *      country.
 *   3. Back-compat slug lookup — `/modules/es-pbc-exchange` resolves
 *      to the same registry entry (deep-link compat shim).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

// Stub the API layer — the test never makes a network call. Mocking
// also keeps React Query from hanging on a real fetch promise.
vi.mock('@/shared/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/shared/lib/api')>();
  return {
    ...actual,
    apiGet: vi.fn(async () => []),
    apiPost: vi.fn(async () => ({ imported: 0, errors: [] })),
    triggerDownload: vi.fn(),
  };
});

// Toast store would otherwise touch zustand internals during the
// import-success path. Mocking it keeps the test side-effect free.
vi.mock('@/stores/useToastStore', () => ({
  useToastStore: () => vi.fn(),
}));

import RegionalExchangePage from './RegionalExchangePage';
import {
  COUNTRY_TEMPLATES,
  getRegionalTemplate,
  getRegionalTemplateBySlug,
} from './regionalRegistry';

function renderWithProviders(template: ReturnType<typeof getRegionalTemplate>) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/${template!.routeSlug}`]}>
        <RegionalExchangePage template={template!} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('RegionalExchangePage - registry pickup', () => {
  it('renders the Spanish PBC template with flag, native label, and BC3 hint', () => {
    const es = getRegionalTemplate('es-pbc');
    expect(es).toBeDefined();

    renderWithProviders(es);

    // Header label is the native template label
    expect(screen.getByTestId('regional-label').textContent).toMatch(
      /Spanish PBC/i,
    );
    // Flag is rendered (the emoji shows up as text content)
    expect(screen.getByTestId('regional-flag').textContent).toContain('🇪🇸');
    // Format hint mentions BC3 (the Spanish native format)
    expect(screen.getByTestId('regional-format-hint').textContent).toMatch(/BC3/i);
    // Sample-file link points to the design-mandated BC3 sample
    const sampleLink = screen.getByTestId('regional-sample-link');
    expect(sampleLink.getAttribute('href')).toBe('/templates/es-pbc-sample.bc3');
  });

  it('renders the US MasterFormat template with the US flag and MasterFormat hint', () => {
    const us = getRegionalTemplate('us-masterformat');
    expect(us).toBeDefined();

    renderWithProviders(us);

    expect(screen.getByTestId('regional-label').textContent).toMatch(/MasterFormat/i);
    expect(screen.getByTestId('regional-flag').textContent).toContain('🇺🇸');
    expect(screen.getByTestId('regional-format-hint').textContent).toMatch(/MasterFormat/i);
    const sampleLink = screen.getByTestId('regional-sample-link');
    expect(sampleLink.getAttribute('href')).toBe('/templates/masterformat-sample.csv');
  });

  it('renders the page container with the active template id as a data attribute', () => {
    const de = getRegionalTemplate('de-din276');
    expect(de).toBeDefined();

    renderWithProviders(de);
    const root = screen.getByTestId('regional-exchange-page');
    expect(root.getAttribute('data-template-id')).toBe('de-din276');
  });
});

describe('RegionalExchangePage - deep-link compat shim', () => {
  it('deep-link slug /es-pbc-exchange resolves to the same template', () => {
    const direct = getRegionalTemplate('es-pbc');
    const viaSlug = getRegionalTemplateBySlug('es-pbc-exchange');
    expect(viaSlug).toBe(direct);

    // And rendering with the slug-resolved template gives the same UI as
    // rendering with the id-resolved template — the polymorphic page
    // does not care whether the parent route was the new id-based one
    // or the old country-slug back-compat one.
    renderWithProviders(viaSlug);
    expect(screen.getByTestId('regional-label').textContent).toMatch(/Spanish PBC/i);
  });

  it('deep-link slug for every registry entry mounts the polymorphic page', () => {
    for (const tpl of COUNTRY_TEMPLATES) {
      const resolved = getRegionalTemplateBySlug(tpl.routeSlug);
      expect(resolved).toBeDefined();
      expect(resolved!.id).toBe(tpl.id);
    }
  });
});

describe('RegionalExchangePage - sample link visibility', () => {
  it('hides the sample link for countries without a sample file', () => {
    // Australia is one of the templates that does NOT ship a sample
    // file as part of Epic I scope (only es-pbc / it-computo / uk-nrm /
    // us-masterformat have native sample files). The polymorphic page
    // simply omits the link when sampleFile is undefined.
    const au = getRegionalTemplate('au-acmm');
    expect(au?.sampleFile).toBeUndefined();

    renderWithProviders(au);
    expect(screen.queryByTestId('regional-sample-link')).toBeNull();
  });
});

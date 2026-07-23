// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
// Tests for <RomEstimatePage>.
//
// Covers:
//   1. The reference table populates the building-type / quality / region
//      selectors.
//   2. Filling the area and submitting calls romEstimateApi.generate with the
//      chosen inputs, and the returned elemental breakdown renders (element
//      labels + total).

import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

/* ── i18n shim with interpolation (component reaches @/shared/ui -> app/i18n) ── */
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_key: string, opts?: { defaultValue?: string } & Record<string, unknown>) => {
      if (typeof opts === 'object' && opts && 'defaultValue' in opts) {
        let dv = opts.defaultValue ?? '';
        for (const [k, v] of Object.entries(opts)) {
          if (k === 'defaultValue') continue;
          dv = dv.replaceAll(`{{${k}}}`, String(v));
        }
        return dv;
      }
      return _key;
    },
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
  Trans: ({ children }: { children: React.ReactNode }) => children,
  initReactI18next: { type: '3rdParty', init: () => {} },
  I18nextProvider: ({ children }: { children: React.ReactNode }) => children,
}));

/* ── API mock ──────────────────────────────────────────────────────────────── */
const apiMocks = vi.hoisted(() => ({
  referenceMock: vi.fn(),
  generateMock: vi.fn(),
  reconciliationMock: vi.fn(),
  createMock: vi.fn(),
  listMock: vi.fn(),
  deleteMock: vi.fn(),
  createBoqMock: vi.fn(),
}));
const { referenceMock, generateMock } = apiMocks;
vi.mock('./api', () => ({
  romEstimateApi: {
    reference: apiMocks.referenceMock,
    generate: apiMocks.generateMock,
    reconciliation: apiMocks.reconciliationMock,
    create: apiMocks.createMock,
    list: apiMocks.listMock,
    delete: apiMocks.deleteMock,
    createBoq: apiMocks.createBoqMock,
  },
}));

// No active project in these tests, so the reconciliation panel stays hidden and
// this suite exercises only the calculator.
vi.mock('@/shared/hooks/useActiveProjectId', () => ({ useActiveProjectId: () => '' }));

import { RomEstimatePage } from './RomEstimatePage';

const REFERENCE = {
  building_types: [
    { key: 'office', label: 'Office building', base_rate_per_m2: '2000', accuracy_low_pct: '-25', accuracy_high_pct: '35' },
    { key: 'warehouse', label: 'Warehouse / logistics', base_rate_per_m2: '700', accuracy_low_pct: '-18', accuracy_high_pct: '28' },
  ],
  quality_levels: [
    { key: 'standard', label: 'Standard', factor: '1.00' },
    { key: 'premium', label: 'Premium', factor: '1.28' },
  ],
  regions: [
    { key: 'global', label: 'Global (worldwide default)', factor: '1.00' },
    { key: 'north_america', label: 'North America', factor: '1.10' },
  ],
  elements: [
    { key: 'substructure', label: 'Substructure' },
    { key: 'services', label: 'Building services (MEP)' },
  ],
  default_quality: 'standard',
  default_region: 'global',
  reference_basis_note: 'Indicative rates.',
};

const RESULT = {
  building_type: 'office',
  building_type_label: 'Office building',
  quality: 'standard',
  quality_label: 'Standard',
  region: 'global',
  region_label: 'Global (worldwide default)',
  currency: 'EUR',
  gross_floor_area: '1000',
  gfa_unit: 'm2',
  gfa_canonical_m2: '1000',
  quality_factor: '1.00',
  regional_factor: '1.00',
  cost_per_m2: '2000.00',
  subtotal_base: '2000000.00',
  total: '2000000.00',
  accuracy: {
    estimate_class: 'order_of_magnitude',
    estimate_class_label: 'Order-of-magnitude (concept)',
    low_pct: '-33',
    high_pct: '47',
    low_amount: '1340000.00',
    high_amount: '2940000.00',
    localized: false,
    note: 'Widened, no region.',
  },
  elements: [
    { key: 'substructure', label: 'Substructure', cost_share_pct: '8.00', rate_per_m2: '160.00', amount: '160000.00' },
    { key: 'services', label: 'Building services (MEP)', cost_share_pct: '30.00', rate_per_m2: '600.00', amount: '600000.00' },
  ],
  notes: 'Order-of-magnitude estimate.',
};

afterEach(() => {
  cleanup();
  referenceMock.mockReset();
  generateMock.mockReset();
});

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <RomEstimatePage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe('<RomEstimatePage>', () => {
  it('populates the building-type selector from the reference table', async () => {
    referenceMock.mockResolvedValueOnce(REFERENCE);
    generateMock.mockResolvedValue(RESULT);
    renderPage();

    expect(await screen.findByRole('option', { name: 'Office building' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Warehouse / logistics' })).toBeInTheDocument();
  });

  it('generates an estimate and renders the elemental breakdown', async () => {
    referenceMock.mockResolvedValueOnce(REFERENCE);
    generateMock.mockResolvedValueOnce(RESULT);
    renderPage();

    // Wait for the reference to seed the selectors (default building type = office).
    await screen.findByRole('option', { name: 'Office building' });

    fireEvent.change(screen.getByLabelText(/Gross floor area/i), { target: { value: '1000' } });
    fireEvent.click(screen.getByRole('button', { name: /Generate estimate/i }));

    await waitFor(() => expect(generateMock).toHaveBeenCalledTimes(1));

    const body = generateMock.mock.calls[0]?.[0] as Record<string, unknown>;
    expect(body.building_type).toBe('office');
    expect(body.gross_floor_area).toBe('1000');
    expect(body.quality).toBe('standard');
    expect(body.region).toBe('global');

    // The breakdown renders the element labels returned by the backend.
    expect(await screen.findByText('Building services (MEP)')).toBeInTheDocument();
    expect(screen.getByText('Substructure')).toBeInTheDocument();
    // The unlocalized-band warning shows because region was left at the default.
    expect(
      screen.getByText(/No regional cost factor applied/i),
    ).toBeInTheDocument();
  });

  it('keeps the Generate button disabled until a positive area is entered', async () => {
    referenceMock.mockResolvedValueOnce(REFERENCE);
    generateMock.mockResolvedValue(RESULT);
    renderPage();
    await screen.findByRole('option', { name: 'Office building' });

    const button = screen.getByRole('button', { name: /Generate estimate/i });
    expect(button).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/Gross floor area/i), { target: { value: '1500' } });
    expect(button).not.toBeDisabled();
  });

  it('re-runs the estimate with the base cost/m² override when set on the result view', async () => {
    referenceMock.mockResolvedValueOnce(REFERENCE);
    generateMock.mockResolvedValue(RESULT);
    renderPage();
    await screen.findByRole('option', { name: 'Office building' });

    fireEvent.change(screen.getByLabelText(/Gross floor area/i), { target: { value: '1000' } });
    fireEvent.click(screen.getByRole('button', { name: /Generate estimate/i }));
    await waitFor(() => expect(generateMock).toHaveBeenCalledTimes(1));
    // The first run carries no override.
    const first = generateMock.mock.calls[0]?.[0] as Record<string, unknown>;
    expect(first.base_rate_per_m2_override).toBeUndefined();

    // Set a real base rate on the result view and re-run.
    fireEvent.change(await screen.findByLabelText(/base cost/i), { target: { value: '2500' } });
    fireEvent.click(screen.getByRole('button', { name: /Update estimate/i }));
    await waitFor(() => expect(generateMock).toHaveBeenCalledTimes(2));

    // Money override is passed through verbatim as a string (never float-mathed).
    const second = generateMock.mock.calls[1]?.[0] as Record<string, unknown>;
    expect(second.base_rate_per_m2_override).toBe('2500');
  });
});

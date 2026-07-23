// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// NoMatchModal tests — pins the "Create custom position" flow that used to
// be a backend stub. The modal must:
//   * default to the TBD action,
//   * reveal the custom description / unit / rate fields + the new
//     "save to my catalogue" checkbox only when Custom is selected,
//   * POST the custom spec (incl. save_to_my_catalogue) to noMatch so the
//     backend can write a real BOQ line and (optionally) a reusable rate.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// i18n: return the defaultValue so assertions match the English copy.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string | { defaultValue?: string }) => {
      if (typeof fallback === 'string') return fallback;
      if (fallback && typeof fallback === 'object' && fallback.defaultValue)
        return fallback.defaultValue;
      return key;
    },
  }),
}));

vi.mock('../api', () => ({
  matchElementsApi: {
    noMatch: vi.fn(),
  },
}));

import { matchElementsApi } from '../api';
import { NoMatchModal } from '../NoMatchModal';

const noMatchSpy = matchElementsApi.noMatch as ReturnType<typeof vi.fn>;

function renderModal(onDone = vi.fn(), onClose = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <NoMatchModal
        sessionId="sess-1"
        groupKey="ifc_class:IfcWall|material:Earth"
        onClose={onClose}
        onDone={onDone}
      />
    </QueryClientProvider>,
  );
  return { onDone, onClose };
}

beforeEach(() => {
  noMatchSpy.mockReset();
  noMatchSpy.mockResolvedValue({ status: 'confirmed' });
});
afterEach(() => cleanup());

describe('NoMatchModal', () => {
  it('hides custom fields until Custom is selected', () => {
    renderModal();
    // Description input is part of the custom panel and is absent by default.
    expect(screen.queryByPlaceholderText('Position description')).toBeNull();
    fireEvent.click(screen.getByText('Create custom position'));
    expect(screen.getByPlaceholderText('Position description')).toBeTruthy();
    // The new reuse checkbox is part of the custom panel.
    expect(
      screen.getByText(/Save to my catalogue/i),
    ).toBeTruthy();
  });

  it('posts the custom spec with save_to_my_catalogue when checked', async () => {
    renderModal();
    fireEvent.click(screen.getByText('Create custom position'));

    fireEvent.change(screen.getByPlaceholderText('Position description'), {
      target: { value: 'Rammed earth wall' },
    });
    fireEvent.change(screen.getByPlaceholderText('Unit'), {
      target: { value: 'm3' },
    });
    fireEvent.change(screen.getByPlaceholderText('Unit rate'), {
      target: { value: '145.5' },
    });
    // Tick "save to my catalogue".
    fireEvent.click(screen.getByRole('checkbox'));

    fireEvent.click(screen.getByText('Apply'));

    await waitFor(() => expect(noMatchSpy).toHaveBeenCalledTimes(1));
    expect(noMatchSpy).toHaveBeenCalledWith('sess-1', {
      group_key: 'ifc_class:IfcWall|material:Earth',
      action: 'custom',
      custom_description: 'Rammed earth wall',
      custom_unit: 'm3',
      custom_rate: 145.5,
      save_to_my_catalogue: true,
    });
  });

  it('TBD action posts no custom payload', async () => {
    renderModal();
    // TBD is the default action; Apply immediately.
    fireEvent.click(screen.getByText('Apply'));
    await waitFor(() => expect(noMatchSpy).toHaveBeenCalledTimes(1));
    expect(noMatchSpy).toHaveBeenCalledWith('sess-1', {
      group_key: 'ifc_class:IfcWall|material:Earth',
      action: 'tbd',
    });
  });
});

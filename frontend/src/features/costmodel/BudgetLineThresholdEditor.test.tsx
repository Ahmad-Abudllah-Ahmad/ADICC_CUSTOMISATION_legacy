// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for <BudgetLineThresholdEditor> (Gap D cost-overrun alerts).
//
// Covers:
//   1. parseThreshold clamps to the [0, 50] UI range and defaults to 0.
//   2. Changing the slider and saving calls setOverrunAlertThreshold with the
//      clamped value and shows a success toast.
//   3. On success the ['costmodel'] query is invalidated so the page refetches.
//   4. The Save button is disabled until the value actually changes (no-op edits
//      do not hit the API).

import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

/* ── i18n shim with interpolation ─────────────────────────────────────────── */

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

/* ── Toast mock ───────────────────────────────────────────────────────────── */

const toastMocks = vi.hoisted(() => ({ addToastMock: vi.fn() }));
const addToastMock = toastMocks.addToastMock;
vi.mock('@/stores/useToastStore', () => ({
  useToastStore: Object.assign(
    (selector: (s: { addToast: typeof toastMocks.addToastMock }) => unknown) =>
      selector({ addToast: toastMocks.addToastMock }),
    { getState: () => ({ addToast: toastMocks.addToastMock }) },
  ),
}));

/* ── API mock ─────────────────────────────────────────────────────────────── */

const apiMocks = vi.hoisted(() => ({ setThresholdMock: vi.fn() }));
const setThresholdMock = apiMocks.setThresholdMock;
vi.mock('./api', () => ({
  costModelApi: { setOverrunAlertThreshold: apiMocks.setThresholdMock },
}));

import { BudgetLineThresholdEditor, parseThreshold } from './BudgetLineThresholdEditor';

afterEach(() => {
  cleanup();
  setThresholdMock.mockReset();
  addToastMock.mockReset();
});

function renderEditor(lineId = 'line-1', initial: string | null = '0') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const invalidateSpy = vi.spyOn(client, 'invalidateQueries');
  return {
    invalidateSpy,
    ...render(
      <QueryClientProvider client={client}>
        <BudgetLineThresholdEditor lineId={lineId} initialThresholdPct={initial} />
      </QueryClientProvider>,
    ),
  };
}

describe('parseThreshold', () => {
  it('defaults blank / null / unparseable values to 0', () => {
    expect(parseThreshold(undefined)).toBe(0);
    expect(parseThreshold(null)).toBe(0);
    expect(parseThreshold('')).toBe(0);
    expect(parseThreshold('not-a-number')).toBe(0);
  });

  it('clamps above 50 down to 50 and below 0 up to 0', () => {
    expect(parseThreshold('80')).toBe(50);
    expect(parseThreshold('-5')).toBe(0);
  });

  it('rounds and passes through in-range values', () => {
    expect(parseThreshold('10')).toBe(10);
    expect(parseThreshold('12.4')).toBe(12);
  });
});

describe('<BudgetLineThresholdEditor>', () => {
  it('saves the clamped slider value and shows a success toast', async () => {
    setThresholdMock.mockResolvedValueOnce({ id: 'line-1', overrun_alert_threshold_pct: '15' });
    renderEditor('line-1', '0');

    const slider = screen.getByRole('slider');
    fireEvent.change(slider, { target: { value: '15' } });
    fireEvent.click(screen.getByRole('button', { name: /Save/i }));

    await waitFor(() => expect(setThresholdMock).toHaveBeenCalledTimes(1));
    expect(setThresholdMock.mock.calls[0]).toEqual(['line-1', 15]);
    await waitFor(() => expect(addToastMock).toHaveBeenCalledTimes(1));
    expect((addToastMock.mock.calls[0]?.[0] as { type: string }).type).toBe('success');
  });

  it('invalidates the ["costmodel"] query on success', async () => {
    setThresholdMock.mockResolvedValueOnce({ id: 'line-9', overrun_alert_threshold_pct: '20' });
    const { invalidateSpy } = renderEditor('line-9', '0');

    fireEvent.change(screen.getByRole('slider'), { target: { value: '20' } });
    fireEvent.click(screen.getByRole('button', { name: /Save/i }));

    await waitFor(() =>
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['costmodel'] }),
    );
  });

  it('keeps Save disabled until the threshold actually changes', () => {
    renderEditor('line-2', '10');
    // Initial value equals the persisted value -> not dirty -> disabled.
    expect(screen.getByRole('button', { name: /Save/i })).toBeDisabled();
  });

  it('disabling (slider to 0) posts 0 to the API', async () => {
    setThresholdMock.mockResolvedValueOnce({ id: 'line-3', overrun_alert_threshold_pct: '0' });
    renderEditor('line-3', '10');

    fireEvent.change(screen.getByRole('slider'), { target: { value: '0' } });
    fireEvent.click(screen.getByRole('button', { name: /Save/i }));

    await waitFor(() => expect(setThresholdMock).toHaveBeenCalledTimes(1));
    expect(setThresholdMock.mock.calls[0]).toEqual(['line-3', 0]);
  });
});

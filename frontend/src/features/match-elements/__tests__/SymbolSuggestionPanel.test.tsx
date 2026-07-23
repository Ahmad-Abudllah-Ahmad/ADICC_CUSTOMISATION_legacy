// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Item #18 — SymbolSuggestionPanel tests.
//
// Pins the panel contract: renders the ranked suggestion list with
// confidence chips, surfaces the honesty note, expands per-suggestion
// factors on "Why?", calls the review-only apply callback (never
// auto-commits), and renders an explicit empty state.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  render,
  screen,
  cleanup,
  fireEvent,
} from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// i18n: return the defaultValue so assertions match the English copy.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_key: string, opts?: { defaultValue?: string } | string) =>
      typeof opts === 'object' && opts?.defaultValue ? opts.defaultValue : _key,
  }),
}));

// Stub the API so we control suggestSymbols call-by-call.
vi.mock('../api', () => ({
  matchElementsApi: {
    suggestSymbols: vi.fn(),
  },
}));

import { matchElementsApi, type SymbolSuggestResponse } from '../api';
import { SymbolSuggestionPanel } from '../SymbolSuggestionPanel';

const suggestSpy = matchElementsApi.suggestSymbols as ReturnType<typeof vi.fn>;

const RANKED: SymbolSuggestResponse = {
  signature: {
    category: 'door',
    ratios: { aspect: 2.33, slenderness: 2.33 },
    property_fingerprint: ['ifc_class=ifcdoor'],
    raw_dimensions: { height: 2.1, width: 0.9 },
  },
  suggestions: [
    {
      symbol: 'door',
      confidence: 1.0,
      confidence_band: 'high',
      rank: 0,
      factors: [
        {
          name: 'category',
          weight: 0.55,
          contribution: 1.0,
          detail: "category 'door' vs ['door', 'ifcdoor']",
        },
        {
          name: 'ratio:aspect',
          weight: 1.0,
          contribution: 1.0,
          detail: 'aspect=2.33 vs [1.6, 3.2] -> fit 1.00',
        },
      ],
    },
    {
      symbol: 'window',
      confidence: 0.42,
      confidence_band: 'medium',
      rank: 1,
      factors: [],
    },
    {
      symbol: 'beam',
      confidence: 0.1,
      confidence_band: 'low',
      rank: 2,
      factors: [],
    },
  ],
  note:
    'Deterministic shape-signature heuristic over structured geometry/properties. Raster computer-vision symbol detection is the separate cv-pipeline service (roadmap Phase 3).',
};

function renderPanel(props: Partial<Parameters<typeof SymbolSuggestionPanel>[0]> = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SymbolSuggestionPanel
        sessionId="sess-1"
        groupKey="ifc_class:IfcDoor"
        {...props}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  suggestSpy.mockReset();
});

afterEach(() => {
  cleanup();
});

describe('SymbolSuggestionPanel', () => {
  it('renders the ranked list with confidence chips', async () => {
    suggestSpy.mockResolvedValue(RANKED);
    renderPanel();

    // Wait for the door row to mount (top suggestion).
    await screen.findByTestId('symbol-suggestion-door');

    // All three suggestions render, in order.
    const list = screen.getByTestId('symbol-suggestion-list');
    const items = list.querySelectorAll('[data-testid^="symbol-suggestion-"]');
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveAttribute('data-testid', 'symbol-suggestion-door');
    expect(items[1]).toHaveAttribute('data-testid', 'symbol-suggestion-window');
    expect(items[2]).toHaveAttribute('data-testid', 'symbol-suggestion-beam');

    // Confidence chips render with the right band + percentage.
    const chips = screen.getAllByTestId('symbol-confidence-chip');
    expect(chips).toHaveLength(3);
    expect(chips[0]).toHaveAttribute('data-band', 'high');
    expect(chips[0]).toHaveTextContent('100%');
    expect(chips[1]).toHaveAttribute('data-band', 'medium');
    expect(chips[1]).toHaveTextContent('42%');
    expect(chips[2]).toHaveAttribute('data-band', 'low');
  });

  it('always shows the honesty note (not CV)', async () => {
    suggestSpy.mockResolvedValue(RANKED);
    renderPanel();
    const note = await screen.findByTestId('symbol-honesty-note');
    expect(note.textContent?.toLowerCase()).toContain('computer-vision');
  });

  it('expands contributing factors on "Why?"', async () => {
    suggestSpy.mockResolvedValue(RANKED);
    renderPanel();
    await screen.findByTestId('symbol-suggestion-door');

    // Factors hidden until expanded.
    expect(screen.queryByTestId('symbol-factors-door')).toBeNull();

    fireEvent.click(screen.getByTestId('symbol-why-door'));

    const factors = await screen.findByTestId('symbol-factors-door');
    expect(factors).toHaveTextContent('category');
    expect(factors).toHaveTextContent('ratio:aspect');
  });

  it('calls onApplyForReview with the chosen suggestion (no auto-commit)', async () => {
    suggestSpy.mockResolvedValue(RANKED);
    const onApply = vi.fn();
    renderPanel({ onApplyForReview: onApply });
    await screen.findByTestId('symbol-suggestion-door');

    fireEvent.click(screen.getByTestId('symbol-apply-door'));

    expect(onApply).toHaveBeenCalledTimes(1);
    expect(onApply.mock.calls[0]?.[0]).toMatchObject({ symbol: 'door', rank: 0 });
    // The panel never calls confirm/apply itself.
    expect(suggestSpy).toHaveBeenCalledTimes(1);
  });

  it('renders an empty state when no symbol is recognised', async () => {
    suggestSpy.mockResolvedValue({
      ...RANKED,
      suggestions: [],
    });
    renderPanel();
    expect(await screen.findByTestId('symbol-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('symbol-suggestion-list')).toBeNull();
  });

  it('does not fetch when there is no input to fingerprint', () => {
    suggestSpy.mockResolvedValue(RANKED);
    renderPanel({ sessionId: undefined, groupKey: undefined });
    expect(suggestSpy).not.toHaveBeenCalled();
  });
});

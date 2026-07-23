// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for <AccuracyScoreboard /> - the AI trust moat made visible. It scores
// each agent's stated confidence against the outcomes the user recorded, and
// reads out a calibration verdict (well calibrated / over- / under-confident).
//
// Coverage:
//   1. A well-calibrated agent: shows accuracy %, Brier, and the calibrated tag.
//   2. An over-confident agent (claims much more than it delivers).
//   3. Prefers the descriptor's display name when available.
//   4. Empty state when no runs have been scored.

import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';

import type { AccuracyScore } from '../api';

/* -- i18n shim - return defaultValue with interpolation. -------------- */

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_key: string, opts?: { defaultValue?: string } & Record<string, unknown>) => {
      if (typeof opts === 'object' && opts && 'defaultValue' in opts) {
        let dv = String(opts.defaultValue ?? '');
        for (const [k, v] of Object.entries(opts)) {
          if (k === 'defaultValue' || k === 'defaultValue_plural') continue;
          dv = dv.replaceAll(`{{${k}}}`, String(v));
        }
        return dv;
      }
      return _key;
    },
    i18n: { language: 'en' },
  }),
  initReactI18next: { type: '3rdParty', init: () => undefined },
  I18nextProvider: ({ children }: { children: unknown }) => children,
  Trans: ({ children }: { children?: unknown }) => children ?? null,
}));

import { AccuracyScoreboard } from '../components/AccuracyScoreboard';

const baseScore: AccuracyScore = {
  agent_name: 'estimate_reviewer',
  count: 12,
  brier_score: 0.18,
  mean_confidence: 0.82,
  observed_rate: 0.75,
  calibration_error: 0.09,
  bins: [],
};

afterEach(cleanup);

describe('AccuracyScoreboard', () => {
  it('shows a well-calibrated agent with accuracy and Brier score', () => {
    render(<AccuracyScoreboard scores={[baseScore]} agents={[]} loading={false} />);
    // gap = 0.82 - 0.75 = 0.07 <= 0.1 -> well calibrated
    expect(screen.getByText('Well calibrated')).toBeInTheDocument();
    expect(screen.getByText('Estimate Reviewer')).toBeInTheDocument();
    expect(screen.getByText('Brier 0.18')).toBeInTheDocument();
    expect(screen.getByText('Said')).toBeInTheDocument();
    expect(screen.getByText('Real')).toBeInTheDocument();
  });

  it('flags an over-confident agent', () => {
    render(
      <AccuracyScoreboard
        scores={[{ ...baseScore, mean_confidence: 0.9, observed_rate: 0.5 }]}
        agents={[]}
        loading={false}
      />,
    );
    // gap = 0.9 - 0.5 = 0.4 > 0.1 -> over-confident
    expect(screen.getByText('Over-confident')).toBeInTheDocument();
  });

  it('prefers the descriptor display name when present', () => {
    render(
      <AccuracyScoreboard
        scores={[baseScore]}
        agents={[
          {
            name: 'estimate_reviewer',
            display_name: 'Estimate QA',
            description: '',
            max_iterations: 6,
            allowed_tools: [],
          },
        ]}
        loading={false}
      />,
    );
    expect(screen.getByText('Estimate QA')).toBeInTheDocument();
  });

  it('renders an empty state when nothing has been scored', () => {
    render(<AccuracyScoreboard scores={[]} agents={[]} loading={false} />);
    expect(screen.getByText('No scored runs yet')).toBeInTheDocument();
    // The sample-seed action is hidden unless the demo affordance is enabled.
    expect(screen.queryByRole('button', { name: /See AI in practice/i })).not.toBeInTheDocument();
  });

  it('offers the sample-seed action in the empty state on the demo and fires it', () => {
    const onSeedSample = vi.fn();
    render(
      <AccuracyScoreboard
        scores={[]}
        agents={[]}
        loading={false}
        canSeedSample
        onSeedSample={onSeedSample}
      />,
    );
    const btn = screen.getByRole('button', { name: /See AI in practice/i });
    fireEvent.click(btn);
    expect(onSeedSample).toHaveBeenCalledTimes(1);
  });

  it('does not offer the sample-seed action once runs are scored', () => {
    render(
      <AccuracyScoreboard scores={[baseScore]} agents={[]} loading={false} canSeedSample onSeedSample={vi.fn()} />,
    );
    expect(screen.queryByRole('button', { name: /See AI in practice/i })).not.toBeInTheDocument();
  });
});

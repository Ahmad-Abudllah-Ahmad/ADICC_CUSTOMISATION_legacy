// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for <FeedbackSummaryPanel /> - the read side of the generic trust loop.
// It rolls the user's thumbs up / down verdicts on non-run AI surfaces up into
// an overall correct rate plus a per-surface breakdown.
//
// Coverage:
//   1. Empty state when the user has no verdicts yet.
//   2. Populated: overall rate, per-surface counts and percentages.
//   3. A surface with no verdicts shows a dash, never a misleading 0%.

import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';

import type { AIFeedbackSummary } from '../api';

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

import { FeedbackSummaryPanel } from '../components/FeedbackSummaryPanel';

afterEach(cleanup);

describe('FeedbackSummaryPanel', () => {
  it('renders the empty state when there is no feedback yet', () => {
    render(<FeedbackSummaryPanel summary={{ total: 0, correct: 0, incorrect: 0, correct_rate: null, by_surface: [] }} loading={false} />);
    expect(screen.getByText('No feedback yet')).toBeInTheDocument();
  });

  it('renders the empty state when the summary is null', () => {
    render(<FeedbackSummaryPanel summary={null} loading={false} />);
    expect(screen.getByText('No feedback yet')).toBeInTheDocument();
  });

  it('shows the overall rate and a per-surface breakdown', () => {
    const summary: AIFeedbackSummary = {
      total: 4,
      correct: 3,
      incorrect: 1,
      correct_rate: 0.75,
      by_surface: [
        { surface: 'ai_estimator', total: 3, correct: 2, incorrect: 1, correct_rate: 0.6667 },
        { surface: 'advisor', total: 1, correct: 1, incorrect: 0, correct_rate: 1 },
      ],
    };
    render(<FeedbackSummaryPanel summary={summary} loading={false} />);

    expect(screen.getByText('75%')).toBeInTheDocument();
    expect(screen.getByText('marked correct')).toBeInTheDocument();
    // The test i18n shim uses the singular defaultValue, so match either form.
    expect(screen.getByText(/4 verdict/)).toBeInTheDocument();
    // Per-surface counts.
    expect(screen.getByText('2/3 correct')).toBeInTheDocument();
    expect(screen.getByText('1/1 correct')).toBeInTheDocument();
    // 0.6667 -> 67%, 1 -> 100%.
    expect(screen.getByText('67%')).toBeInTheDocument();
    expect(screen.getByText('100%')).toBeInTheDocument();
  });

  it('shows 0% for an all-wrong surface, not a dash (0% != no data)', () => {
    const summary: AIFeedbackSummary = {
      total: 2,
      correct: 0,
      incorrect: 2,
      correct_rate: 0,
      by_surface: [{ surface: 'advisor', total: 2, correct: 0, incorrect: 2, correct_rate: 0 }],
    };
    render(<FeedbackSummaryPanel summary={summary} loading={false} />);
    // "all wrong" reads as 0% (overall + the surface row), never a dash.
    expect(screen.getAllByText('0%').length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText('—')).not.toBeInTheDocument();
  });
});

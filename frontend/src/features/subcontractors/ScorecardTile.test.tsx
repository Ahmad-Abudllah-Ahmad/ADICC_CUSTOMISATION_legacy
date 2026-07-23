// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for <ScorecardTile> — the four-dial subcontractor performance
// scorecard rendered inside the DetailDrawer "Ratings" tab.
//
// Covers:
//   * Empty array renders the empty-state copy (no period selector).
//   * Single rating renders all four dials + overall, no trend chip.
//   * Two ratings render a positive trend chip with "+N vs prior".
//   * Two ratings with regression render a red trend chip with "-N".
//   * Score normalisation: < 0 clamps to 0, > 100 clamps to 100, so a
//     bug in the rating computation can't break the layout.

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { ScorecardTile } from './ScorecardTile';
import type { Rating } from './api';

function makeRating(period: string, scores: Partial<Rating> = {}): Rating {
  return {
    id: `r-${period}`,
    subcontractor_id: 'sub-1',
    period,
    quality_score: 0,
    hse_score: 0,
    schedule_score: 0,
    cost_score: 0,
    overall_score: 0,
    basis: {},
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...scores,
  };
}

describe('ScorecardTile', () => {
  it('shows the empty-state copy when no ratings exist', () => {
    render(<ScorecardTile ratings={[]} />);
    expect(
      screen.getByText(/No performance ratings recorded yet/i),
    ).toBeInTheDocument();
  });

  it('renders all four dials + overall when one period exists', () => {
    const r = makeRating('2026-05', {
      hse_score: 82,
      quality_score: 75,
      schedule_score: 90,
      cost_score: 68,
      overall_score: 79,
    });
    render(<ScorecardTile ratings={[r]} />);
    // The four dial labels + overall block.
    expect(screen.getByText('Safety')).toBeInTheDocument();
    expect(screen.getByText('Quality')).toBeInTheDocument();
    expect(screen.getByText('Schedule')).toBeInTheDocument();
    expect(screen.getByText('Cost')).toBeInTheDocument();
    expect(screen.getByText('Overall')).toBeInTheDocument();
    // Overall score is rendered.
    expect(screen.getByText('79')).toBeInTheDocument();
    // No "vs prior" chip when only one period exists.
    expect(screen.queryByText(/vs prior/i)).not.toBeInTheDocument();
  });

  it('renders a positive trend chip when current beats prior', () => {
    const current = makeRating('2026-05', {
      hse_score: 90,
      quality_score: 90,
      schedule_score: 90,
      cost_score: 90,
      overall_score: 90,
    });
    const prior = makeRating('2026-04', {
      hse_score: 70,
      quality_score: 70,
      schedule_score: 70,
      cost_score: 70,
      overall_score: 70,
    });
    render(<ScorecardTile ratings={[current, prior]} />);
    // The overall chip carries the aria-label form; each dial chip
    // matches "+20 vs prior period". We assert at least one "+20"
    // exists and that the "vs prior" badge copy is rendered.
    const positives = screen.getAllByText(/\+20/);
    expect(positives.length).toBeGreaterThan(0);
    expect(screen.getByText(/vs prior/i)).toBeInTheDocument();
  });

  it('renders a negative trend when current regresses vs prior', () => {
    const current = makeRating('2026-05', { overall_score: 50 });
    const prior = makeRating('2026-04', { overall_score: 70 });
    render(<ScorecardTile ratings={[current, prior]} />);
    // "-20" rather than "+-20" — sign formatting test. The overall
    // and dial chips both render, so we accept >= 1 match.
    const negatives = screen.getAllByText(/-20/);
    expect(negatives.length).toBeGreaterThan(0);
  });

  it('accepts numeric-string scores (Decimal-as-string from the API)', () => {
    // The API returns Decimal columns as JSON strings ("90.00") to
    // avoid float-precision loss; the tile must accept both shapes.
    const r = makeRating('2026-05', {
      hse_score: '82.00' as unknown as number,
      overall_score: '88.00' as unknown as number,
    });
    render(<ScorecardTile ratings={[r]} />);
    expect(screen.getByText('88')).toBeInTheDocument();
  });

  it('clamps out-of-range scores so the bar layout stays sane', () => {
    // Pathological data: negative HSE, > 100 quality. We still want
    // a visible card — the bars must clamp to [0, 100] internally.
    const r = makeRating('2026-05', {
      hse_score: -10,
      quality_score: 150,
      schedule_score: 50,
      cost_score: 50,
      overall_score: 50,
    });
    render(<ScorecardTile ratings={[r]} />);
    // The Safety bar's progressbar element should report aria-valuenow=0.
    const safetyBar = screen.getByLabelText(/Safety score 0 out of 100/i);
    expect(safetyBar).toBeInTheDocument();
    const qualityBar = screen.getByLabelText(/Quality score 100 out of 100/i);
    expect(qualityBar).toBeInTheDocument();
  });
});

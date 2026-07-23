// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Regression suite for the v3.0.6 "Currency normalization" hang fix.
//
// Symptom users reported: /match-elements would freeze on the
// "Currency normalization" stage for minutes at a time. The original
// MatchProgressCard was a pure wall-clock heuristic that painted a
// "Currency normalization" label at the 28s mark; real matches on
// non-trivial projects take 60-300s so the label sat there forever
// while the synchronous POST drained in the background. Compounding
// the bug, the fetch had no timeout and no cancel button, so a
// genuinely wedged backend would wedge the page too.
//
// Fix: (1) drive the timeline off the existing /progress endpoint when
// a sessionId is supplied; (2) remove the misleading "Currency
// normalization" stage from the timeline entirely (it was never a real
// backend stage); (3) ship a Cancel button + 5-minute fetch timeout so
// the user can always recover.
//
// These tests pin the user-visible contract so a regression that
// reintroduces the wall-clock-only timeline or drops the Cancel
// button fails loudly. The heavy parent flow (mutations, React Query)
// is intentionally not exercised — that surface is covered by the
// Playwright probe under qa-tests/_match-currency-fix/.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  render,
  screen,
  cleanup,
  act,
  fireEvent,
} from '@testing-library/react';

// Stub the api module BEFORE importing the card so its getProgress
// import binds to the spy. The default mock returns an idle snapshot
// — individual tests override per-call as needed.
vi.mock('../api', () => ({
  matchElementsApi: {
    getProgress: vi.fn().mockResolvedValue({
      stage: 'idle',
      stage_idx: 0,
      total_stages: 5,
      groups_done: 0,
      groups_total: 0,
      status: 'idle',
      started_at: null,
      updated_at: null,
      error: null,
    }),
  },
}));

import { matchElementsApi } from '../api';
import { MatchProgressCard } from '../MatchProgressCard';

const getProgressSpy = matchElementsApi.getProgress as ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.useFakeTimers();
  getProgressSpy.mockReset();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe('MatchProgressCard - v3.0.6 hang regression', () => {
  it('does not render a "Currency normalization" stage', () => {
    // The fake stage was the misleading label users saw freeze on.
    // The post-fix timeline carries only real backend stages.
    render(
      <MatchProgressCard
        status="running"
        onDone={() => {}}
      />,
    );
    expect(screen.queryByText(/currency normalization/i)).toBeNull();
  });

  it('renders all five real backend stages', () => {
    render(
      <MatchProgressCard
        status="running"
        onDone={() => {}}
      />,
    );
    // Stage rows are stamped with data-stage-row so the test doesn't
    // depend on locale-specific copy. Real backend stages: init,
    // elements, ranking, save, done (the runner's _write_progress
    // payload keys, see app/modules/match_elements/service.py).
    for (const stage of ['init', 'elements', 'ranking', 'save', 'done']) {
      expect(
        document.querySelector(`[data-stage-row="${stage}"]`),
      ).not.toBeNull();
    }
  });

  it('polls /progress when a sessionId is supplied', async () => {
    getProgressSpy.mockResolvedValue({
      stage: 'ranking',
      stage_idx: 3,
      total_stages: 5,
      groups_done: 4,
      groups_total: 10,
      status: 'running',
      started_at: null,
      updated_at: null,
      error: null,
    });

    render(
      <MatchProgressCard
        status="running"
        sessionId="session-xyz"
        onDone={() => {}}
      />,
    );

    // Drain the immediate-on-mount poll. Under fake timers we have
    // to advance microtasks manually — Promise.resolve x N flushes
    // the awaited body of the async poll callback so setState lands
    // before we assert.
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(getProgressSpy).toHaveBeenCalledWith('session-xyz');

    // Card data-source attribute flips to "backend" once the first
    // successful poll lands — proving the wall-clock fallback isn't
    // driving the timeline.
    const card = screen.getByTestId('match-progress-card');
    expect(card.getAttribute('data-progress-source')).toBe('backend');
  });

  it('does not poll /progress when no sessionId is supplied', async () => {
    render(
      <MatchProgressCard status="running" onDone={() => {}} />,
    );
    await act(async () => {
      vi.advanceTimersByTime(2000);
    });
    expect(getProgressSpy).not.toHaveBeenCalled();
    // Without backend data the card stays on the heuristic fallback.
    expect(
      screen.getByTestId('match-progress-card').getAttribute(
        'data-progress-source',
      ),
    ).toBe('heuristic');
  });

  it('shows a Cancel button after the 20s safety threshold', async () => {
    const onCancel = vi.fn();
    render(
      <MatchProgressCard
        status="running"
        onCancel={onCancel}
        onDone={() => {}}
      />,
    );

    // Cancel is hidden during the first 20s — it would be noise on
    // healthy short runs.
    expect(screen.queryByTestId('match-progress-cancel')).toBeNull();

    // Advance the wall-clock past the threshold; the card's 1Hz
    // ticker updates `now` on every interval.
    await act(async () => {
      vi.advanceTimersByTime(21_000);
    });
    expect(screen.getByTestId('match-progress-cancel')).not.toBeNull();
  });

  it('does not mount a Cancel button when onCancel is not provided', async () => {
    render(
      <MatchProgressCard status="running" onDone={() => {}} />,
    );
    await act(async () => {
      vi.advanceTimersByTime(30_000);
    });
    expect(screen.queryByTestId('match-progress-cancel')).toBeNull();
  });

  it('fires onCancel when the Cancel button is clicked', async () => {
    const onCancel = vi.fn();
    render(
      <MatchProgressCard
        status="running"
        onCancel={onCancel}
        onDone={() => {}}
      />,
    );
    await act(async () => {
      vi.advanceTimersByTime(21_000);
    });
    const cancelBtn = screen.getByTestId('match-progress-cancel');
    fireEvent.click(cancelBtn);
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('falls back to the heuristic timeline after three failed polls', async () => {
    getProgressSpy.mockRejectedValue(new Error('network down'));
    render(
      <MatchProgressCard
        status="running"
        sessionId="session-failing"
        onDone={() => {}}
      />,
    );

    // Three poll cycles ~= 3 * 800ms; flush microtasks each tick so
    // the rejected promise resolves before the next interval fires.
    for (let i = 0; i < 4; i++) {
      await act(async () => {
        vi.advanceTimersByTime(800);
        await Promise.resolve();
      });
    }

    const card = screen.getByTestId('match-progress-card');
    expect(card.getAttribute('data-progress-source')).toBe('heuristic');
  });

  it('renders groups_done / groups_total counter on the ranking stage', async () => {
    getProgressSpy.mockResolvedValue({
      stage: 'ranking',
      stage_idx: 3,
      total_stages: 5,
      groups_done: 7,
      groups_total: 12,
      status: 'running',
      started_at: null,
      updated_at: null,
      error: null,
    });

    render(
      <MatchProgressCard
        status="running"
        sessionId="session-with-counter"
        onDone={() => {}}
      />,
    );

    // Drain the awaited body of the immediate-poll callback. setState
    // chains commit synchronously inside the act flush.
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    // Counter text appears in the headline ("Ranking — 7 / 12") AND
    // on the ranking stage row. ``getAllByText`` covers both without
    // assuming a single mount point.
    expect(screen.getAllByText('7 / 12').length).toBeGreaterThan(0);
  });
});

describe('MatchProgressCard - empty (no-candidate) terminal state', () => {
  it('renders the empty explainer instead of a green "Match complete"', () => {
    render(
      <MatchProgressCard status="empty" onDone={() => {}} />,
    );
    // The dedicated empty footer is present...
    expect(screen.getByTestId('match-progress-empty')).not.toBeNull();
    // ...and the success copy is NOT — an empty run is not a success.
    expect(screen.queryByText(/Match complete/i)).toBeNull();
    // The card stamps its status so downstream / e2e can assert it.
    expect(
      screen.getByTestId('match-progress-card').getAttribute('data-status'),
    ).toBe('empty');
  });

  it('does NOT call onDone for the empty state (nothing to hand over)', async () => {
    const onDone = vi.fn();
    render(<MatchProgressCard status="empty" onDone={onDone} />);
    // onDone fires ~800ms after a *done* flip; empty must never advance.
    await act(async () => {
      vi.advanceTimersByTime(2000);
    });
    expect(onDone).not.toHaveBeenCalled();
  });

  it('fires onAdjust and onRetry from the empty footer buttons', () => {
    const onAdjust = vi.fn();
    const onRetry = vi.fn();
    render(
      <MatchProgressCard
        status="empty"
        onDone={() => {}}
        onAdjust={onAdjust}
        onRetry={onRetry}
      />,
    );
    fireEvent.click(screen.getByTestId('match-progress-empty-adjust'));
    expect(onAdjust).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByTestId('match-progress-empty-retry'));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});

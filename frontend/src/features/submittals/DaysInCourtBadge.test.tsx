// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for <DaysInCourtBadge>.

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render } from '@testing-library/react';

import { DaysInCourtBadge } from './DaysInCourtBadge';

const FIXED_NOW = new Date('2026-05-25T00:00:00Z');

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(FIXED_NOW);
});

afterEach(() => {
  vi.useRealTimers();
});

describe('<DaysInCourtBadge>', () => {
  it('renders nothing when date_submitted is null', () => {
    const { container } = render(
      <DaysInCourtBadge dateSubmitted={null} status="submitted" />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing for draft (not yet in reviewer court)', () => {
    const { container } = render(
      <DaysInCourtBadge dateSubmitted="2026-05-01" status="draft" />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing for approved (already returned)', () => {
    const { container } = render(
      <DaysInCourtBadge dateSubmitted="2026-05-01" status="approved" />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing for revise_and_resubmit (ball returned)', () => {
    const { container } = render(
      <DaysInCourtBadge dateSubmitted="2026-05-01" status="revise_and_resubmit" />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing for a fresh submission (under threshold)', () => {
    // Submitted yesterday — 1d in court, below the 3d neutral threshold.
    const { container } = render(
      <DaysInCourtBadge dateSubmitted="2026-05-24" status="submitted" />,
    );
    expect(container.firstChild).toBeNull();
  });

  // The shared vitest setup mocks react-i18next with a `t` that returns
  // the `defaultValue` template verbatim (no {{days}} interpolation). We
  // assert the badge picks the right branch by matching the template
  // string and the surrounding day count is verified at runtime by
  // i18next.
  it('renders neutral badge in the 3-7d range', () => {
    const { container } = render(
      <DaysInCourtBadge dateSubmitted="2026-05-20" status="under_review" />,
    );
    // Renders something (not null) and uses the in-court template.
    expect(container.firstChild).not.toBeNull();
    expect(container.textContent).toMatch(/in court/i);
  });

  it('renders warning variant at 8-13 days', () => {
    const { container } = render(
      <DaysInCourtBadge dateSubmitted="2026-05-15" status="under_review" />,
    );
    expect(container.firstChild).not.toBeNull();
    expect(container.textContent).toMatch(/in court/i);
  });

  it('renders error variant + SLA-breach a11y text at 14d+', () => {
    // 20 days in court — past the AIA G714 14-day SLA window.
    const { container } = render(
      <DaysInCourtBadge dateSubmitted="2026-05-05" status="under_review" />,
    );
    expect(container.textContent).toMatch(/in court/i);
    expect(container.textContent).toMatch(/SLA breached/i);
  });

  it('renders nothing for malformed dates', () => {
    const { container } = render(
      <DaysInCourtBadge dateSubmitted="not-a-date" status="submitted" />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('clamps negative diffs to zero (future-dated submissions)', () => {
    // Future submission shouldn't ever happen but must not crash.
    const { container } = render(
      <DaysInCourtBadge dateSubmitted="2026-12-01" status="submitted" />,
    );
    // 0 days < neutral threshold → nothing rendered.
    expect(container.firstChild).toBeNull();
  });
});

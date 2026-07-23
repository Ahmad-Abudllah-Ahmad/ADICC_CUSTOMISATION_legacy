// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for <DueDateBadge>.
//
// Pins the system clock so the date arithmetic is deterministic. The
// badge does its math in UTC (Date.UTC + getUTCFullYear, ...), so
// freezing UTC midnight is enough — no need to spoof timezones.

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render } from '@testing-library/react';

import { DueDateBadge } from './DueDateBadge';

const FIXED_NOW = new Date('2026-05-25T00:00:00Z');

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(FIXED_NOW);
});

afterEach(() => {
  vi.useRealTimers();
});

describe('<DueDateBadge>', () => {
  it('renders nothing when date_required is null', () => {
    const { container } = render(
      <DueDateBadge dateRequired={null} status="submitted" />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing for an approved submittal even if overdue', () => {
    const { container } = render(
      <DueDateBadge dateRequired="2026-05-20" status="approved" />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing for a closed submittal', () => {
    const { container } = render(
      <DueDateBadge dateRequired="2026-05-20" status="closed" />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing for a rejected submittal', () => {
    const { container } = render(
      <DueDateBadge dateRequired="2026-05-20" status="rejected" />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing for revise_and_resubmit (ball is with submitter)', () => {
    const { container } = render(
      <DueDateBadge dateRequired="2026-05-20" status="revise_and_resubmit" />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing when due more than a week out', () => {
    const { container } = render(
      <DueDateBadge dateRequired="2026-07-01" status="submitted" />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('flags overdue with day count', () => {
    const { container } = render(
      <DueDateBadge dateRequired="2026-05-20" status="submitted" />,
    );
    expect(container.textContent).toMatch(/Overdue/i);
  });

  it('flags due-today', () => {
    const { container } = render(
      <DueDateBadge dateRequired="2026-05-25" status="submitted" />,
    );
    expect(container.textContent).toMatch(/Due today/i);
  });

  it('flags due-in-N-days when within a week', () => {
    const { container } = render(
      <DueDateBadge dateRequired="2026-05-28" status="submitted" />,
    );
    expect(container.textContent).toMatch(/Due in/i);
  });

  it('renders nothing for malformed dates', () => {
    const { container } = render(
      <DueDateBadge dateRequired="not-a-date" status="submitted" />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('treats under_review the same as submitted (still in court)', () => {
    const { container } = render(
      <DueDateBadge dateRequired="2026-05-20" status="under_review" />,
    );
    expect(container.textContent).toMatch(/Overdue/i);
  });
});

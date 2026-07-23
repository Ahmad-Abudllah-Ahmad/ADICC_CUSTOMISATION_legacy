// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import {
  ProjectStatusBadge,
  CURATED_PROJECT_STATUSES,
} from '../ProjectStatusBadge';

describe('ProjectStatusBadge', () => {
  it('renders curated statuses with their English labels', () => {
    render(<ProjectStatusBadge status="active" />);
    expect(screen.getByText('Active')).toBeInTheDocument();
  });

  it('humanises the on_hold token to "On hold"', () => {
    render(<ProjectStatusBadge status="on_hold" />);
    expect(screen.getByText('On hold')).toBeInTheDocument();
  });

  it('humanises an unknown custom status (in_review -> In review)', () => {
    render(<ProjectStatusBadge status="in_review" />);
    expect(screen.getByText('In review')).toBeInTheDocument();
  });

  it('renders the curated "cancelled" status with its label (#284)', () => {
    // "cancelled" is a curated terminal status (distinct from "on hold" /
    // "waiting"), so it must render its own label, not a humanised fallback.
    render(<ProjectStatusBadge status="cancelled" />);
    expect(screen.getByText('Cancelled')).toBeInTheDocument();
  });

  it('includes "cancelled" in the curated set so pickers/filters offer it (#284)', () => {
    // The status picker + any status-driven UI map over CURATED_PROJECT_STATUSES,
    // so membership here is what surfaces the option everywhere it is chosen.
    expect(CURATED_PROJECT_STATUSES).toContain('cancelled');
  });

  it('renders every curated status without throwing', () => {
    for (const s of CURATED_PROJECT_STATUSES) {
      const { unmount } = render(<ProjectStatusBadge status={s} />);
      unmount();
    }
    expect(CURATED_PROJECT_STATUSES).toContain('archived');
  });

  it('falls back to the raw value when the status has no separators', () => {
    render(<ProjectStatusBadge status="paused" />);
    // "paused" is title-cased to "Paused".
    expect(screen.getByText('Paused')).toBeInTheDocument();
  });
});

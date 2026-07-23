// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for <SubmittalStatusPipeline>.

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { SubmittalStatusPipeline } from './SubmittalStatusPipeline';

describe('<SubmittalStatusPipeline>', () => {
  it('renders four dots for a happy-path submittal', () => {
    const { container } = render(<SubmittalStatusPipeline status="submitted" />);
    // 4 dot spans = 4 stages on the happy path.
    const dots = container.querySelectorAll('span');
    expect(dots.length).toBe(4);
  });

  it('exposes an accessible label naming the current stage', () => {
    render(<SubmittalStatusPipeline status="under_review" />);
    const node = screen.getByRole('img');
    expect(node).toHaveAttribute('aria-label', expect.stringContaining('Under Review'));
  });

  it('falls back to draft for an unknown status', () => {
    render(<SubmittalStatusPipeline status="bogus_garbage" />);
    const node = screen.getByRole('img');
    expect(node).toHaveAttribute('aria-label', expect.stringContaining('Draft'));
  });

  it('collapses to a single bar for rejected', () => {
    const { container } = render(<SubmittalStatusPipeline status="rejected" />);
    const dots = container.querySelectorAll('span');
    expect(dots.length).toBe(1);
    expect(screen.getByRole('img')).toHaveAttribute(
      'aria-label',
      expect.stringContaining('Rejected'),
    );
  });

  it('collapses to a single bar for revise_and_resubmit', () => {
    const { container } = render(
      <SubmittalStatusPipeline status="revise_and_resubmit" />,
    );
    const dots = container.querySelectorAll('span');
    expect(dots.length).toBe(1);
    expect(screen.getByRole('img')).toHaveAttribute(
      'aria-label',
      expect.stringContaining('Revise'),
    );
  });

  it('collapses to a single bar for closed', () => {
    const { container } = render(<SubmittalStatusPipeline status="closed" />);
    const dots = container.querySelectorAll('span');
    expect(dots.length).toBe(1);
    expect(screen.getByRole('img')).toHaveAttribute(
      'aria-label',
      expect.stringContaining('Closed'),
    );
  });

  it('marks the approved stage as the last active dot', () => {
    render(<SubmittalStatusPipeline status="approved" />);
    expect(screen.getByRole('img')).toHaveAttribute(
      'aria-label',
      expect.stringContaining('Approved'),
    );
  });

  it('handles empty string as draft', () => {
    render(<SubmittalStatusPipeline status="" />);
    const node = screen.getByRole('img');
    expect(node).toHaveAttribute('aria-label', expect.stringContaining('Draft'));
  });
});

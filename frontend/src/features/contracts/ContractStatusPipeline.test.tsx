// DDC-CWICR-OE: DataDrivenConstruction / OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for <ContractStatusPipeline>.

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { ContractStatusPipeline } from './ContractStatusPipeline';

describe('<ContractStatusPipeline>', () => {
  it('renders three dots for the canonical draft→active→completed flow', () => {
    const { container } = render(<ContractStatusPipeline status="draft" />);
    const dots = container.querySelectorAll('span');
    expect(dots.length).toBe(3);
  });

  it('exposes an accessible label including the current stage', () => {
    render(<ContractStatusPipeline status="active" />);
    expect(screen.getByRole('img')).toHaveAttribute(
      'aria-label',
      expect.stringContaining('Active'),
    );
  });

  it('falls back to draft for an unknown status', () => {
    render(<ContractStatusPipeline status="bogus" />);
    expect(screen.getByRole('img')).toHaveAttribute(
      'aria-label',
      expect.stringContaining('Draft'),
    );
  });

  it('collapses to a single red bar when terminated', () => {
    const { container } = render(<ContractStatusPipeline status="terminated" />);
    const bars = container.querySelectorAll('span');
    expect(bars.length).toBe(1);
    expect(screen.getByRole('img')).toHaveAttribute(
      'aria-label',
      expect.stringContaining('Terminated'),
    );
  });

  it('renders an amber suspended pause variant with three indicators', () => {
    const { container } = render(<ContractStatusPipeline status="suspended" />);
    const bars = container.querySelectorAll('span');
    expect(bars.length).toBe(3);
    expect(screen.getByRole('img')).toHaveAttribute(
      'aria-label',
      expect.stringContaining('Suspended'),
    );
  });

  it('marks completed as the rightmost active dot', () => {
    render(<ContractStatusPipeline status="completed" />);
    expect(screen.getByRole('img')).toHaveAttribute(
      'aria-label',
      expect.stringContaining('Completed'),
    );
  });
});

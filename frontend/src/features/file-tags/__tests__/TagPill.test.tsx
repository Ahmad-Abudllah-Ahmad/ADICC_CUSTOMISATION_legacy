// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction

import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { TagPill } from '../TagPill';
import type { TagRecord } from '../types';

function makeTag(overrides: Partial<TagRecord> = {}): TagRecord {
  return {
    id: '11111111-1111-1111-1111-111111111111',
    project_id: '22222222-2222-2222-2222-222222222222',
    name: 'structural',
    display_name: 'Structural',
    color: '#ef4444',
    category: 'discipline',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    created_by_id: null,
    assignment_count: 0,
    ...overrides,
  };
}

describe('TagPill', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the tag display name and the color dot', () => {
    render(<TagPill tag={makeTag()} />);
    expect(screen.getByText('Structural')).toBeInTheDocument();
    const dot = screen.getByTestId('tag-pill-dot');
    expect(dot).toBeInTheDocument();
    // The dot's inline style carries the tag color verbatim.
    expect(dot.getAttribute('style') ?? '').toContain('rgb(239, 68, 68)');
  });

  it('does NOT render the × button by default', () => {
    render(<TagPill tag={makeTag()} />);
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('shows the × button when removable=true and calls onRemove on click', () => {
    const onRemove = vi.fn();
    const tag = makeTag();
    render(<TagPill tag={tag} removable onRemove={onRemove} />);
    const btn = screen.getByRole('button');
    expect(btn).toBeInTheDocument();
    fireEvent.click(btn);
    expect(onRemove).toHaveBeenCalledTimes(1);
    expect(onRemove).toHaveBeenCalledWith(tag);
  });

  it('does not call onRemove when removable=false even if onRemove is passed', () => {
    const onRemove = vi.fn();
    render(<TagPill tag={makeTag()} removable={false} onRemove={onRemove} />);
    expect(screen.queryByRole('button')).toBeNull();
    expect(onRemove).not.toHaveBeenCalled();
  });

  it('renders larger size variant when size="md"', () => {
    const { rerender } = render(<TagPill tag={makeTag()} size="sm" />);
    const small = screen.getByTestId('tag-pill').className;

    rerender(<TagPill tag={makeTag()} size="md" />);
    const medium = screen.getByTestId('tag-pill').className;
    expect(small).not.toEqual(medium);
  });

  it('exposes display_name via the title attribute for hover preview', () => {
    render(
      <TagPill
        tag={makeTag({ display_name: 'Mechanical & Plumbing Systems' })}
      />,
    );
    expect(
      screen.getByTitle('Mechanical & Plumbing Systems'),
    ).toBeInTheDocument();
  });
});

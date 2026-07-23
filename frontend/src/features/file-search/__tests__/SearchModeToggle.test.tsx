// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction

import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SearchModeToggle } from '../SearchModeToggle';

describe('SearchModeToggle', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders both modes as tabs', () => {
    render(<SearchModeToggle mode="filename" onChange={vi.fn()} />);
    // Each pill button has role="tab" and aria-selected reflects the active mode.
    const tabs = screen.getAllByRole('tab');
    expect(tabs).toHaveLength(2);
  });

  it('marks the active mode as aria-selected', () => {
    const { rerender } = render(
      <SearchModeToggle mode="filename" onChange={vi.fn()} />,
    );
    const filenameTab = screen.getByRole('tab', { selected: true });
    expect(filenameTab).toHaveTextContent(/Filename/);

    rerender(<SearchModeToggle mode="content" onChange={vi.fn()} />);
    const contentTab = screen.getByRole('tab', { selected: true });
    expect(contentTab).toHaveTextContent(/Content/);
  });

  it('calls onChange with "content" when the content tab is clicked', () => {
    const onChange = vi.fn();
    render(<SearchModeToggle mode="filename" onChange={onChange} />);
    const contentTab = screen.getByRole('tab', { name: /Content/ });
    fireEvent.click(contentTab);
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith('content');
  });

  it('calls onChange with "filename" when the filename tab is clicked', () => {
    const onChange = vi.fn();
    render(<SearchModeToggle mode="content" onChange={onChange} />);
    const filenameTab = screen.getByRole('tab', { name: /Filename/ });
    fireEvent.click(filenameTab);
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith('filename');
  });

  it('respects the className override', () => {
    const { container } = render(
      <SearchModeToggle mode="filename" onChange={vi.fn()} className="custom-x" />,
    );
    const tablist = container.querySelector('[role="tablist"]');
    expect(tablist?.className).toContain('custom-x');
  });
});

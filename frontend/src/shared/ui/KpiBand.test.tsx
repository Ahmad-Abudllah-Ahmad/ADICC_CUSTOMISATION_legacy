import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ListChecks } from 'lucide-react';
import { KpiBand, type KpiBandItem } from './KpiBand';

describe('KpiBand', () => {
  const baseItems: KpiBandItem[] = [
    { key: 'open', label: 'Open', value: 12 },
    { key: 'overdue', label: 'Overdue', value: 3 },
  ];

  it('renders a tile per item with its label and value', () => {
    render(<KpiBand items={baseItems} />);

    expect(screen.getByText('Open')).toBeInTheDocument();
    expect(screen.getByText('12')).toBeInTheDocument();
    expect(screen.getByText('Overdue')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('renders nothing when given an empty list', () => {
    const { container } = render(<KpiBand items={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders the optional sub line and icon', () => {
    render(
      <KpiBand
        items={[{ key: 'age', label: 'Avg age', value: '4d', sub: 'open items', icon: ListChecks }]}
      />,
    );
    expect(screen.getByText('open items')).toBeInTheDocument();
  });

  it('makes a tile interactive when onClick is supplied and fires on click', () => {
    const onClick = vi.fn();
    render(<KpiBand items={[{ key: 'open', label: 'Open', value: 1, onClick }]} />);

    const tile = screen.getByRole('button', { name: 'Open' });
    fireEvent.click(tile);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('activates an interactive tile via the keyboard (Enter and Space)', () => {
    const onClick = vi.fn();
    render(
      <KpiBand
        items={[{ key: 'open', label: 'Open', value: 1, onClick, ariaLabel: 'Filter to open' }]}
      />,
    );

    const tile = screen.getByRole('button', { name: 'Filter to open' });
    fireEvent.keyDown(tile, { key: 'Enter' });
    fireEvent.keyDown(tile, { key: ' ' });
    expect(onClick).toHaveBeenCalledTimes(2);
  });

  it('leaves non-interactive tiles as plain, non-button elements', () => {
    render(<KpiBand items={baseItems} />);
    expect(screen.queryByRole('button')).toBeNull();
  });
});

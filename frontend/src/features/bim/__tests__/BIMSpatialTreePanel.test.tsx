// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Tests for the IFC spatial structure tree (B3): grouping, click-to-select,
 * node highlight, search filtering, and the empty state.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { BIMElementData } from '@/shared/ui/BIMViewer';
import BIMSpatialTreePanel from '../BIMSpatialTreePanel';

const els = [
  { id: 'wall-a', name: 'Wall A', element_type: 'IfcWall', storey: 'L1' },
  { id: 'wall-b', name: 'Wall B', element_type: 'IfcWall', storey: 'L2' },
  { id: 'slab-1', name: 'Slab 1', element_type: 'IfcSlab', storey: 'L1' },
] as unknown as BIMElementData[];

function setup(overrides: Partial<React.ComponentProps<typeof BIMSpatialTreePanel>> = {}) {
  const onSelectElement = vi.fn();
  const onHighlightElements = vi.fn();
  render(
    <BIMSpatialTreePanel
      elements={els}
      onSelectElement={onSelectElement}
      onHighlightElements={onHighlightElements}
      {...overrides}
    />,
  );
  return { onSelectElement, onHighlightElements };
}

describe('BIMSpatialTreePanel', () => {
  it('groups elements by storey (collapsed by default)', () => {
    setup();
    expect(screen.getByText('L1')).toBeInTheDocument();
    expect(screen.getByText('L2')).toBeInTheDocument();
    // collapsed: leaves are not in the DOM yet
    expect(screen.queryByText('Wall A')).not.toBeInTheDocument();
  });

  it('renders an empty state with no elements', () => {
    setup({ elements: [] });
    expect(screen.getByTestId('bim-structure-empty')).toBeInTheDocument();
  });

  it('highlights every element of a storey when its label is clicked', () => {
    const { onHighlightElements } = setup();
    fireEvent.click(screen.getByText('L2'));
    expect(onHighlightElements).toHaveBeenCalledWith(['wall-b']);
  });

  it('search filters the tree, auto-expands, and a leaf click selects it', () => {
    const { onSelectElement } = setup();
    fireEvent.change(screen.getByTestId('bim-structure-search'), {
      target: { value: 'slab' },
    });
    // The matching leaf is now visible (search auto-expands) ...
    const leaf = screen.getByText('Slab 1');
    expect(leaf).toBeInTheDocument();
    // ... and the non-matching wall is pruned.
    expect(screen.queryByText('Wall A')).not.toBeInTheDocument();
    fireEvent.click(leaf);
    expect(onSelectElement).toHaveBeenCalledWith('slab-1');
  });

  it('shows a no-matches message when the search excludes everything', () => {
    setup();
    fireEvent.change(screen.getByTestId('bim-structure-search'), {
      target: { value: 'zzzz-nothing' },
    });
    expect(screen.getByText(/No elements match/i)).toBeInTheDocument();
  });
});

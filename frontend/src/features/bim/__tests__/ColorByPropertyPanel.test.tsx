// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/** 
 * ColorByPropertyPanel UI tests — v3.13.0 W6.6.
 *
 * Mocks the ElementManager surface the panel touches
 * (`getAvailablePropertyKeys`, `getDistinctPropertyValues`,
 * `setColorByProperty`) and verifies the round-trip:
 *   - dropdowns populate from the manager
 *   - Apply → setColorByProperty called with the chosen config
 *   - Reset → setColorByProperty(null)
 *   - sequential palettes show min/max inputs
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import ColorByPropertyPanel from '../ColorByPropertyPanel';
import type { ElementManager, PropertyValueCount } from '@/shared/ui/BIMViewer';

interface MockManager {
  manager: ElementManager;
  setColorByProperty: ReturnType<typeof vi.fn>;
}

function buildMockManager(
  keys: string[],
  distinctMap: Record<string, PropertyValueCount[]>,
): MockManager {
  const setColorByProperty = vi.fn();
  const manager = {
    getAvailablePropertyKeys: vi.fn(() => keys),
    getDistinctPropertyValues: vi.fn((k: string) => distinctMap[k] ?? []),
    setColorByProperty,
  } as unknown as ElementManager;
  return { manager, setColorByProperty };
}

describe('ColorByPropertyPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('populates the property dropdown from the manager', () => {
    const { manager } = buildMockManager(['fire_rating', 'level', 'category'], {
      fire_rating: [
        { value: 'F90', count: 3 },
        { value: 'F60', count: 2 },
      ],
    });

    render(<ColorByPropertyPanel elementManager={manager} />);

    const propertySelect = screen.getByTestId(
      'bim-color-by-property-key',
    ) as HTMLSelectElement;
    const options = Array.from(propertySelect.options).map((o) => o.value);
    expect(options).toEqual(['fire_rating', 'level', 'category']);
  });

  it('populates the palette dropdown with all four palettes', () => {
    const { manager } = buildMockManager(['fire_rating'], {});
    render(<ColorByPropertyPanel elementManager={manager} />);

    const paletteSelect = screen.getByTestId(
      'bim-color-by-property-palette',
    ) as HTMLSelectElement;
    const values = Array.from(paletteSelect.options).map((o) => o.value);
    expect(values).toEqual([
      'categorical-12',
      'sequential-blue',
      'sequential-red-blue',
      'fire-rating',
    ]);
  });

  it('shows numeric range inputs only for sequential palettes', () => {
    const { manager } = buildMockManager(['volume'], {
      volume: [
        { value: 1, count: 2 },
        { value: 10, count: 1 },
      ],
    });

    render(<ColorByPropertyPanel elementManager={manager} />);

    // categorical-12 by default → no range inputs.
    expect(screen.queryByTestId('bim-color-by-property-min')).toBeNull();

    const paletteSelect = screen.getByTestId('bim-color-by-property-palette');
    act(() => {
      fireEvent.change(paletteSelect, { target: { value: 'sequential-blue' } });
    });

    expect(screen.getByTestId('bim-color-by-property-min')).toBeTruthy();
    expect(screen.getByTestId('bim-color-by-property-max')).toBeTruthy();
  });

  it('calls setColorByProperty with the chosen config when Apply is clicked', () => {
    const { manager, setColorByProperty } = buildMockManager(['fire_rating'], {
      fire_rating: [
        { value: 'F90', count: 3 },
        { value: 'F60', count: 2 },
      ],
    });

    render(<ColorByPropertyPanel elementManager={manager} />);

    // Switch palette to fire-rating
    const paletteSelect = screen.getByTestId('bim-color-by-property-palette');
    act(() => {
      fireEvent.change(paletteSelect, { target: { value: 'fire-rating' } });
    });

    const applyBtn = screen.getByTestId('bim-color-by-property-apply');
    act(() => {
      fireEvent.click(applyBtn);
    });

    expect(setColorByProperty).toHaveBeenCalledTimes(1);
    expect(setColorByProperty).toHaveBeenCalledWith({
      propertyKey: 'fire_rating',
      palette: 'fire-rating',
    });
  });

  it('calls setColorByProperty with numericRange for sequential palettes', () => {
    const { manager, setColorByProperty } = buildMockManager(['volume'], {
      volume: [
        { value: 1, count: 2 },
        { value: 5, count: 3 },
        { value: 10, count: 1 },
      ],
    });

    render(<ColorByPropertyPanel elementManager={manager} />);

    const paletteSelect = screen.getByTestId('bim-color-by-property-palette');
    act(() => {
      fireEvent.change(paletteSelect, { target: { value: 'sequential-blue' } });
    });

    const applyBtn = screen.getByTestId('bim-color-by-property-apply');
    act(() => {
      fireEvent.click(applyBtn);
    });

    expect(setColorByProperty).toHaveBeenCalledTimes(1);
    const arg = setColorByProperty.mock.calls[0]![0];
    expect(arg.propertyKey).toBe('volume');
    expect(arg.palette).toBe('sequential-blue');
    expect(arg.numericRange).toBeDefined();
    expect(arg.numericRange[0]).toBe(1);
    expect(arg.numericRange[1]).toBe(10);
  });

  it('calls setColorByProperty(null) when Reset is clicked', () => {
    const { manager, setColorByProperty } = buildMockManager(['fire_rating'], {
      fire_rating: [{ value: 'F90', count: 1 }],
    });

    render(<ColorByPropertyPanel elementManager={manager} />);

    const resetBtn = screen.getByTestId('bim-color-by-property-reset');
    act(() => {
      fireEvent.click(resetBtn);
    });

    expect(setColorByProperty).toHaveBeenCalledTimes(1);
    expect(setColorByProperty).toHaveBeenCalledWith(null);
  });

  it('renders the categorical legend with swatches for the top values', () => {
    const { manager } = buildMockManager(['element_type'], {
      element_type: [
        { value: 'Walls', count: 12 },
        { value: 'Doors', count: 7 },
        { value: 'Windows', count: 3 },
      ],
    });

    render(<ColorByPropertyPanel elementManager={manager} />);

    // Legend rows include the value names.
    expect(screen.getByText('Walls')).toBeTruthy();
    expect(screen.getByText('Doors')).toBeTruthy();
    expect(screen.getByText('Windows')).toBeTruthy();
  });

  it('renders the gradient legend for sequential palettes with min/max labels', () => {
    const { manager } = buildMockManager(['volume'], {
      volume: [
        { value: 0, count: 1 },
        { value: 50, count: 1 },
        { value: 100, count: 1 },
      ],
    });

    render(<ColorByPropertyPanel elementManager={manager} />);

    const paletteSelect = screen.getByTestId('bim-color-by-property-palette');
    act(() => {
      fireEvent.change(paletteSelect, {
        target: { value: 'sequential-red-blue' },
      });
    });

    // Min/max labels in the gradient bar.
    expect(screen.getByText('0')).toBeTruthy();
    expect(screen.getByText('100')).toBeTruthy();
  });

  it('disables Apply when no property is selected (no keys)', () => {
    const { manager } = buildMockManager([], {});
    render(<ColorByPropertyPanel elementManager={manager} />);

    const applyBtn = screen.getByTestId(
      'bim-color-by-property-apply',
    ) as HTMLButtonElement;
    expect(applyBtn.disabled).toBe(true);
  });

  it('renders gracefully with a null manager', () => {
    render(<ColorByPropertyPanel elementManager={null} />);
    const root = screen.getByTestId('bim-color-by-property-panel');
    expect(root).toBeTruthy();
  });
});

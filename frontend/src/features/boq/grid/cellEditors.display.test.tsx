// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Issue #287 regression - measurement-system write boundaries in the BOQ grid.
 *
 * v9.4.0 made the grid imperial-aware for DISPLAY (renderers convert
 * metric->imperial) while storage stayed metric-canonical. The read side was
 * symmetric but the cell editors were not: they OPENED seeded with the raw
 * metric value while their commit path converts display->metric, so opening
 * and committing a cell unchanged double-converted and silently corrupted
 * storage for imperial users.
 *
 * These tests pin the fix from the user's side of the seam: each editor must
 * OPEN on the value the cell shows (display) and RETURN a display value for
 * the commit path to reverse. Both editors must be a strict no-op under
 * metric (identity), so this covers every country, not just the US.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, renderHook, cleanup, screen, fireEvent } from '@testing-library/react';
import { createRef } from 'react';

import { FormulaCellEditor, RateCellEditor } from './cellEditors';
import type { FormulaCellEditorParams } from './cellEditors';
import { useDisplayQuantity, type DisplayQuantityApi } from '@/shared/hooks/useDisplayQuantity';
import { usePreferencesStore, type MeasurementSystem } from '@/stores/usePreferencesStore';

/** Bind a real DisplayQuantityApi to a system (the same object the grid uses). */
function apiFor(system: MeasurementSystem): DisplayQuantityApi {
  usePreferencesStore.getState().setPreference('measurementSystem', system);
  const { result, unmount } = renderHook(() => useDisplayQuantity());
  const api = result.current; // pure functions closed over `system`
  unmount();
  return api;
}

type GetValueHandle = { getValue(): number };

function renderRate(value: number, unit: string, api: DisplayQuantityApi) {
  const ref = createRef<GetValueHandle>();
  const params = {
    value,
    data: { unit },
    context: { displayQuantity: api },
  } as unknown as FormulaCellEditorParams;
  render(<RateCellEditor {...params} ref={ref} />);
  const input = screen.getByRole('spinbutton') as HTMLInputElement;
  return { ref, input };
}

function renderQty(value: number, unit: string, api: DisplayQuantityApi) {
  const ref = createRef<GetValueHandle>();
  const params = {
    value,
    data: { unit },
    context: { displayQuantity: api },
    // no metadata.formula -> the plain-number branch we are fixing
  } as unknown as FormulaCellEditorParams;
  render(<FormulaCellEditor {...params} ref={ref} />);
  const input = screen.getByPlaceholderText(/123/) as HTMLInputElement;
  return { ref, input };
}

describe('RateCellEditor - Issue #287', () => {
  beforeEach(() => {
    cleanup();
    usePreferencesStore.getState().setPreference('measurementSystem', 'metric');
  });

  it('is a strict identity under metric (open + unchanged commit)', () => {
    const { input, ref } = renderRate(50, 'm', apiFor('metric'));
    expect(Number(input.value)).toBe(50);
    expect(ref.current!.getValue()).toBe(50);
  });

  it('opens on the reciprocal display rate under imperial and returns it', () => {
    // 50 per metre reads as ~15.24 per foot; the column valueParser reverses
    // the returned display value back to 50/m, so an unchanged commit is a
    // no-op instead of dividing the stored rate by the unit factor again.
    const { input, ref } = renderRate(50, 'm', apiFor('imperial'));
    expect(Number(input.value)).toBeCloseTo(15.24, 2);
    expect(ref.current!.getValue()).toBeCloseTo(15.24, 2);
  });

  it('leaves unitless rates untouched in imperial (pcs, lsum)', () => {
    const { input, ref } = renderRate(120, 'pcs', apiFor('imperial'));
    expect(Number(input.value)).toBe(120);
    expect(ref.current!.getValue()).toBe(120);
  });
});

describe('FormulaCellEditor quantity seed - Issue #287', () => {
  beforeEach(() => {
    cleanup();
    usePreferencesStore.getState().setPreference('measurementSystem', 'metric');
  });

  it('is a strict identity under metric', () => {
    const { input } = renderQty(10, 'm2', apiFor('metric'));
    expect(Number(input.value)).toBe(10);
  });

  it('opens on the converted quantity under imperial', () => {
    // 10 m2 -> ~107.64 ft2. The editor commits via toMetricQty, so seeding the
    // displayed value keeps open+commit-unchanged lossless.
    const { input } = renderQty(10, 'm2', apiFor('imperial'));
    expect(Number(input.value)).toBeCloseTo(107.639, 2);
  });

  it('leaves unitless quantities untouched in imperial (pcs)', () => {
    const { input } = renderQty(7, 'pcs', apiFor('imperial'));
    expect(Number(input.value)).toBe(7);
  });
});

/**
 * Resource-less unit-rate commit path.
 *
 * A rate typed on a BOQ position WITHOUT contributing resources was silently
 * dropped: ag-grid-react v32 + React 18 can skip the editor's getValue after
 * stopEditing, and the synthetic onChange did not always fire in the edit root,
 * so the cell reverted and no PATCH went out. The fix writes the value straight
 * to the row via node.setDataValue on Enter / Tab / blur and cancels ag-grid's
 * secondary commit. These tests pin that write path.
 */
describe('RateCellEditor - commit path (resource-less rate fix)', () => {
  beforeEach(() => {
    cleanup();
    usePreferencesStore.getState().setPreference('measurementSystem', 'metric');
  });

  function renderRateForCommit(seed: number, unit: string, api: DisplayQuantityApi) {
    const setDataValue = vi.fn();
    const stopEditing = vi.fn();
    const tabToNextCell = vi.fn();
    const params = {
      value: seed,
      data: { unit },
      context: { displayQuantity: api },
      node: { data: { unit, unit_rate: seed }, setDataValue },
      api: { stopEditing, tabToNextCell },
      column: { getColId: () => 'unit_rate' },
    } as unknown as FormulaCellEditorParams;
    render(<RateCellEditor {...params} />);
    const input = screen.getByRole('spinbutton') as HTMLInputElement;
    return { input, setDataValue, stopEditing, tabToNextCell };
  }

  it('writes a typed rate straight to the row on Enter (was silently dropped)', () => {
    const { input, setDataValue, stopEditing } = renderRateForCommit(0, 'm', apiFor('metric'));
    fireEvent.input(input, { target: { value: '99' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(setDataValue).toHaveBeenCalledWith('unit_rate', 99);
    // Wrote via setDataValue -> cancel ag-grid's secondary commit (stopEditing true).
    expect(stopEditing).toHaveBeenCalledWith(true);
  });

  it('also commits on blur, not just Enter', () => {
    const { input, setDataValue } = renderRateForCommit(0, 'm', apiFor('metric'));
    fireEvent.input(input, { target: { value: '42' } });
    fireEvent.blur(input);
    expect(setDataValue).toHaveBeenCalledWith('unit_rate', 42);
  });

  it('does not write or double-commit when the value is unchanged', () => {
    const { input, setDataValue, stopEditing } = renderRateForCommit(50, 'm', apiFor('metric'));
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(setDataValue).not.toHaveBeenCalled();
    expect(stopEditing).toHaveBeenCalledWith(false);
  });

  it('converts the typed display rate back to metric before writing (imperial)', () => {
    const { input, setDataValue } = renderRateForCommit(50, 'm', apiFor('imperial'));
    fireEvent.input(input, { target: { value: '16' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(setDataValue).toHaveBeenCalledTimes(1);
    const written = Number(setDataValue.mock.calls[0]![1]);
    // A per-foot figure stores as a larger per-metre rate, so NOT the raw 16.
    expect(written).toBeGreaterThan(16);
    expect(written).not.toBeCloseTo(16, 1);
  });
});

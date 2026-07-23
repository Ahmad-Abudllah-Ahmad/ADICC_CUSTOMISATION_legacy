/**
 * Tests for useDisplayQuantity — verifies the hook reads the live
 * measurementSystem preference and binds the converter to it (display +
 * reverse-for-edit), so the metric/imperial decision is consistent app-wide.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook, cleanup } from '@testing-library/react';

import { useDisplayQuantity } from './useDisplayQuantity';
import { usePreferencesStore, type MeasurementSystem } from '../../stores/usePreferencesStore';

function setSystem(system: MeasurementSystem) {
  usePreferencesStore.getState().setPreference('measurementSystem', system);
}

describe('useDisplayQuantity', () => {
  beforeEach(() => {
    cleanup();
    setSystem('metric');
  });

  it('passes metric quantities through, only tidying the unit label', () => {
    setSystem('metric');
    const { result } = renderHook(() => useDisplayQuantity());
    expect(result.current.system).toBe('metric');
    expect(result.current.convert(10, 'm2')).toEqual({ value: 10, unit: 'm²' });
    expect(result.current.unitFor('m3')).toBe('m³');
    expect(result.current.toMetric(10, 'm²')).toBe(10);
  });

  it('converts metric-canonical quantities to imperial', () => {
    setSystem('imperial');
    const { result } = renderHook(() => useDisplayQuantity());
    expect(result.current.system).toBe('imperial');
    const a = result.current.convert(10, 'm²');
    expect(a.value).toBeCloseTo(107.639, 3);
    expect(a.unit).toBe('ft²');
    expect(result.current.unitFor('m')).toBe('ft');
  });

  it('round-trips an edited imperial value back to metric storage', () => {
    setSystem('imperial');
    const { result } = renderHook(() => useDisplayQuantity());
    const shown = result.current.convert(20, 'm²');
    expect(result.current.toMetric(shown.value, 'm²')).toBeCloseTo(20, 6);
  });

  it('restates a per-unit rate reciprocally and reverses it for storage', () => {
    setSystem('imperial');
    const { result } = renderHook(() => useDisplayQuantity());
    const shownRate = result.current.convertRate(50, 'm'); // ~15.24 / ft
    expect(shownRate).toBeCloseTo(15.24, 2);
    expect(result.current.toMetricRate(shownRate, 'm')).toBeCloseTo(50, 6);
    expect(result.current.factorFor('m')).toBeCloseTo(3.2808399, 6);
  });

  it('keeps rates untouched in metric', () => {
    setSystem('metric');
    const { result } = renderHook(() => useDisplayQuantity());
    expect(result.current.convertRate(50, 'm')).toBe(50);
    expect(result.current.factorFor('m')).toBe(1);
  });
});

// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Regression tests for DWG measurement maths.
 *
 *  - D-TKC-006: formatMeasurement must NOT apply a linear k/m SI prefix
 *    to area/volume units (1500 m² was rendering as "1.50 km²").
 *  - D-TKC-015: a self-intersecting ("bowtie") polygon must be flagged,
 *    not silently reported as a wrong/zero area.
 */

import { describe, it, expect } from 'vitest';
import {
  formatMeasurement,
  calculateArea,
  calculateAreaSafe,
  isSelfIntersecting,
  unitFactorToMetres,
} from '../measurement';

describe('formatMeasurement - dimensional safety (D-TKC-006)', () => {
  it('keeps the SI k-prefix for LINEAR units', () => {
    expect(formatMeasurement(1500, 'm')).toBe('1.50 km');
    expect(formatMeasurement(0.005, 'm')).toBe('5.00 mm');
  });

  it('NEVER prefix-scales an area unit (was 1500 m² → "1.50 km2")', () => {
    const out = formatMeasurement(1500, 'm²');
    expect(out).not.toMatch(/k m²|km²|km2/);
    expect(out).toContain('m²');
    // 1500 m² stays 1500 m² (grouped), not 1.5 of anything.
    expect(out.replace(/[^0-9]/g, '')).toContain('1500');
  });

  it('NEVER prefix-scales a volume unit', () => {
    const out = formatMeasurement(2500, 'm³');
    expect(out).not.toMatch(/km³|km3/);
    expect(out).toContain('m³');
  });

  it('small composite values stay visible with precision, not "0"', () => {
    const out = formatMeasurement(0.005, 'm²');
    expect(out).not.toBe('0 m²');
    expect(out).toContain('m²');
    expect(parseFloat(out)).toBeCloseTo(0.005, 6);
  });

  it('non-finite input degrades to a safe label', () => {
    expect(formatMeasurement(NaN, 'm²')).toBe('0 m²');
  });
});

describe('calculateAreaSafe - degeneracy detection (D-TKC-015)', () => {
  const bowtie = [
    { x: 0, y: 0 },
    { x: 4, y: 4 },
    { x: 4, y: 0 },
    { x: 0, y: 4 },
  ];

  it('shoelace alone silently cancels the bowtie to ~0', () => {
    // Documents the underlying hazard the safe wrapper guards against.
    expect(calculateArea(bowtie)).toBeLessThan(1e-6);
  });

  it('isSelfIntersecting detects the crossing edges', () => {
    expect(isSelfIntersecting(bowtie)).toBe(true);
  });

  it('a simple square is NOT flagged and area is correct', () => {
    const square = [
      { x: 0, y: 0 },
      { x: 5, y: 0 },
      { x: 5, y: 5 },
      { x: 0, y: 5 },
    ];
    expect(isSelfIntersecting(square)).toBe(false);
    const r = calculateAreaSafe(square);
    expect(r.degenerate).toBeNull();
    expect(r.area).toBeCloseTo(25, 9);
  });

  it('a triangle can never self-intersect', () => {
    const tri = [
      { x: 0, y: 0 },
      { x: 3, y: 0 },
      { x: 0, y: 4 },
    ];
    expect(isSelfIntersecting(tri)).toBe(false);
    expect(calculateAreaSafe(tri).degenerate).toBeNull();
  });

  it('flags the bowtie as self_intersecting', () => {
    expect(calculateAreaSafe(bowtie).degenerate).toBe('self_intersecting');
  });

  it('flags fewer-than-three-points', () => {
    expect(calculateAreaSafe([{ x: 0, y: 0 }, { x: 1, y: 1 }]).degenerate).toBe(
      'too_few_points',
    );
  });

  it('flags a collapsed (zero-area) simple polygon', () => {
    const collinear = [
      { x: 0, y: 0 },
      { x: 1, y: 0 },
      { x: 2, y: 0 },
    ];
    expect(calculateAreaSafe(collinear).degenerate).toBe('zero');
  });
});

describe('unitFactorToMetres (D-TKC-002 support)', () => {
  it('maps mm/cm/m/ft/in to metre factors', () => {
    expect(unitFactorToMetres('mm')).toBe(0.001);
    expect(unitFactorToMetres('cm')).toBe(0.01);
    expect(unitFactorToMetres('m')).toBe(1);
    expect(unitFactorToMetres('ft')).toBeCloseTo(0.3048, 9);
    expect(unitFactorToMetres('in')).toBeCloseTo(0.0254, 9);
  });

  it('falls back to 1.0 for unitless / missing headers', () => {
    expect(unitFactorToMetres(null)).toBe(1);
    expect(unitFactorToMetres(undefined)).toBe(1);
    expect(unitFactorToMetres('')).toBe(1);
  });
});

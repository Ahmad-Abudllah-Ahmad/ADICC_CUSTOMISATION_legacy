// @ts-nocheck
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import {
  pixelDistance,
  toRealDistance,
  polygonAreaPixels,
  toRealArea,
  polygonPerimeterPixels,
  formatMeasurement,
  deriveScale,
  presetScale,
  ratioFromScale,
  COMMON_SCALES,
} from './data/scale-helpers';

describe('scale-helpers', () => {
  describe('pixelDistance', () => {
    it('should calculate distance between two points', () => {
      expect(pixelDistance(0, 0, 3, 4)).toBe(5);
    });

    it('should return 0 for same point', () => {
      expect(pixelDistance(5, 5, 5, 5)).toBe(0);
    });

    it('should handle negative coordinates', () => {
      expect(pixelDistance(-3, 0, 0, 4)).toBe(5);
    });
  });

  describe('toRealDistance', () => {
    it('should convert pixel distance using scale', () => {
      const scale = { pixelsPerUnit: 100, unitLabel: 'm' };
      expect(toRealDistance(500, scale)).toBe(5);
    });

    it('should return 0 for zero scale', () => {
      const scale = { pixelsPerUnit: 0, unitLabel: 'm' };
      expect(toRealDistance(500, scale)).toBe(0);
    });
  });

  describe('polygonAreaPixels', () => {
    it('should calculate area of a square', () => {
      const points = [
        { x: 0, y: 0 },
        { x: 100, y: 0 },
        { x: 100, y: 100 },
        { x: 0, y: 100 },
      ];
      expect(polygonAreaPixels(points)).toBe(10000);
    });

    it('should calculate area of a triangle', () => {
      const points = [
        { x: 0, y: 0 },
        { x: 100, y: 0 },
        { x: 50, y: 100 },
      ];
      expect(polygonAreaPixels(points)).toBe(5000);
    });

    it('should return 0 for less than 3 points', () => {
      expect(polygonAreaPixels([{ x: 0, y: 0 }])).toBe(0);
      expect(polygonAreaPixels([])).toBe(0);
    });
  });

  describe('toRealArea', () => {
    it('should convert pixel area using scale squared', () => {
      const scale = { pixelsPerUnit: 10, unitLabel: 'm' };
      // 10000 px² / (10 px/m)² = 100 m²
      expect(toRealArea(10000, scale)).toBe(100);
    });
  });

  describe('polygonPerimeterPixels', () => {
    it('should calculate perimeter of a square', () => {
      const points = [
        { x: 0, y: 0 },
        { x: 100, y: 0 },
        { x: 100, y: 100 },
        { x: 0, y: 100 },
      ];
      expect(polygonPerimeterPixels(points)).toBe(400);
    });

    it('should return 0 for less than 2 points', () => {
      expect(polygonPerimeterPixels([{ x: 0, y: 0 }])).toBe(0);
    });
  });

  describe('formatMeasurement', () => {
    it('should format sub-unit values with 4 decimals', () => {
      expect(formatMeasurement(0.123, 'm')).toBe('0.1230 m');
    });

    it('should format medium values with 2 decimals', () => {
      expect(formatMeasurement(12.345, 'm')).toBe('12.35 m');
    });

    it('should format large values with 1 decimal', () => {
      expect(formatMeasurement(1234.5, 'm')).toBe('1234.5 m');
    });

    it('suppresses only genuinely degenerate values (0 / negative / NaN)', () => {
      expect(formatMeasurement(0, 'm')).toBe('');
      expect(formatMeasurement(-1, 'm')).toBe('');
      expect(formatMeasurement(NaN, 'm')).toBe('');
    });

    // D-TKC-007: a real 9 mm distance / 80 cm² patch must stay VISIBLE
    // with enough precision, not collapse to '' or '0 m'.
    it('shows small-but-real quantities instead of hiding them', () => {
      expect(formatMeasurement(0.009, 'm')).toBe('0.0090 m');
      expect(formatMeasurement(0.008, 'm²')).toBe('0.0080 m²');
      expect(formatMeasurement(0.0004, 'm')).toBe('0.00040 m');
    });
  });

  describe('deriveScale', () => {
    it('should derive scale from known dimension', () => {
      const scale = deriveScale(200, 2); // 200 pixels = 2 meters
      expect(scale.pixelsPerUnit).toBe(100);
      expect(scale.unitLabel).toBe('m');
    });

    // D-TKC-010: must NOT silently fall back to 1 px = 1 m — that
    // inflated a 28 346 px line to "28 346 m". An invalid reference
    // yields an explicitly invalid scale so downstream maths → 0.
    it('returns an invalid scale (never 1:1) for bad inputs', () => {
      for (const s of [deriveScale(0, 2), deriveScale(100, 0), deriveScale(-5, 2), deriveScale(NaN, 2)]) {
        expect(s.pixelsPerUnit).toBe(0);
        expect(s.invalid).toBe(true);
      }
      // Downstream conversion stays safe (no grossly inflated reading).
      expect(toRealDistance(28346, deriveScale(0, 2))).toBe(0);
      expect(formatMeasurement(toRealDistance(28346, deriveScale(0, 2)), 'm')).toBe('');
    });
  });

  // D-TKC-029: pin the 72-DPI / PDF-point invariant the preset scale
  // buttons rely on. A 1:100 preset must give ≈28.3465 px/m and a
  // round-trip through ratioFromScale must recover the ratio.
  describe('presetScale (72 DPI PDF-point invariant)', () => {
    it('1:100 yields ≈28.3465 pixels per metre', () => {
      const s = presetScale(100);
      expect(s.pixelsPerUnit).toBeCloseTo(28.3465, 3);
      expect(s.unitLabel).toBe('m');
    });

    it('a 10 m square drawn at 1:100 reads 100 m²', () => {
      const s = presetScale(100);
      const sidePx = 10 * s.pixelsPerUnit; // 10 m on paper
      const sq = [
        { x: 0, y: 0 },
        { x: sidePx, y: 0 },
        { x: sidePx, y: sidePx },
        { x: 0, y: sidePx },
      ];
      expect(toRealArea(polygonAreaPixels(sq), s)).toBeCloseTo(100, 4);
    });

    it('ratioFromScale round-trips every common preset', () => {
      for (const { ratio } of COMMON_SCALES) {
        expect(ratioFromScale(presetScale(ratio))).toBe(ratio);
      }
    });

    it('rejects a non-positive ratio with an invalid scale', () => {
      expect(presetScale(0).invalid).toBe(true);
      expect(presetScale(-50).invalid).toBe(true);
    });
  });

  describe('COMMON_SCALES', () => {
    it('should have standard architectural scales', () => {
      expect(COMMON_SCALES.length).toBeGreaterThan(5);
      expect(COMMON_SCALES.some((s) => s.label === '1:100')).toBe(true);
      expect(COMMON_SCALES.some((s) => s.label === '1:50')).toBe(true);
    });

    it('should have increasing ratios', () => {
      for (let i = 1; i < COMMON_SCALES.length; i++) {
        expect(COMMON_SCALES[i].ratio).toBeGreaterThan(COMMON_SCALES[i - 1].ratio);
      }
    });
  });
});

describe('TakeoffViewerModule', () => {
  // Lazy loaded component — test manifest registration
  it('should be registered in MODULE_REGISTRY', async () => {
    const { MODULE_REGISTRY } = await import('../_registry');
    const mod = MODULE_REGISTRY.find((m) => m.id === 'pdf-takeoff');
    expect(mod).toBeDefined();
    expect(mod!.name).toBe('PDF Takeoff Viewer');
    expect(mod!.routes[0].path).toBe('/takeoff-viewer');
  }, 15000);
});

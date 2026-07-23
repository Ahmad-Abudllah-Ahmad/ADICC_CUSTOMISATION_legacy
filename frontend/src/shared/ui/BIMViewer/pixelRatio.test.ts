// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
import { describe, it, expect } from 'vitest';

import { MAX_PIXEL_RATIO, cappedDevicePixelRatio } from './pixelRatio';

describe('cappedDevicePixelRatio', () => {
  it('caps a 3x display at 2', () => {
    expect(cappedDevicePixelRatio(3)).toBe(2);
  });

  it('caps a 4x / 4K panel at the ceiling', () => {
    expect(cappedDevicePixelRatio(4)).toBe(MAX_PIXEL_RATIO);
  });

  it('leaves a 1.5x display untouched', () => {
    expect(cappedDevicePixelRatio(1.5)).toBe(1.5);
  });

  it('leaves exactly 2x untouched (the common retina no-op)', () => {
    expect(cappedDevicePixelRatio(2)).toBe(2);
  });

  it('leaves 1x untouched', () => {
    expect(cappedDevicePixelRatio(1)).toBe(1);
  });

  it('falls back to 1 for a non-positive or non-finite ratio', () => {
    expect(cappedDevicePixelRatio(0)).toBe(1);
    expect(cappedDevicePixelRatio(-2)).toBe(1);
    expect(cappedDevicePixelRatio(Number.NaN)).toBe(1);
  });
});

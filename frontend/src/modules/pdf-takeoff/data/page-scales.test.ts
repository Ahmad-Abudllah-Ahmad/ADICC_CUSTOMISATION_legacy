import { describe, it, expect } from 'vitest';
import {
  emptyPageScales,
  defaultScaleConfig,
  scaleForPage,
  setPageScale,
  pageIsCalibrated,
  pageScalesHaveCalibration,
  reconcilePageScales,
  hydratePageScales,
  type PageScales,
} from './page-scales';

describe('page-scales (per-sheet scale model)', () => {
  it('uncalibrated pages fall back to the document default', () => {
    const ps = emptyPageScales();
    expect(scaleForPage(ps, 1).pixelsPerUnit).toBe(100);
    expect(scaleForPage(ps, 7).pixelsPerUnit).toBe(100);
    expect(pageIsCalibrated(ps, 1)).toBe(false);
  });

  it('setPageScale calibrates ONE page without touching others', () => {
    const ps0 = emptyPageScales();
    const ps1 = setPageScale(ps0, 3, { pixelsPerUnit: 25, unitLabel: 'm' });
    // Page 3 now has its own scale...
    expect(scaleForPage(ps1, 3).pixelsPerUnit).toBe(25);
    expect(pageIsCalibrated(ps1, 3)).toBe(true);
    // ...but other pages keep the default.
    expect(scaleForPage(ps1, 1).pixelsPerUnit).toBe(100);
    expect(pageIsCalibrated(ps1, 1)).toBe(false);
    // Immutable: the original is untouched.
    expect(pageIsCalibrated(ps0, 3)).toBe(false);
  });

  it('different sheets keep independent scales', () => {
    let ps = emptyPageScales();
    ps = setPageScale(ps, 1, { pixelsPerUnit: 144, unitLabel: 'm' }); // 1:50
    ps = setPageScale(ps, 3, { pixelsPerUnit: 14.4, unitLabel: 'm' }); // 1:500
    expect(scaleForPage(ps, 1).pixelsPerUnit).toBe(144);
    expect(scaleForPage(ps, 3).pixelsPerUnit).toBe(14.4);
    // A measurement on page 1 vs page 3 converts with its own ratio: the
    // SAME pixel length is a different real length on each sheet.
    const pxLen = 720;
    expect(pxLen / scaleForPage(ps, 1).pixelsPerUnit).toBeCloseTo(5, 6); // 5 m
    expect(pxLen / scaleForPage(ps, 3).pixelsPerUnit).toBeCloseTo(50, 6); // 50 m
  });

  describe('hydratePageScales (graceful migration)', () => {
    it('promotes a legacy single scale into the document default', () => {
      // Old document: only a single global scale, no per-page map.
      const legacy = { pixelsPerUnit: 50, unitLabel: 'm' };
      const ps = hydratePageScales(undefined, legacy);
      expect(ps.defaultScale.pixelsPerUnit).toBe(50);
      expect(ps.byPage).toEqual({});
      // Every page reads the legacy scale until re-calibrated, so existing
      // measurements keep the value they always had.
      expect(scaleForPage(ps, 1).pixelsPerUnit).toBe(50);
      expect(scaleForPage(ps, 9).pixelsPerUnit).toBe(50);
    });

    it('reads a new per-page model back as-is', () => {
      const saved: PageScales = {
        defaultScale: { pixelsPerUnit: 100, unitLabel: 'm' },
        byPage: { 2: { pixelsPerUnit: 25, unitLabel: 'm' } },
      };
      const ps = hydratePageScales(saved, undefined);
      expect(ps.defaultScale.pixelsPerUnit).toBe(100);
      expect(ps.byPage[2]!.pixelsPerUnit).toBe(25);
    });

    it('new model wins but borrows the legacy scale when its default is bad', () => {
      const saved = { byPage: { 2: { pixelsPerUnit: 25, unitLabel: 'm' } } };
      const legacy = { pixelsPerUnit: 60, unitLabel: 'm' };
      const ps = hydratePageScales(saved, legacy);
      expect(ps.defaultScale.pixelsPerUnit).toBe(60);
      expect(ps.byPage[2]!.pixelsPerUnit).toBe(25);
    });

    it('rejects malformed per-page entries', () => {
      const saved = {
        defaultScale: { pixelsPerUnit: 100, unitLabel: 'm' },
        byPage: {
          1: { pixelsPerUnit: 50, unitLabel: 'm' },
          2: { pixelsPerUnit: 'oops', unitLabel: 'm' }, // bad
          '-3': { pixelsPerUnit: 10, unitLabel: 'm' }, // bad page
        },
      };
      const ps = hydratePageScales(saved, undefined);
      expect(ps.byPage[1]!.pixelsPerUnit).toBe(50);
      expect(ps.byPage[2]).toBeUndefined();
      expect(ps.byPage[-3]).toBeUndefined();
    });

    it('falls back to the factory default with no inputs', () => {
      const ps = hydratePageScales(undefined, undefined);
      expect(ps.defaultScale).toEqual(defaultScaleConfig());
      expect(ps.byPage).toEqual({});
    });
  });

  describe('pageScalesHaveCalibration (issue #334)', () => {
    it('is false for the factory default', () => {
      expect(pageScalesHaveCalibration(emptyPageScales())).toBe(false);
    });

    it('is true once any page is calibrated', () => {
      const ps = setPageScale(emptyPageScales(), 2, { pixelsPerUnit: 25, unitLabel: 'm' });
      expect(pageScalesHaveCalibration(ps)).toBe(true);
    });

    it('is true when the document default was moved off the factory ratio', () => {
      const ps: PageScales = { defaultScale: { pixelsPerUnit: 50, unitLabel: 'm' }, byPage: {} };
      expect(pageScalesHaveCalibration(ps)).toBe(true);
    });
  });

  describe('reconcilePageScales (issue #334 load reconciliation)', () => {
    it('a stale local DEFAULT never overrides an explicit server calibration', () => {
      // The exact #334 failure: localStorage still on the factory default, the
      // server carries a real calibration. The server calibration must survive.
      const local = emptyPageScales();
      const server = setPageScale(emptyPageScales(), 1, { pixelsPerUnit: 144, unitLabel: 'm' });
      const merged = reconcilePageScales(local, server)!;
      expect(scaleForPage(merged, 1).pixelsPerUnit).toBe(144);
      expect(pageIsCalibrated(merged, 1)).toBe(true);
    });

    it('a local calibration is kept when the server has none', () => {
      const local = setPageScale(emptyPageScales(), 2, { pixelsPerUnit: 25, unitLabel: 'm' });
      const merged = reconcilePageScales(local, emptyPageScales())!;
      expect(scaleForPage(merged, 2).pixelsPerUnit).toBe(25);
    });

    it('unions per-page calibrations from both sides, local winning a conflict', () => {
      // Page 1 calibrated on the server (another device), page 3 here (local),
      // page 1 ALSO re-calibrated locally -> local wins page 1, page 3 survives.
      let server = setPageScale(emptyPageScales(), 1, { pixelsPerUnit: 100.5, unitLabel: 'm' });
      server = setPageScale(server, 5, { pixelsPerUnit: 10, unitLabel: 'm' });
      let local = setPageScale(emptyPageScales(), 1, { pixelsPerUnit: 144, unitLabel: 'm' });
      local = setPageScale(local, 3, { pixelsPerUnit: 25, unitLabel: 'm' });
      const merged = reconcilePageScales(local, server)!;
      expect(scaleForPage(merged, 1).pixelsPerUnit).toBe(144); // local wins the conflict
      expect(scaleForPage(merged, 3).pixelsPerUnit).toBe(25); // local-only survives
      expect(scaleForPage(merged, 5).pixelsPerUnit).toBe(10); // server-only survives
    });

    it('returns the non-null side and null when neither exists', () => {
      const only = setPageScale(emptyPageScales(), 1, { pixelsPerUnit: 30, unitLabel: 'm' });
      expect(reconcilePageScales(only, null)).toBe(only);
      expect(reconcilePageScales(null, only)).toBe(only);
      expect(reconcilePageScales(null, null)).toBeNull();
    });
  });
});

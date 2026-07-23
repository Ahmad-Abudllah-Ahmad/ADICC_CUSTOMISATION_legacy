import { describe, expect, it } from 'vitest';
import { enuFromLatLon, isWithinBounds, metresToModelUnits, modelPointFromGeo } from './geoLocate';

describe('enuFromLatLon', () => {
  it('is zero at the anchor itself', () => {
    const { east, north } = enuFromLatLon(52.52, 13.405, 52.52, 13.405);
    expect(east).toBeCloseTo(0, 6);
    expect(north).toBeCloseTo(0, 6);
  });

  it('moves north for higher latitude', () => {
    const { north } = enuFromLatLon(52.52, 13.405, 52.521, 13.405);
    // 0.001 deg lat ~ 110.54 m
    expect(north).toBeCloseTo(110.54, 1);
  });

  it('moves east for higher longitude, shrunk by cos(lat)', () => {
    const { east } = enuFromLatLon(52.52, 13.405, 52.52, 13.406);
    // 0.001 deg lon * cos(52.52) * 111320 ~ 67.7 m
    const expected = 0.001 * Math.cos((52.52 * Math.PI) / 180) * 111320;
    expect(east).toBeCloseTo(expected, 3);
    expect(east).toBeGreaterThan(0);
  });

  it('shrinks east offset toward the poles', () => {
    const equator = enuFromLatLon(0, 0, 0, 1).east;
    const high = enuFromLatLon(60, 0, 60, 1).east;
    expect(high).toBeLessThan(equator);
    expect(high).toBeCloseTo(equator * Math.cos((60 * Math.PI) / 180), 0);
  });
});

describe('modelPointFromGeo', () => {
  const anchor = { lat: 52.52, lon: 13.405 };

  it('maps the anchor to the origin (with default ground)', () => {
    const p = modelPointFromGeo(anchor, anchor);
    expect(p.x).toBeCloseTo(0, 6);
    expect(p.y).toBeCloseTo(0, 6);
    expect(p.z).toBeCloseTo(0, 6);
  });

  it('puts north into -Z and east into +X', () => {
    const north = modelPointFromGeo(anchor, { lat: 52.521, lon: 13.405 });
    expect(north.z).toBeLessThan(0);
    expect(Math.abs(north.x)).toBeLessThan(1e-6);

    const east = modelPointFromGeo(anchor, { lat: 52.52, lon: 13.406 });
    expect(east.x).toBeGreaterThan(0);
    expect(Math.abs(east.z)).toBeLessThan(1e-6);
  });

  it('scales metres into model units (mm)', () => {
    const p = modelPointFromGeo(anchor, { lat: 52.521, lon: 13.405 }, { metresToModelUnits: 1000 });
    // ~110.54 m north -> -110540 mm on Z
    expect(p.z).toBeCloseTo(-110540, 0);
  });

  it('honours groundY', () => {
    const p = modelPointFromGeo(anchor, anchor, { groundY: 5 });
    expect(p.y).toBe(5);
  });

  it('applies a 90deg north rotation into the X axis', () => {
    const p = modelPointFromGeo(
      anchor,
      { lat: 52.521, lon: 13.405 },
      { northRotationRad: Math.PI / 2 },
    );
    // north (0, +110.54) rotated +90deg -> east-component -110.54, mapped to X
    expect(p.x).toBeCloseTo(-110.54, 1);
    expect(Math.abs(p.z)).toBeLessThan(1e-3);
  });
});

describe('isWithinBounds', () => {
  const box = { min: { x: -10, y: 0, z: -10 }, max: { x: 10, y: 5, z: 10 } };

  it('accepts an interior point ignoring Y', () => {
    expect(isWithinBounds({ x: 0, y: 999, z: 0 }, box)).toBe(true);
  });

  it('rejects a point outside the footprint', () => {
    expect(isWithinBounds({ x: 20, y: 0, z: 0 }, box)).toBe(false);
  });

  it('accepts an outside point within margin', () => {
    expect(isWithinBounds({ x: 12, y: 0, z: 0 }, box, 5)).toBe(true);
  });
});

describe('metresToModelUnits', () => {
  it('maps common unit strings', () => {
    expect(metresToModelUnits('mm')).toBe(1000);
    expect(metresToModelUnits('Millimetre')).toBe(1000);
    expect(metresToModelUnits('cm')).toBe(100);
    expect(metresToModelUnits('ft')).toBeCloseTo(3.28084, 5);
    expect(metresToModelUnits('m')).toBe(1);
  });

  it('falls back to metres for unknown or empty units', () => {
    expect(metresToModelUnits('')).toBe(1);
    expect(metresToModelUnits(null)).toBe(1);
    expect(metresToModelUnits('parsecs')).toBe(1);
  });
});

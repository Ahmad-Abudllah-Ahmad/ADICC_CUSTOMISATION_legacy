import { describe, it, expect } from 'vitest';
import {
  distance3,
  polygonArea3,
  polygonPerimeter3,
  angleBetween3,
  centroid3,
} from '../measureMath';

describe('measureMath.distance3', () => {
  it('computes the 3-4-5 hypotenuse', () => {
    expect(distance3({ x: 0, y: 0, z: 0 }, { x: 3, y: 4, z: 0 })).toBe(5);
  });

  it('includes the z component', () => {
    // 1² + 2² + 2² = 9 → 3
    expect(distance3({ x: 0, y: 0, z: 0 }, { x: 1, y: 2, z: 2 })).toBe(3);
  });

  it('is zero for identical points', () => {
    expect(distance3({ x: 5, y: 5, z: 5 }, { x: 5, y: 5, z: 5 })).toBe(0);
  });
});

describe('measureMath.polygonArea3', () => {
  it('returns 0 for fewer than 3 points', () => {
    expect(polygonArea3([])).toBe(0);
    expect(polygonArea3([{ x: 0, y: 0, z: 0 }])).toBe(0);
    expect(
      polygonArea3([
        { x: 0, y: 0, z: 0 },
        { x: 1, y: 0, z: 0 },
      ]),
    ).toBe(0);
  });

  it('computes a unit square in the XY plane', () => {
    const area = polygonArea3([
      { x: 0, y: 0, z: 0 },
      { x: 1, y: 0, z: 0 },
      { x: 1, y: 1, z: 0 },
      { x: 0, y: 1, z: 0 },
    ]);
    expect(area).toBeCloseTo(1, 9);
  });

  it('is orientation-independent (same square in a tilted plane)', () => {
    // Triangle with legs 3 and 4 in the XZ plane → area 6.
    const area = polygonArea3([
      { x: 0, y: 0, z: 0 },
      { x: 3, y: 0, z: 0 },
      { x: 0, y: 0, z: 4 },
    ]);
    expect(area).toBeCloseTo(6, 9);
  });

  it('handles a 2×3 rectangle (= 6 m²)', () => {
    const area = polygonArea3([
      { x: 0, y: 0, z: 0 },
      { x: 2, y: 0, z: 0 },
      { x: 2, y: 3, z: 0 },
      { x: 0, y: 3, z: 0 },
    ]);
    expect(area).toBeCloseTo(6, 9);
  });
});

describe('measureMath.polygonPerimeter3', () => {
  it('returns the closed-loop perimeter of a unit square', () => {
    const p = polygonPerimeter3([
      { x: 0, y: 0, z: 0 },
      { x: 1, y: 0, z: 0 },
      { x: 1, y: 1, z: 0 },
      { x: 0, y: 1, z: 0 },
    ]);
    expect(p).toBeCloseTo(4, 9);
  });

  it('returns 0 for a single point', () => {
    expect(polygonPerimeter3([{ x: 0, y: 0, z: 0 }])).toBe(0);
  });
});

describe('measureMath.angleBetween3', () => {
  it('measures a right angle as 90°', () => {
    const deg = angleBetween3(
      { x: 1, y: 0, z: 0 },
      { x: 0, y: 0, z: 0 },
      { x: 0, y: 1, z: 0 },
    );
    expect(deg).toBeCloseTo(90, 9);
  });

  it('measures a straight line as 180°', () => {
    const deg = angleBetween3(
      { x: -1, y: 0, z: 0 },
      { x: 0, y: 0, z: 0 },
      { x: 1, y: 0, z: 0 },
    );
    expect(deg).toBeCloseTo(180, 9);
  });

  it('measures coincident rays as 0°', () => {
    const deg = angleBetween3(
      { x: 1, y: 1, z: 1 },
      { x: 0, y: 0, z: 0 },
      { x: 2, y: 2, z: 2 },
    );
    expect(deg).toBeCloseTo(0, 9);
  });

  it('returns 0 for a degenerate ray', () => {
    expect(
      angleBetween3(
        { x: 0, y: 0, z: 0 },
        { x: 0, y: 0, z: 0 },
        { x: 1, y: 0, z: 0 },
      ),
    ).toBe(0);
  });

  it('clamps floating-point overshoot (no NaN for collinear input)', () => {
    const deg = angleBetween3(
      { x: 0.1, y: 0.2, z: 0.3 },
      { x: 0, y: 0, z: 0 },
      { x: 0.2, y: 0.4, z: 0.6 },
    );
    expect(Number.isNaN(deg)).toBe(false);
    expect(deg).toBeCloseTo(0, 6);
  });
});

describe('measureMath.centroid3', () => {
  it('averages the points', () => {
    const c = centroid3([
      { x: 0, y: 0, z: 0 },
      { x: 2, y: 0, z: 0 },
      { x: 2, y: 6, z: 3 },
      { x: 0, y: 6, z: 3 },
    ]);
    expect(c).toEqual({ x: 1, y: 3, z: 1.5 });
  });

  it('returns origin for an empty set', () => {
    expect(centroid3([])).toEqual({ x: 0, y: 0, z: 0 });
  });
});

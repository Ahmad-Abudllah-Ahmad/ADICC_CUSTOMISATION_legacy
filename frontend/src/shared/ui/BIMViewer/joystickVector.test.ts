// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { describe, expect, it } from 'vitest';

import { joystickVector } from './joystickVector';

const R = 60;

describe('joystickVector', () => {
  it('returns zero at the centre', () => {
    const v = joystickVector(0, 0, R);
    expect(v.strafe).toBe(0);
    expect(v.forward).toBe(0);
    expect(v.magnitude).toBe(0);
    expect(v.knobX).toBe(0);
    expect(v.knobY).toBe(0);
  });

  it('pushing up (negative dy) is forward', () => {
    const v = joystickVector(0, -R, R);
    expect(v.forward).toBeCloseTo(1, 5);
    expect(v.strafe).toBeCloseTo(0, 5);
    expect(v.magnitude).toBeCloseTo(1, 5);
  });

  it('pushing down (positive dy) is backward', () => {
    const v = joystickVector(0, R, R);
    expect(v.forward).toBeCloseTo(-1, 5);
  });

  it('pushing right is positive strafe', () => {
    const v = joystickVector(R, 0, R);
    expect(v.strafe).toBeCloseTo(1, 5);
    expect(v.forward).toBeCloseTo(0, 5);
  });

  it('ignores movement inside the deadzone but still tracks the knob', () => {
    const v = joystickVector(R * 0.1, 0, R, { deadzone: 0.15 });
    expect(v.magnitude).toBe(0);
    expect(v.strafe).toBe(0);
    // Knob still follows the finger inside the deadzone.
    expect(v.knobX).toBeCloseTo(R * 0.1, 5);
  });

  it('clamps beyond the base to unit magnitude and keeps the knob on the ring', () => {
    const v = joystickVector(R * 3, 0, R);
    expect(v.strafe).toBeCloseTo(1, 5);
    expect(v.magnitude).toBeCloseTo(1, 5);
    expect(v.knobX).toBeCloseTo(R, 5); // knob clamped to the base radius
  });

  it('clamps a diagonal push to the unit circle (never exceeds full speed)', () => {
    const v = joystickVector(R, -R, R); // 45 degrees, distance sqrt(2)
    const speed = Math.hypot(v.strafe, v.forward);
    expect(speed).toBeLessThanOrEqual(1 + 1e-9);
    expect(v.strafe).toBeCloseTo(Math.SQRT1_2, 5);
    expect(v.forward).toBeCloseTo(Math.SQRT1_2, 5);
  });

  it('is zero for a non-positive or non-finite radius', () => {
    expect(joystickVector(10, 10, 0).magnitude).toBe(0);
    expect(joystickVector(10, 10, -5).magnitude).toBe(0);
    expect(joystickVector(Number.NaN, 0, R).magnitude).toBe(0);
  });

  it('ramps magnitude from just outside the deadzone toward the edge', () => {
    const near = joystickVector(R * 0.2, 0, R, { deadzone: 0.15 }).magnitude;
    const far = joystickVector(R * 0.8, 0, R, { deadzone: 0.15 }).magnitude;
    expect(near).toBeGreaterThan(0);
    expect(near).toBeLessThan(far);
    expect(far).toBeLessThan(1);
  });
});

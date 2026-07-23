// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Effective-quantity math for takeoff measurements.
 *
 * A raw measurement carries the geometry it was drawn at (plan length / area /
 * volume / count). The number an estimator actually reports can differ from
 * that geometry for three additive, opt-in reasons:
 *
 *   - slope / pitch  (area only): a sloped roof or ramp covers more true
 *                    surface than its plan projection, so the reported area is
 *                    `plan area x slopeFactor` (>= 1).
 *   - wastage %      : materials are ordered with an allowance on top of the
 *                    net quantity (cut waste, laps, breakage).
 *   - multiplier     : a "typical" detail repeats N times (typical floors,
 *                    identical bays) so one drawn shape stands for N.
 *
 * Every field is optional and its default is the identity value, so a
 * measurement with none of them set reports exactly its raw value - this whole
 * module is a no-op for existing data.
 *
 * {@link effectiveQuantity} is the SINGLE place this folding happens (plus the
 * opening-deduction sign) so the ledger, legend, exports and the linked-BOQ
 * push all report the same figure. It is pure + dependency-free (only the
 * shared Measurement type), so it unit-tests without React or pdf.js.
 */

import type { Measurement } from './takeoff-types';

/**
 * Clamp a user-entered slope/pitch FACTOR to a sane, finite multiplier.
 * A factor is dimensionless and never less than 1 (a slope only adds surface);
 * non-finite or <= 0 input falls back to 1 (flat, no change).
 */
export function normalizeSlopeFactor(raw: number | undefined | null): number {
  if (raw == null || !Number.isFinite(raw) || raw < 1) return 1;
  return raw;
}

/**
 * Convert a roof / ramp pitch in DEGREES to its plan -> true-surface area
 * factor, `1 / cos(deg)`. A flat 0 degrees gives 1; a 45 degree pitch gives
 * ~1.414. Guarded: input is clamped to (-89, 89) degrees so `cos` never
 * approaches 0 (an infinite factor), and any non-finite result falls back to
 * 1.
 */
export function slopeFactorFromDegrees(deg: number): number {
  if (!Number.isFinite(deg)) return 1;
  const clamped = Math.max(-89, Math.min(89, deg));
  const f = 1 / Math.cos((clamped * Math.PI) / 180);
  return Number.isFinite(f) && f >= 1 ? f : 1;
}

/**
 * Inverse of {@link slopeFactorFromDegrees}: the pitch in degrees that a given
 * factor corresponds to, `acos(1 / factor)`. Used to pre-fill the degrees
 * input from a stored factor. A factor <= 1 maps to 0 degrees (flat).
 */
export function degreesFromSlopeFactor(factor: number): number {
  if (!Number.isFinite(factor) || factor <= 1) return 0;
  const deg = (Math.acos(1 / factor) * 180) / Math.PI;
  return Number.isFinite(deg) ? deg : 0;
}

/**
 * Normalize the typical-multiplier to a positive integer count of repeats.
 * Non-finite or < 1 falls back to 1; a fractional value is floored (you cannot
 * have 2.5 typical floors).
 */
export function normalizeMultiplier(raw: number | undefined | null): number {
  if (raw == null || !Number.isFinite(raw)) return 1;
  const n = Math.floor(raw);
  return n >= 1 ? n : 1;
}

/**
 * Normalize the wastage / allowance percent (>= 0). Non-finite or negative
 * falls back to 0 (no allowance).
 */
export function normalizeWastagePct(raw: number | undefined | null): number {
  if (raw == null || !Number.isFinite(raw) || raw < 0) return 0;
  return raw;
}

/**
 * Unitless multiplier folding slope (area only), wastage and the typical
 * multiplier. Always finite and > 0. Returns exactly 1 when nothing is set, so
 * `value x quantityFactor(m)` equals the raw value (zero behaviour change).
 */
export function quantityFactor(m: Measurement): number {
  const slope = m.type === 'area' ? normalizeSlopeFactor(m.slopeFactor) : 1;
  const waste = 1 + normalizeWastagePct(m.wastagePct) / 100;
  const mult = normalizeMultiplier(m.multiplier);
  return slope * waste * mult;
}

/**
 * Whether a measurement carries any active quantity adjustment (slope,
 * wastage or multiplier) that makes its reported quantity differ from its raw
 * geometry. Uses a small tolerance so float noise in the slope factor does not
 * read as "adjusted".
 */
export function hasQuantityFactor(m: Measurement): boolean {
  return Math.abs(quantityFactor(m) - 1) > 1e-9;
}

/**
 * Signed reported quantity for a measurement: the raw measured value scaled by
 * {@link quantityFactor}, negated when the measurement is an opening deduction
 * (area void, so net = gross - openings). This is the single source of truth
 * for the figure shown per-row in the ledger, summed into subtotals / grand
 * totals / the legend, written into exports, and pushed to a linked BOQ
 * position - so every surface reports the same number.
 */
export function effectiveQuantity(m: Measurement): number {
  const base = Number.isFinite(m.value) ? m.value : 0;
  const magnitude = base * quantityFactor(m);
  return m.isDeduction ? -magnitude : magnitude;
}

/**
 * The POSITIVE reported quantity (magnitude of {@link effectiveQuantity}),
 * used where a sign makes no sense - above all the linked-BOQ push, since a
 * BOQ position quantity is always positive. Equals the raw value when no
 * factor is set.
 */
export function reportedMagnitude(m: Measurement): number {
  return Math.abs(effectiveQuantity(m));
}

/**
 * A short, human-readable summary of the active adjustments on a measurement,
 * e.g. `"x3"`, `"+10%"`, `"pitch 1.05"`, or a combination `"x3 +10%"`. Empty
 * string when nothing is set. Rendered as a compact badge next to the value in
 * the ledger / sidebar so a reported number that differs from the drawn
 * geometry is never a mystery.
 */
export function quantityAdjustmentLabel(m: Measurement): string {
  const parts: string[] = [];
  const mult = normalizeMultiplier(m.multiplier);
  if (mult !== 1) parts.push(`x${mult}`);
  const waste = normalizeWastagePct(m.wastagePct);
  if (waste > 0) parts.push(`+${Number(waste.toFixed(2))}%`);
  if (m.type === 'area') {
    const slope = normalizeSlopeFactor(m.slopeFactor);
    if (slope !== 1) parts.push(`pitch ${Number(slope.toFixed(3))}`);
  }
  return parts.join(' ');
}

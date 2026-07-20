// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/** Pixel-to-real-world scale conversion helpers */

export interface ScaleConfig {
  /** Pixels per real-world unit (e.g. pixels per meter).
   *  ``0`` denotes an *un-derivable* calibration (bad / missing
   *  reference) — never a silent 1:1 fallback (see {@link deriveScale}).
   *  All consumers (`toRealDistance`, `toRealArea`, `ratioFromScale`)
   *  treat ``<= 0`` as "no scale" and yield 0 / "—" rather than a
   *  grossly inflated reading. */
  pixelsPerUnit: number;
  /** Display unit label */
  unitLabel: string;
  /** ``true`` when the scale could not be derived from the supplied
   *  reference (zero / negative pixel or real length). The viewer uses
   *  this to refuse measurements and re-prompt the user instead of
   *  recording wildly wrong quantities (D-TKC-010). */
  invalid?: boolean;
}

/**
 * PDF base render resolution, in dots per inch.
 *
 * The whole preset-scale maths hinges on this single invariant: stored
 * measurement points are in **PDF user units** (1 pt = 1/72 inch),
 * because the canvas captures `(clientX - rect.left) / zoom` and the
 * canvas CSS width is `pdfWidth * zoom` at base render scale 1.0.
 * Therefore a `1:ratio` paper scale resolves to
 * `PDF_POINTS_PER_INCH / (METERS_PER_INCH * ratio)` pixels per metre.
 *
 * Centralised + named (was a bare `72` inline) so the invariant has
 * exactly one definition and a regression test can pin it (D-TKC-029).
 */
export const PDF_POINTS_PER_INCH = 72;

/** 1 inch in metres — the metric/imperial bridge used by preset scales. */
export const METERS_PER_INCH = 0.0254;

/**
 * Resolve an architectural `1:ratio` paper scale into a {@link ScaleConfig}.
 *
 * Single source of truth for the preset buttons. By definition an
 * architectural ratio maps paper distance to *metric* real-world
 * distance, so the unit label is always metres (imperial drawings are
 * handled by two-click calibration, not paper presets — D-TKC-016).
 */
export function presetScale(ratio: number): ScaleConfig {
  if (!Number.isFinite(ratio) || ratio <= 0) {
    return { pixelsPerUnit: 0, unitLabel: 'm', invalid: true };
  }
  return {
    pixelsPerUnit: PDF_POINTS_PER_INCH / (METERS_PER_INCH * ratio),
    unitLabel: 'm',
  };
}

/** Common architectural scales */
export const COMMON_SCALES: { label: string; ratio: number }[] = [
  { label: '1:10', ratio: 10 },
  { label: '1:20', ratio: 20 },
  { label: '1:25', ratio: 25 },
  { label: '1:48', ratio: 48 },
  { label: '1:50', ratio: 50 },
  { label: '1:75', ratio: 75 },
  { label: '1:100', ratio: 100 },
  { label: '1:200', ratio: 200 },
  { label: '1:500', ratio: 500 },
  { label: '1:1000', ratio: 1000 },
];

/** Calculate distance between two points in pixels */
export function pixelDistance(
  x1: number,
  y1: number,
  x2: number,
  y2: number,
): number {
  return Math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2);
}

/** Convert pixel distance to real-world distance */
export function toRealDistance(
  pixelDist: number,
  scale: ScaleConfig,
): number {
  if (scale.pixelsPerUnit <= 0) return 0;
  return pixelDist / scale.pixelsPerUnit;
}

/** Calculate area of a polygon (using shoelace formula) in pixel units */
export function polygonAreaPixels(points: { x: number; y: number }[]): number {
  if (points.length < 3) return 0;
  let area = 0;
  for (let i = 0; i < points.length; i++) {
    const j = (i + 1) % points.length;
    const pi = points[i]!;
    const pj = points[j]!;
    area += pi.x * pj.y;
    area -= pj.x * pi.y;
  }
  return Math.abs(area) / 2;
}

/** Convert pixel area to real-world area */
export function toRealArea(
  pixelArea: number,
  scale: ScaleConfig,
): number {
  if (scale.pixelsPerUnit <= 0) return 0;
  return pixelArea / (scale.pixelsPerUnit ** 2);
}

/** Calculate perimeter of a polygon in pixels */
export function polygonPerimeterPixels(
  points: { x: number; y: number }[],
): number {
  if (points.length < 2) return 0;
  let perimeter = 0;
  for (let i = 0; i < points.length; i++) {
    const j = (i + 1) % points.length;
    const pi = points[i]!;
    const pj = points[j]!;
    perimeter += pixelDistance(pi.x, pi.y, pj.x, pj.y);
  }
  return perimeter;
}

/** Format a measurement value with appropriate precision.
 *
 *  Only genuinely degenerate values (non-finite, zero, negative) render
 *  as the empty string — those come from half-finished polygons /
 *  two-identical-points and would otherwise litter the panel with a
 *  misleading "0 m²".  Real but *small* quantities (a 9 mm joint, an
 *  80 cm² patch) must stay visible with enough significant digits
 *  rather than being collapsed to zero or hidden (D-TKC-007): an
 *  estimator measuring small details still needs to read the number. */
export function formatMeasurement(value: number, unit: string): string {
  if (!Number.isFinite(value) || value <= 0) return '';
  if (value < 0.001) return `${value.toPrecision(2)} ${unit}`;
  if (value < 1) return `${value.toFixed(4)} ${unit}`;
  if (value < 100) return `${value.toFixed(2)} ${unit}`;
  return `${value.toFixed(1)} ${unit}`;
}

/** Derive scale from a known reference measurement.
 *  pixelLength = measured pixel distance on drawing
 *  realLength  = known real-world length **in metres**
 *
 *  METRIC-CANONICAL CONTRACT (D-TKC-016): the returned `unitLabel` is
 *  always `'m'` and `pixelsPerUnit` is always pixels-per-metre, even when
 *  the estimator calibrated using feet or inches. `CalibrationDialog`
 *  converts the user's ft/in entry to metres via `toMeters()` *before*
 *  calling this, so every downstream consumer (`presetScale`,
 *  `ratioFromScale`, the recalc effect, persisted measurements) can rely
 *  on a single unit system. The estimator's original unit is **not lost**:
 *  it is surfaced separately on the calibration badge / dialog note so a
 *  feet calibration is no longer silently relabelled as metres.
 */
export function deriveScale(
  pixelLength: number,
  realLength: number,
): ScaleConfig {
  if (
    !Number.isFinite(realLength) ||
    !Number.isFinite(pixelLength) ||
    realLength <= 0 ||
    pixelLength <= 0
  ) {
    // Do NOT fall back to a silent 1 px = 1 m: that turned a 28 346 px
    // line into "28 346 m" with no indication. Return an explicitly
    // invalid scale so downstream maths yields nothing and the viewer
    // forces the user to recalibrate (D-TKC-010).
    return { pixelsPerUnit: 0, unitLabel: 'm', invalid: true };
  }
  return {
    pixelsPerUnit: pixelLength / realLength,
    unitLabel: 'm',
  };
}

/** Calibration units supported by the two-click calibration dialog. */
export type CalibrationUnit = 'm' | 'mm' | 'ft' | 'in';

/** Conversion factors from each supported calibration unit to meters. */
export const UNIT_TO_METERS: Readonly<Record<CalibrationUnit, number>> = {
  m: 1,
  mm: 0.001,
  ft: 0.3048,
  in: 0.0254,
};

/** Convert a real-world length given in `unit` into meters. */
export function toMeters(value: number, unit: CalibrationUnit): number {
  return value * (UNIT_TO_METERS[unit] ?? 1);
}

/** Convert meters back into the supplied display unit. */
export function fromMeters(meters: number, unit: CalibrationUnit): number {
  const factor = UNIT_TO_METERS[unit] ?? 1;
  if (factor === 0) return meters;
  return meters / factor;
}

/**
 * Derive a canonical `1:N` architectural scale ratio from a calibrated
 * `pixelsPerUnit` value, assuming the drawing is rendered at the common
 * 72dpi PDF base resolution (matching the inverse logic used by the
 * preset buttons: `pixelsPerUnit = 72 / (0.0254 * ratio)`).
 *
 * Returns the nearest integer ratio, clamped to sensible bounds.
 */
export function ratioFromScale(scale: ScaleConfig): number {
  if (scale.pixelsPerUnit <= 0) return 0;
  // ppu = PPI / (M_PER_IN * ratio)  →  ratio = PPI / (ppu * M_PER_IN)
  // Same invariant as presetScale(), inverted — kept single-sourced.
  const raw = PDF_POINTS_PER_INCH / (scale.pixelsPerUnit * METERS_PER_INCH);
  return Math.max(1, Math.round(raw));
}

/** Format a derived scale as "1:50" for a status badge. */
export function formatScaleRatio(scale: ScaleConfig): string {
  const ratio = ratioFromScale(scale);
  return ratio > 0 ? `1:${ratio}` : '—';
}

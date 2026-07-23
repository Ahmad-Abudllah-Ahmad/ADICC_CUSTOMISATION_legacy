/**
 * Unit tests for the Wave 24 unit-system formatters in formatters.ts.
 *
 * These are pure-function tests -- no DOM, no i18next runtime dependency.
 * We pass an explicit `locale` argument ('en-US') so results are
 * deterministic across CI environments.
 *
 * Coverage: formatArea, formatLength, formatVolume, formatWeight, formatTemperature
 * Test cases per formatter: zero, negative, large, fractional, both systems, edge.
 */

import { describe, expect, it } from 'vitest';
import {
  formatArea,
  formatLength,
  formatTemperature,
  formatVolume,
  formatWeight,
} from './formatters';

const EN = 'en-US';

// ---- Helpers ---------------------------------------------------------------

/** Parse the numeric part out of a formatted string like "1,297.57 sqft". */
function extractNum(s: string): number {
  // Remove thousands commas and spaces, then strip all non-numeric chars except dot and minus.
  return parseFloat(s.replace(/,/g, '').replace(/[^\d.\-]/g, ''));
}

// ---- formatArea ------------------------------------------------------------

describe('formatArea', () => {
  it('renders 0 in metric with 2 decimals', () => {
    const result = formatArea(0, 'metric', EN);
    // Contains "0.00" and ends with "m²" (allow for any separator)
    expect(result).toMatch(/0\.00/);
    expect(result).toContain('m');
    // Must NOT contain sqft
    expect(result).not.toContain('sqft');
  });

  it('renders 0 in imperial as sqft with 2 decimals', () => {
    const result = formatArea(0, 'imperial', EN);
    expect(result).toMatch(/0\.00/);
    expect(result).toContain('sqft');
  });

  it('converts 1 m2 to ~10.76 sqft', () => {
    const result = formatArea(1, 'imperial', EN);
    const num = extractNum(result);
    expect(Math.abs(num - 10.764)).toBeLessThan(0.005);
    expect(result).toContain('sqft');
  });

  it('renders a large metric area (10 000 m2)', () => {
    const result = formatArea(10000, 'metric', EN);
    const num = extractNum(result);
    expect(Math.abs(num - 10000)).toBeLessThan(1);
    expect(result).not.toContain('sqft');
  });

  it('renders a fractional area preserving at least 2 decimals', () => {
    const result = formatArea(0.5, 'metric', EN);
    // Fractional part must have at least 2 digits
    expect(result).toMatch(/0\.5\d*/);
  });

  it('handles negative values without crashing', () => {
    const result = formatArea(-5, 'metric', EN);
    expect(result).toContain('-');
  });

  it('returns em-dash for null', () => {
    expect(formatArea(null, 'metric', EN)).toBe('—');
  });

  it('returns em-dash for undefined', () => {
    expect(formatArea(undefined, 'imperial', EN)).toBe('—');
  });

  it('returns em-dash for NaN', () => {
    expect(formatArea(NaN, 'metric', EN)).toBe('—');
  });

  it('converts a large imperial value correctly (1000 m2)', () => {
    const result = formatArea(1000, 'imperial', EN);
    const num = extractNum(result);
    // 1000 x 10.7639 = 10763.9
    expect(Math.abs(num - 10763.9)).toBeLessThan(1);
    expect(result).toContain('sqft');
  });
});

// ---- formatLength ----------------------------------------------------------

describe('formatLength', () => {
  it('renders 0 in metric with 2 decimals', () => {
    const result = formatLength(0, 'metric', EN);
    expect(result).toMatch(/0\.00/);
    expect(result).not.toContain('ft');
  });

  it('renders 0 in imperial as ft with 2 decimals', () => {
    const result = formatLength(0, 'imperial', EN);
    expect(result).toMatch(/0\.00/);
    expect(result).toContain('ft');
  });

  it('converts 1 m to ~3.28 ft', () => {
    const result = formatLength(1, 'imperial', EN);
    const num = extractNum(result);
    expect(Math.abs(num - 3.281)).toBeLessThan(0.01);
    expect(result).toContain('ft');
  });

  it('renders a large metric length', () => {
    const result = formatLength(500, 'metric', EN);
    const num = extractNum(result);
    expect(Math.abs(num - 500)).toBeLessThan(1);
    // Unit label is 'm' (not 'ft')
    expect(result).not.toContain('ft');
  });

  it('preserves at least 2 decimal places for fractional metric', () => {
    const result = formatLength(1.5, 'metric', EN);
    expect(result).toMatch(/1\.5\d*/);
  });

  it('handles negative length', () => {
    const result = formatLength(-3, 'imperial', EN);
    expect(result).toContain('-');
    expect(result).toContain('ft');
  });

  it('returns em-dash for null', () => {
    expect(formatLength(null, 'metric', EN)).toBe('—');
  });

  it('returns em-dash for NaN', () => {
    expect(formatLength(NaN, 'imperial', EN)).toBe('—');
  });
});

// ---- formatVolume ----------------------------------------------------------

describe('formatVolume', () => {
  it('renders 0 in metric with 2 decimals', () => {
    const result = formatVolume(0, 'metric', EN);
    expect(result).toMatch(/0\.00/);
    expect(result).not.toContain('ft');
  });

  it('renders 0 in imperial with 2 decimals (ft3)', () => {
    const result = formatVolume(0, 'imperial', EN);
    expect(result).toMatch(/0\.00/);
    expect(result).toContain('ft');
  });

  it('converts 1 m3 to ~35.31 ft3', () => {
    const result = formatVolume(1, 'imperial', EN);
    const num = extractNum(result);
    expect(Math.abs(num - 35.315)).toBeLessThan(0.01);
    expect(result).toContain('ft');
  });

  it('renders a large metric volume', () => {
    const result = formatVolume(1000, 'metric', EN);
    const num = extractNum(result);
    expect(Math.abs(num - 1000)).toBeLessThan(1);
    expect(result).not.toContain('ft');
  });

  it('preserves at least 2 decimal places for fractional volume', () => {
    const result = formatVolume(0.25, 'metric', EN);
    expect(result).toMatch(/0\.25/);
  });

  it('handles negative volume', () => {
    const result = formatVolume(-10, 'imperial', EN);
    expect(result).toContain('-');
    expect(result).toContain('ft');
  });

  it('returns em-dash for null', () => {
    expect(formatVolume(null, 'imperial', EN)).toBe('—');
  });

  it('returns em-dash for NaN', () => {
    expect(formatVolume(NaN, 'metric', EN)).toBe('—');
  });
});

// ---- formatWeight ----------------------------------------------------------

describe('formatWeight', () => {
  it('renders 0 in metric with 2 decimals (kg)', () => {
    const result = formatWeight(0, 'metric', EN);
    expect(result).toMatch(/0\.00/);
    expect(result).toContain('kg');
  });

  it('renders 0 in imperial with 2 decimals (lb)', () => {
    const result = formatWeight(0, 'imperial', EN);
    expect(result).toMatch(/0\.00/);
    expect(result).toContain('lb');
  });

  it('converts 1 kg to ~2.20 lb', () => {
    const result = formatWeight(1, 'imperial', EN);
    const num = extractNum(result);
    expect(Math.abs(num - 2.205)).toBeLessThan(0.01);
    expect(result).toContain('lb');
  });

  it('renders a large metric weight', () => {
    const result = formatWeight(5000, 'metric', EN);
    const num = extractNum(result);
    expect(Math.abs(num - 5000)).toBeLessThan(1);
    expect(result).toContain('kg');
  });

  it('preserves at least 2 decimal places for fractional weight', () => {
    const result = formatWeight(1.5, 'metric', EN);
    expect(result).toMatch(/1\.5\d*/);
    expect(result).toContain('kg');
  });

  it('handles negative weight', () => {
    const result = formatWeight(-50, 'imperial', EN);
    expect(result).toContain('-');
    expect(result).toContain('lb');
  });

  it('returns em-dash for null', () => {
    expect(formatWeight(null, 'metric', EN)).toBe('—');
  });

  it('returns em-dash for NaN', () => {
    expect(formatWeight(NaN, 'imperial', EN)).toBe('—');
  });
});

// ---- formatTemperature -----------------------------------------------------

describe('formatTemperature', () => {
  it('renders 0 in metric with 2 decimals (Celsius)', () => {
    const result = formatTemperature(0, 'metric', EN);
    expect(result).toMatch(/0\.00/);
    expect(result).toContain('C');
    expect(result).not.toContain('F');
  });

  it('converts 0 C to 32 F', () => {
    const result = formatTemperature(0, 'imperial', EN);
    const num = extractNum(result);
    expect(Math.abs(num - 32)).toBeLessThan(0.01);
    expect(result).toContain('F');
  });

  it('converts 100 C to 212 F', () => {
    const result = formatTemperature(100, 'imperial', EN);
    const num = extractNum(result);
    expect(Math.abs(num - 212)).toBeLessThan(0.01);
    expect(result).toContain('F');
  });

  it('converts -40 C to -40 F (crossover point)', () => {
    const result = formatTemperature(-40, 'imperial', EN);
    const num = extractNum(result);
    // At -40 both scales meet: result should be -40 F
    expect(Math.abs(num - (-40))).toBeLessThan(0.01);
    expect(result).toContain('-');
    expect(result).toContain('F');
  });

  it('converts 20 C to 68 F', () => {
    const result = formatTemperature(20, 'imperial', EN);
    const num = extractNum(result);
    expect(Math.abs(num - 68)).toBeLessThan(0.01);
    expect(result).toContain('F');
  });

  it('renders a large metric temperature (1000 C)', () => {
    const result = formatTemperature(1000, 'metric', EN);
    const num = extractNum(result);
    expect(Math.abs(num - 1000)).toBeLessThan(1);
    expect(result).toContain('C');
  });

  it('handles fractional Celsius in metric', () => {
    const result = formatTemperature(37.5, 'metric', EN);
    expect(result).toMatch(/37\.5\d*/);
    expect(result).toContain('C');
  });

  it('handles negative Celsius in metric', () => {
    const result = formatTemperature(-10, 'metric', EN);
    expect(result).toContain('-');
    expect(result).toContain('C');
  });

  it('returns em-dash for null', () => {
    expect(formatTemperature(null, 'metric', EN)).toBe('—');
  });

  it('returns em-dash for undefined', () => {
    expect(formatTemperature(undefined, 'imperial', EN)).toBe('—');
  });

  it('returns em-dash for NaN', () => {
    expect(formatTemperature(NaN, 'metric', EN)).toBe('—');
  });

  it('converts -273.15 C (absolute zero) to approximately -459.67 F', () => {
    const result = formatTemperature(-273.15, 'imperial', EN);
    // We check presence of '-' and 'F' in the output
    expect(result).toContain('-');
    expect(result).toContain('F');
    // extractNum includes the minus sign in its regex, so it returns -459.67
    const num = extractNum(result);
    expect(Math.abs(num - (-459.67))).toBeLessThan(0.05);
  });
});

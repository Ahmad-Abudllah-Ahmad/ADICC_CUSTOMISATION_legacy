// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
/**
 * Unit tests for the AnchorDriftIndicator's detection heuristic.
 */

import { describe, expect, it } from 'vitest';

import { detectDrift } from '../AnchorDriftIndicator';

describe('detectDrift', () => {
  it('returns false when both sides match', () => {
    expect(
      detectDrift(
        'Hauptstraße 12, 10115 Berlin, Germany',
        'Hauptstraße 12, 10115 Berlin, Germany',
      ),
    ).toBe(false);
  });
  it('returns false for case-only differences', () => {
    expect(
      detectDrift(
        'HAUPTSTRASSE 12, BERLIN, GERMANY',
        'Hauptstrasse 12, Berlin, Germany',
      ),
    ).toBe(false);
  });
  it('returns false when one is a substring of the other', () => {
    expect(
      detectDrift(
        'Berlin, Germany',
        'Hauptstraße 12, 10115 Berlin, Germany',
      ),
    ).toBe(false);
  });
  it('returns true when most tokens differ', () => {
    expect(
      detectDrift(
        'Champs-Élysées, Paris, France',
        'Hauptstraße 12, Berlin, Germany',
      ),
    ).toBe(true);
  });
  it('returns false when either side is missing', () => {
    expect(detectDrift(null, 'Berlin')).toBe(false);
    expect(detectDrift('Berlin', null)).toBe(false);
    expect(detectDrift(null, null)).toBe(false);
  });
});

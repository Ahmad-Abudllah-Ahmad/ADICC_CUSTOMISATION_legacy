// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
/**
 * Regression suite for GitHub issue #122
 * ("p.data.filter is not a function" on /match-elements).
 *
 * If unwrapCataloguesPayload ever stops handling either of the two
 * historical response shapes, /match-elements breaks for any user whose
 * react-query cache was populated by the *other* shape — exactly the
 * regression the original bug report describes.
 *
 * Keep these cases pinned. New shape variants must be added here BEFORE
 * the consumer code learns to read them.
 */

import { describe, it, expect } from 'vitest';
import {
  unwrapCataloguesPayload,
  type CataloguesPayloadCatalogue,
} from '../catalogues-payload';

const sample: CataloguesPayloadCatalogue = {
  region: 'AE_DUBAI',
  language: 'ar',
  install_status: 'available',
  size_mb: 415,
  country_iso: 'AE',
};

describe('unwrapCataloguesPayload (issue #122 regression)', () => {
  it('returns the bare array unchanged', () => {
    const out = unwrapCataloguesPayload([sample]);
    expect(Array.isArray(out)).toBe(true);
    expect(out).toHaveLength(1);
    expect(out[0]?.region).toBe('AE_DUBAI');
  });

  it('unwraps the legacy `{catalogues:[…]}` envelope', () => {
    const out = unwrapCataloguesPayload({ catalogues: [sample] });
    expect(Array.isArray(out)).toBe(true);
    expect(out[0]?.region).toBe('AE_DUBAI');
  });

  it('returns [] for undefined (initial loading state)', () => {
    expect(unwrapCataloguesPayload(undefined)).toEqual([]);
  });

  it('returns [] for null (defensive)', () => {
    expect(unwrapCataloguesPayload(null)).toEqual([]);
  });

  it('returns [] for an object missing `catalogues`', () => {
    // The exact shape that triggered the v2.9.39 crash: a non-array
    // payload reaching `.filter()`. This was the original failure mode in
    // issue #122 — a stale cache entry shaped `{ server: {...} }` from a
    // mid-development build that returned the envelope without the
    // catalogues key for unauthenticated requests.
    const out = unwrapCataloguesPayload({ server: { reachable: false } } as never);
    expect(out).toEqual([]);
  });

  it('returns [] when `catalogues` is itself a non-array', () => {
    const out = unwrapCataloguesPayload({ catalogues: 'not-an-array' as never });
    expect(out).toEqual([]);
  });

  it('result is always safe to call .filter on (the actual issue)', () => {
    // The crash was `p.data.filter is not a function`. This assertion
    // mirrors the consumer code path: feed every shape variant into the
    // helper and verify the result supports the Array.prototype.filter
    // call that originally exploded.
    const variants: unknown[] = [
      undefined,
      null,
      [],
      [sample],
      { catalogues: [sample] },
      { server: {} },
      { catalogues: 42 },
      'not-an-object',
      42,
    ];
    for (const v of variants) {
      const list = unwrapCataloguesPayload(v as never);
      expect(typeof list.filter).toBe('function');
      // .filter() must not throw, regardless of input shape
      expect(() => list.filter((c) => c.install_status === 'available')).not.toThrow();
    }
  });
});

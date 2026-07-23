// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Unit tests for the 360-panorama gating + URL helpers.
 *
 * Pure logic only - no three.js, no DOM. Asserts that the spherical viewer is
 * offered only for flagged photos that actually have a source URL, and that
 * the sphere is always textured with the full-resolution image.
 */
import { describe, expect, it } from 'vitest';

import {
  is360Photo,
  panoramaImageUrl,
  type Panorama360Photo,
} from './panorama360';

describe('is360Photo', () => {
  it('is true for a flagged photo with a file_url', () => {
    expect(
      is360Photo({ is_360: true, file_url: '/files/site/sphere.jpg' }),
    ).toBe(true);
  });

  it('is false when is_360 is false', () => {
    expect(
      is360Photo({ is_360: false, file_url: '/files/site/flat.jpg' }),
    ).toBe(false);
  });

  it('is false when is_360 is missing/undefined', () => {
    expect(is360Photo({ file_url: '/files/site/flat.jpg' })).toBe(false);
  });

  it('is false when flagged but the file_url is absent', () => {
    expect(is360Photo({ is_360: true })).toBe(false);
    expect(is360Photo({ is_360: true, file_url: null })).toBe(false);
  });

  it('is false when flagged but the file_url is blank/whitespace', () => {
    expect(is360Photo({ is_360: true, file_url: '' })).toBe(false);
    expect(is360Photo({ is_360: true, file_url: '   ' })).toBe(false);
  });

  it('does not treat a truthy non-true value as 360', () => {
    // Guards against a sloppy ``if (photo.is_360)`` that would accept 1/"true".
    const sneaky = { is_360: 1, file_url: '/x.jpg' } as unknown as Panorama360Photo;
    expect(is360Photo(sneaky)).toBe(false);
  });

  it('is false for null / undefined input', () => {
    expect(is360Photo(null)).toBe(false);
    expect(is360Photo(undefined)).toBe(false);
  });
});

describe('panoramaImageUrl', () => {
  it('returns the trimmed full-resolution file_url', () => {
    expect(
      panoramaImageUrl({ file_url: '  /files/site/sphere.jpg  ' }),
    ).toBe('/files/site/sphere.jpg');
  });

  it('prefers file_url even when a thumbnail exists (sphere needs full res)', () => {
    expect(
      panoramaImageUrl({
        file_url: '/files/full.jpg',
        thumbnail_url: '/files/thumb.jpg',
      }),
    ).toBe('/files/full.jpg');
  });

  it('returns null when there is no usable file_url', () => {
    expect(panoramaImageUrl({ thumbnail_url: '/files/thumb.jpg' })).toBeNull();
    expect(panoramaImageUrl({ file_url: '' })).toBeNull();
    expect(panoramaImageUrl({ file_url: '   ' })).toBeNull();
    expect(panoramaImageUrl({ file_url: null })).toBeNull();
    expect(panoramaImageUrl(null)).toBeNull();
    expect(panoramaImageUrl(undefined)).toBeNull();
  });

  it('passes an absolute http(s) URL through unchanged', () => {
    expect(
      panoramaImageUrl({ file_url: 'https://cdn.example.com/p.jpg' }),
    ).toBe('https://cdn.example.com/p.jpg');
  });
});

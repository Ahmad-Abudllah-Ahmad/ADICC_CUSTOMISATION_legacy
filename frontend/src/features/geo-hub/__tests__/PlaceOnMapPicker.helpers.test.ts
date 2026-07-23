// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { describe, it, expect } from 'vitest';

import { isPdfDocument, overlayCentroid } from '../PlaceOnMapPicker';
import type { DocumentItem } from '@/features/documents/api';

// Regression guard for the "Place on map" picker crash:
// "Cannot read properties of undefined (reading 'toLowerCase')".
//
// The picker used to read a `filename` field that the CDE document API
// does not return (it returns `name`), so isPdfDocument dereferenced an
// undefined value and the whole geo page threw on modal open. These tests
// pin the classification down to the real `name`/`mime_type` fields and,
// crucially, that a missing name never throws.

const doc = (over: Partial<DocumentItem>): DocumentItem => ({ ...over } as DocumentItem);

describe('isPdfDocument', () => {
  it('classifies by .pdf name extension', () => {
    expect(isPdfDocument(doc({ name: 'A_book_of_house_plans.pdf' }))).toBe(true);
  });

  it('is case-insensitive on the extension', () => {
    expect(isPdfDocument(doc({ name: 'PLAN.PDF' }))).toBe(true);
  });

  it('classifies by application/pdf mime type even without a .pdf name', () => {
    expect(isPdfDocument(doc({ name: 'drawing', mime_type: 'application/pdf' }))).toBe(true);
  });

  it('is case-insensitive on the mime type', () => {
    expect(isPdfDocument(doc({ name: 'drawing', mime_type: 'APPLICATION/PDF' }))).toBe(true);
  });

  it('rejects non-PDF documents (e.g. CAD models)', () => {
    expect(isPdfDocument(doc({ name: 'tower.rvt', mime_type: 'application/octet-stream' }))).toBe(
      false,
    );
  });

  it('does not throw when name is undefined (the original crash)', () => {
    expect(() => isPdfDocument(doc({ name: undefined as unknown as string }))).not.toThrow();
    expect(isPdfDocument(doc({ name: undefined as unknown as string }))).toBe(false);
  });

  it('does not throw on a bare document object', () => {
    expect(() => isPdfDocument({} as DocumentItem)).not.toThrow();
    expect(isPdfDocument({} as DocumentItem)).toBe(false);
  });
});

// The picker flies the camera to a freshly-placed PDF overlay's centroid so
// the user sees the drawing immediately instead of an off-screen square. The
// centroid must be the mean of the four corners and must degrade to null on
// bad input (the parent then skips the fly rather than flying to NaN).
describe('overlayCentroid', () => {
  it('averages four [lon, lat] corners', () => {
    const corners: [number, number][] = [
      [10, 50],
      [12, 50],
      [12, 48],
      [10, 48],
    ];
    expect(overlayCentroid(corners)).toEqual({ lon: 11, lat: 49 });
  });

  it('ignores malformed corner entries', () => {
    const corners = [
      [10, 50],
      [12, 50],
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      [Number.NaN, 48] as any,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ['bad'] as any,
    ];
    expect(overlayCentroid(corners)).toEqual({ lon: 11, lat: 50 });
  });

  it('returns null for empty / missing corners', () => {
    expect(overlayCentroid([])).toBeNull();
    expect(overlayCentroid(null)).toBeNull();
    expect(overlayCentroid(undefined)).toBeNull();
  });

  it('returns null when every corner is non-finite', () => {
    const corners = [
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      [Number.NaN, Number.NaN] as any,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      [Number.POSITIVE_INFINITY, 1] as any,
    ];
    expect(overlayCentroid(corners)).toBeNull();
  });
});

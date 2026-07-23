// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Pure-function tests for the field-tag helpers behind FieldImageToggle
 * (#284 follow-up). The "field" tag is the canonical signal that opts a
 * general image document INTO the project Photo strip; these guards keep
 * the toggle idempotent and case-insensitive.
 */
import { describe, it, expect } from 'vitest';
import { FIELD_TAG, hasFieldTag, nextFieldTags } from '../FieldImageToggle';

describe('hasFieldTag', () => {
  it('detects the field tag regardless of case', () => {
    expect(hasFieldTag(['field'])).toBe(true);
    expect(hasFieldTag(['Field'])).toBe(true);
    expect(hasFieldTag(['FIELD', 'elevation'])).toBe(true);
  });

  it('is false for missing / unrelated tags and nullish input', () => {
    expect(hasFieldTag([])).toBe(false);
    expect(hasFieldTag(['marketing'])).toBe(false);
    expect(hasFieldTag(null)).toBe(false);
    expect(hasFieldTag(undefined)).toBe(false);
  });
});

describe('nextFieldTags', () => {
  it('adds the field tag, preserving existing tags', () => {
    expect(nextFieldTags(['elevation'], true)).toEqual(['elevation', FIELD_TAG]);
  });

  it('is idempotent when adding to an already-field image', () => {
    expect(nextFieldTags(['field', 'rebar'], true)).toEqual(['field', 'rebar']);
  });

  it('removes every case-variant of the field tag', () => {
    expect(nextFieldTags(['Field', 'rebar', 'FIELD'], false)).toEqual(['rebar']);
  });

  it('handles nullish input without throwing', () => {
    expect(nextFieldTags(null, true)).toEqual([FIELD_TAG]);
    expect(nextFieldTags(undefined, false)).toEqual([]);
  });
});

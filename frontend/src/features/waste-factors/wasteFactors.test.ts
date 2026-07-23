// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
// Unit tests for the pure waste-factor helpers. No DOM / network needed - they
// exercise the parsing and display helpers the page relies on, keeping every
// quantity and factor an exact string (never float math).
import { describe, it, expect } from 'vitest';

import { parseApplyInput, trimQty } from './api';

describe('parseApplyInput', () => {
  it('parses one "category quantity" pair per line', () => {
    expect(parseApplyInput('concrete 12.5\nrebar 340')).toEqual([
      { category: 'concrete', net_qty: '12.5' },
      { category: 'rebar', net_qty: '340' },
    ]);
  });

  it('keeps multi-word categories, using the last token as the quantity', () => {
    expect(parseApplyInput('structural steel 8')).toEqual([{ category: 'structural steel', net_qty: '8' }]);
  });

  it('splits on commas, semicolons and tabs as well as spaces', () => {
    expect(parseApplyInput('rebar, 340\ntiling;85\nconcrete\t12')).toEqual([
      { category: 'rebar', net_qty: '340' },
      { category: 'tiling', net_qty: '85' },
      { category: 'concrete', net_qty: '12' },
    ]);
  });

  it('keeps the quantity as a raw string, never a float', () => {
    const [line] = parseApplyInput('blockwork 100.0001');
    expect(line?.net_qty).toBe('100.0001');
  });

  it('skips blank lines, lines with no category, and non-numeric quantities', () => {
    expect(parseApplyInput('\n\nconcrete 12\n\ntiling\nrebar abc\n99')).toEqual([
      { category: 'concrete', net_qty: '12' },
    ]);
  });

  it('returns an empty list for empty input', () => {
    expect(parseApplyInput('')).toEqual([]);
    expect(parseApplyInput('   \n  ')).toEqual([]);
  });
});

describe('trimQty', () => {
  it('trims trailing zeros without float math', () => {
    expect(trimQty('12.5000')).toBe('12.5');
    expect(trimQty('1.0000')).toBe('1');
    expect(trimQty('100')).toBe('100');
    expect(trimQty('0.1000')).toBe('0.1');
  });

  it('keeps a value that needs all its digits', () => {
    expect(trimQty('1.2345')).toBe('1.2345');
  });

  it('treats null / empty as zero', () => {
    expect(trimQty('')).toBe('0');
    expect(trimQty(null)).toBe('0');
    expect(trimQty(undefined)).toBe('0');
  });

  it('passes a non-decimal string through unchanged', () => {
    expect(trimQty('n/a')).toBe('n/a');
  });
});

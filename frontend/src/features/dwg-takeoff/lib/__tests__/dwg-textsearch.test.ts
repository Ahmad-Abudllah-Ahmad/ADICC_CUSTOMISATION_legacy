// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { describe, it, expect } from 'vitest';
import { findTextMatches, textBoxForEntity, buildSnippet } from '../dwg-textsearch';
import type { DxfEntity } from '../../api';

function text(id: string, str: string, x: number, y: number, height = 0.5, layer = 'ANNOT'): DxfEntity {
  return { id, type: 'TEXT', layer, color: '#ffffff', start: { x, y }, text: str, height };
}

describe('findTextMatches', () => {
  const entities: DxfEntity[] = [
    text('a', 'ROOM 101', 2, 9),
    text('b', 'ROOM 102', 8, 9),
    text('c', 'OFFICE', 2, 5),
    text('d', 'CORRIDOR', 5, 2),
    { id: 'line', type: 'LINE', layer: 'WALLS', color: 7, start: { x: 0, y: 0 }, end: { x: 1, y: 1 } },
  ];

  it('returns nothing for an empty or whitespace query', () => {
    expect(findTextMatches(entities, '')).toEqual([]);
    expect(findTextMatches(entities, '   ')).toEqual([]);
  });

  it('matches case-insensitively', () => {
    const m = findTextMatches(entities, 'room');
    expect(m.map((x) => x.entityId).sort()).toEqual(['a', 'b']);
  });

  it('returns one match per matching entity', () => {
    const m = findTextMatches(entities, 'O'); // appears in ROOM, OFFICE, CORRIDOR
    expect(m.length).toBe(4);
  });

  it('ignores non-TEXT entities', () => {
    const m = findTextMatches(entities, 'line');
    expect(m).toEqual([]);
  });

  it('ignores TEXT entities missing text or start', () => {
    const broken: DxfEntity[] = [
      { id: 'x', type: 'TEXT', layer: 'ANNOT', color: 7, text: 'HELLO' }, // no start
      { id: 'y', type: 'TEXT', layer: 'ANNOT', color: 7, start: { x: 0, y: 0 } }, // no text
    ];
    expect(findTextMatches(broken, 'hello')).toEqual([]);
  });

  it('orders matches top-to-bottom then left-to-right (reading order)', () => {
    // y: a,b at 9 (top); c at 5; d at 2 (bottom). a.x(2) < b.x(8).
    const m = findTextMatches(entities, 'o');
    expect(m.map((x) => x.entityId)).toEqual(['a', 'b', 'c', 'd']);
    expect(m.map((x) => x.index)).toEqual([0, 1, 2, 3]);
  });

  it('includes a snippet and a centre point', () => {
    const m = findTextMatches([text('a', 'ROOM 101', 2, 9)], 'room');
    expect(m[0]!.snippet).toContain('ROOM 101');
    expect(m[0]!.center.x).toBeGreaterThan(2);
    expect(m[0]!.center.y).toBeGreaterThan(9);
  });
});

describe('textBoxForEntity', () => {
  it('frames a single-line text from its insertion point', () => {
    const box = textBoxForEntity(text('a', 'ABCDE', 10, 20, 1))!;
    expect(box.minX).toBe(10);
    expect(box.minY).toBe(20);
    expect(box.maxX).toBeCloseTo(10 + 1 * 5 * 0.6, 5); // h*len*0.6
    expect(box.maxY).toBeGreaterThan(20);
  });

  it('grows the box height for multi-line text', () => {
    const one = textBoxForEntity(text('a', 'ONE', 0, 0, 1))!;
    const three = textBoxForEntity(text('b', 'ONE\nTWO\nTHREE', 0, 0, 1))!;
    expect(three.maxY).toBeGreaterThan(one.maxY);
    // width driven by the longest line ("THREE" = 5 chars)
    expect(three.maxX).toBeCloseTo(0 + 1 * 5 * 0.6, 5);
  });

  it('returns null for non-text or empty entities', () => {
    expect(textBoxForEntity({ id: 'l', type: 'LINE', layer: 'x', color: 7, start: { x: 0, y: 0 } })).toBeNull();
    expect(textBoxForEntity({ id: 't', type: 'TEXT', layer: 'x', color: 7, text: 'hi' })).toBeNull();
  });
});

describe('buildSnippet', () => {
  it('collapses whitespace and keeps the match', () => {
    expect(buildSnippet('ROOM   101', 0, 4)).toBe('ROOM 101');
  });

  it('adds ellipses when clipped', () => {
    const long = 'x'.repeat(40) + 'TARGET' + 'y'.repeat(40);
    const s = buildSnippet(long, 40, 6);
    expect(s.startsWith('…')).toBe(true);
    expect(s.endsWith('…')).toBe(true);
    expect(s).toContain('TARGET');
  });
});

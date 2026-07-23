// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Unit tests for the architecture map's neighbourhood helper - the math
 * behind "click a node, light up what it connects to".
 */
import { describe, expect, it } from 'vitest';
import { computeNeighborhood, neighborCount, type GraphEdgeRef } from './architectureGraph';

const EDGES: GraphEdgeRef[] = [
  { id: 'e1', source: 'a', target: 'b' },
  { id: 'e2', source: 'a', target: 'c' },
  { id: 'e3', source: 'd', target: 'a' }, // inbound to a
  { id: 'e4', source: 'b', target: 'c' }, // unrelated to a
];

describe('computeNeighborhood', () => {
  it('collects neighbours in both edge directions plus the node itself', () => {
    const n = computeNeighborhood(EDGES, 'a');
    expect([...n.nodeIds].sort()).toEqual(['a', 'b', 'c', 'd']);
  });

  it('collects exactly the edges incident to the active node', () => {
    const n = computeNeighborhood(EDGES, 'a');
    expect([...n.edgeIds].sort()).toEqual(['e1', 'e2', 'e3']);
    // e4 (b->c) does not touch a, so it must stay out.
    expect(n.edgeIds.has('e4')).toBe(false);
  });

  it('always includes the active node even when it has no edges', () => {
    const n = computeNeighborhood(EDGES, 'z');
    expect([...n.nodeIds]).toEqual(['z']);
    expect(n.edgeIds.size).toBe(0);
  });

  it('returns empty sets when nothing is active', () => {
    for (const active of [null, undefined, '']) {
      const n = computeNeighborhood(EDGES, active);
      expect(n.nodeIds.size).toBe(0);
      expect(n.edgeIds.size).toBe(0);
    }
  });

  it('handles a self-loop without double-counting', () => {
    const n = computeNeighborhood([{ id: 'loop', source: 'x', target: 'x' }], 'x');
    expect([...n.nodeIds]).toEqual(['x']);
    expect([...n.edgeIds]).toEqual(['loop']);
  });

  it('is unaffected by duplicate parallel edges beyond their own ids', () => {
    const dup: GraphEdgeRef[] = [
      { id: 'p1', source: 'a', target: 'b' },
      { id: 'p2', source: 'a', target: 'b' },
    ];
    const n = computeNeighborhood(dup, 'a');
    expect([...n.nodeIds].sort()).toEqual(['a', 'b']);
    expect([...n.edgeIds].sort()).toEqual(['p1', 'p2']);
  });
});

describe('neighborCount', () => {
  it('excludes the active node from the connection count', () => {
    expect(neighborCount(computeNeighborhood(EDGES, 'a'))).toBe(3);
  });

  it('is zero for an isolated or empty selection', () => {
    expect(neighborCount(computeNeighborhood(EDGES, 'z'))).toBe(0);
    expect(neighborCount(computeNeighborhood(EDGES, null))).toBe(0);
  });
});

// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
// Unit tests for the BOQ-proposal extractor used by ApplyActionButton (Item 29).
// Pure function — no DOM / router needed.
import { describe, it, expect } from 'vitest';

import { extractPositionProposals } from './ApplyActionButton';

describe('extractPositionProposals', () => {
  it('returns [] for plain markdown text', () => {
    expect(extractPositionProposals('Here is a summary of the work.')).toEqual([]);
  });

  it('returns [] for malformed JSON', () => {
    expect(extractPositionProposals('{ not valid json')).toEqual([]);
  });

  it('parses a single position object', () => {
    const out = extractPositionProposals(
      JSON.stringify({
        kind: 'boq_position_proposal',
        description: 'C30/37 ground slab',
        unit: 'm3',
        qty: 9,
        unit_rate: 120,
        total: 1080,
        currency: 'eur',
      }),
    );
    expect(out).toHaveLength(1);
    expect(out[0]).toMatchObject({
      description: 'C30/37 ground slab',
      unit: 'm3',
      qty: 9,
      unit_rate: 120,
      total: 1080,
      currency: 'EUR',
    });
  });

  it('parses a { positions: [...] } envelope and computes missing totals', () => {
    const out = extractPositionProposals(
      JSON.stringify({
        positions: [
          { description: 'Excavation', unit: 'm3', quantity: 10, rate: 5 },
          { description: 'Hardcore', unit: 'm2', qty: 100, unit_rate: 2, total: 200, currency: 'GBP' },
        ],
      }),
    );
    expect(out).toHaveLength(2);
    // qty/quantity and rate/unit_rate aliases both resolve; total back-filled.
    expect(out[0]).toMatchObject({ description: 'Excavation', qty: 10, unit_rate: 5, total: 50 });
    expect(out[1]!.currency).toBe('GBP');
  });

  it('parses a bare array of positions', () => {
    const out = extractPositionProposals(
      JSON.stringify([{ description: 'Item A', unit: 'pcs', qty: 1, unit_rate: 0 }]),
    );
    expect(out).toHaveLength(1);
  });

  it('ignores entries lacking a description', () => {
    const out = extractPositionProposals(JSON.stringify([{ unit: 'm2', qty: 1 }]));
    expect(out).toEqual([]);
  });
});

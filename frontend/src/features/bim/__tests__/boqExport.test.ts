// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Unit tests for the BOQ-export request mapping helpers.
 *
 * These are the pure bits of the IFC->BOQ Excel export (B6): the network
 * call itself is exercised in the browser, but the scope -> body mapping and
 * the Content-Disposition filename parse are easy to get subtly wrong, so we
 * pin them here.
 */

import { describe, it, expect } from 'vitest';
import { buildBoqExportBody, parseAttachmentFilename } from '../api';

const ctx = (selectedIds: string[], filters: Record<string, string[]> | null) => ({
  selectedIds,
  filters,
});

describe('buildBoqExportBody', () => {
  it('whole-model scope sends neither element_ids nor filters', () => {
    const body = buildBoqExportBody('all', 'element_type', ctx(['a', 'b'], { storey: ['L1'] }));
    expect(body).toEqual({ group_by: 'element_type' });
  });

  it('selected scope sends the picked element ids', () => {
    const body = buildBoqExportBody('selected', 'storey', ctx(['a', 'b'], null));
    expect(body).toEqual({ group_by: 'storey', element_ids: ['a', 'b'] });
  });

  it('selected scope with no selection falls back to whole model (guarded in UI)', () => {
    const body = buildBoqExportBody('selected', 'element_type', ctx([], null));
    expect(body).toEqual({ group_by: 'element_type' });
  });

  it('filter scope sends the active filters', () => {
    const body = buildBoqExportBody(
      'filter',
      'element_type_storey',
      ctx([], { storey: ['L1', 'L2'], element_type: ['IfcWall'] }),
    );
    expect(body).toEqual({
      group_by: 'element_type_storey',
      filters: { storey: ['L1', 'L2'], element_type: ['IfcWall'] },
    });
  });

  it('trims and attaches an optional title', () => {
    const body = buildBoqExportBody('all', 'element_type', ctx([], null), '  Tower A BOQ  ');
    expect(body.title).toBe('Tower A BOQ');
  });

  it('omits an empty title', () => {
    const body = buildBoqExportBody('all', 'element_type', ctx([], null), '   ');
    expect('title' in body).toBe(false);
  });
});

describe('parseAttachmentFilename', () => {
  it('reads a plain filename', () => {
    expect(
      parseAttachmentFilename('attachment; filename="BOQ_Tower_A.xlsx"', 'BOQ.xlsx'),
    ).toBe('BOQ_Tower_A.xlsx');
  });

  it('reads an RFC 5987 filename*', () => {
    expect(
      parseAttachmentFilename(
        "attachment; filename*=UTF-8''BOQ_%D0%91%D0%B0%D1%88%D0%BD%D1%8F.xlsx",
        'BOQ.xlsx',
      ),
    ).toBe('BOQ_Башня.xlsx');
  });

  it('falls back when the header is absent', () => {
    expect(parseAttachmentFilename(null, 'BOQ.xlsx')).toBe('BOQ.xlsx');
  });
});

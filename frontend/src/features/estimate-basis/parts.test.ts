// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
import { describe, expect, it } from 'vitest';
import type { EstimateBasisDocument, QualificationItem } from './api';
import {
  basisFilename,
  enabledItems,
  newManualItem,
  renderBasisMarkdown,
  type MarkdownLabels,
} from './parts';

const LABELS: MarkdownLabels = {
  inclusions: 'Inclusions',
  exclusions: 'Exclusions',
  assumptions: 'Assumptions',
  notes: 'Notes',
  none: 'None.',
  status: 'Status',
  generated: 'Generated',
};

function item(over: Partial<QualificationItem>): QualificationItem {
  return {
    id: 'x',
    category: 'inclusion',
    text: 'text',
    trade_code: null,
    trade_label: null,
    basis: '',
    source: 'auto',
    enabled: true,
    ...over,
  };
}

function doc(over: Partial<EstimateBasisDocument>): EstimateBasisDocument {
  return {
    id: 'd1',
    project_id: 'p1',
    boq_id: null,
    title: 'Basis of estimate',
    status: 'draft',
    notes: '',
    inclusions: [],
    exclusions: [],
    assumptions: [],
    coverage: {
      present_trades: [],
      absent_trades: [],
      total_positions: 0,
      classified_positions: 0,
      unclassified_positions: 0,
      zero_rate_positions: 0,
      missing_quantity_positions: 0,
      provisional_positions: 0,
      by_others_positions: 0,
    },
    generated_at: null,
    created_at: null,
    updated_at: null,
    ...over,
  };
}

describe('enabledItems', () => {
  it('keeps only enabled lines', () => {
    const items = [item({ id: 'a' }), item({ id: 'b', enabled: false })];
    expect(enabledItems(items).map((i) => i.id)).toEqual(['a']);
  });
});

describe('renderBasisMarkdown', () => {
  it('renders the title, sections and only enabled lines', () => {
    const md = renderBasisMarkdown(
      doc({
        title: 'Tower A - Basis',
        inclusions: [item({ text: 'Building works included' })],
        exclusions: [
          item({ category: 'exclusion', text: 'VAT excluded' }),
          item({ category: 'exclusion', text: 'Hidden line', enabled: false }),
        ],
      }),
      LABELS,
    );
    expect(md).toContain('# Tower A - Basis');
    expect(md).toContain('## Inclusions');
    expect(md).toContain('- Building works included');
    expect(md).toContain('- VAT excluded');
    expect(md).not.toContain('Hidden line');
    // An empty section still renders with a "none" placeholder.
    expect(md).toContain('## Assumptions');
    expect(md).toContain('None.');
    // Trailing newline, single.
    expect(md.endsWith('\n')).toBe(true);
    expect(md.endsWith('\n\n')).toBe(false);
  });

  it('includes the notes section only when notes are present', () => {
    expect(renderBasisMarkdown(doc({ notes: '' }), LABELS)).not.toContain('## Notes');
    const withNotes = renderBasisMarkdown(doc({ notes: 'Client to confirm scope.' }), LABELS);
    expect(withNotes).toContain('## Notes');
    expect(withNotes).toContain('Client to confirm scope.');
  });

  it('weaves the generated timestamp into the meta line when set', () => {
    const md = renderBasisMarkdown(doc({ generated_at: '2026-07-08T10:00:00+00:00' }), LABELS);
    expect(md).toContain('Generated: 2026-07-08T10:00:00+00:00');
    expect(md).toContain('Status: draft');
  });
});

describe('basisFilename', () => {
  it('sanitises the title into a safe .md name', () => {
    expect(basisFilename('Tower A / Phase 1')).toBe('basis_of_estimate_Tower_A_-_Phase_1.md');
  });

  it('falls back when the title is empty', () => {
    expect(basisFilename('')).toBe('basis_of_estimate_document.md');
    expect(basisFilename('   ')).toBe('basis_of_estimate_document.md');
  });
});

describe('newManualItem', () => {
  it('creates a blank, enabled, manual line in the given category', () => {
    const it2 = newManualItem('exclusion', 'manual-123');
    expect(it2).toEqual({
      id: 'manual-123',
      category: 'exclusion',
      text: '',
      trade_code: null,
      trade_label: null,
      basis: 'manual',
      source: 'manual',
      enabled: true,
    });
  });
});

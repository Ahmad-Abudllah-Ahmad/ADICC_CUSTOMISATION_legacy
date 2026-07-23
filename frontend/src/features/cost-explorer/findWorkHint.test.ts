// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
import { describe, expect, it } from 'vitest';
import { DID_YOU_MEAN_CODE, selectFindWorkHint } from './findWorkHint';

describe('selectFindWorkHint', () => {
  it('returns null when there is no response or no hint', () => {
    expect(selectFindWorkHint(undefined)).toBeNull();
    expect(selectFindWorkHint(null)).toBeNull();
    expect(selectFindWorkHint({ hint: null, hint_code: null })).toBeNull();
    expect(selectFindWorkHint({ hint: '   ', hint_code: DID_YOU_MEAN_CODE })).toBeNull();
  });

  it('surfaces a spelling suggestion as a chip carrying the corrected query', () => {
    const out = selectFindWorkHint({ hint: 'concrete', hint_code: DID_YOU_MEAN_CODE });
    expect(out).toEqual({ kind: 'suggestion', suggestion: 'concrete' });
  });

  it('hides the suggestion once it has been dismissed', () => {
    const res = { hint: 'concrete', hint_code: DID_YOU_MEAN_CODE };
    expect(selectFindWorkHint(res, 'concrete')).toBeNull();
    // A different (new) suggestion still shows even after an earlier dismissal.
    expect(selectFindWorkHint({ hint: 'screed', hint_code: DID_YOU_MEAN_CODE }, 'concrete')).toEqual({
      kind: 'suggestion',
      suggestion: 'screed',
    });
  });

  it('passes a no-result / low-confidence hint through as a note', () => {
    const noResults = selectFindWorkHint({
      hint: 'No priced works matched your search.',
      hint_code: 'cost_explorer.hint.no_results',
    });
    expect(noResults).toEqual({
      kind: 'note',
      code: 'cost_explorer.hint.no_results',
      message: 'No priced works matched your search.',
    });

    const lowConfidence = selectFindWorkHint({
      hint: 'These are approximate matches.',
      hint_code: 'cost_explorer.hint.low_confidence',
    });
    expect(lowConfidence?.kind).toBe('note');
  });

  it('trims the hint text before using it', () => {
    const out = selectFindWorkHint({ hint: '  concrete  ', hint_code: DID_YOU_MEAN_CODE });
    expect(out).toEqual({ kind: 'suggestion', suggestion: 'concrete' });
  });
});

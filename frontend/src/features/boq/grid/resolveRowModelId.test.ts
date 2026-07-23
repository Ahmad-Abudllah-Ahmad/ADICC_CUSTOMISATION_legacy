// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { describe, it, expect } from 'vitest';
import { resolveRowModelId } from './resolveRowModelId';

// Issue #347 - the BOQ grid must resolve each row's BIM links against the
// model that OWNS those elements (Position.cad_model_id), not one shared
// project-level "first ready" model. These cases pin the selection: the row's
// own model wins whenever present, the project-level model is only a fallback.

const ROW_MODEL = '11111111-1111-1111-1111-111111111111';
const PROJECT_MODEL = '22222222-2222-2222-2222-222222222222';

describe('resolveRowModelId', () => {
  it('prefers the row model over the project-level fallback', () => {
    expect(resolveRowModelId(ROW_MODEL, PROJECT_MODEL)).toBe(ROW_MODEL);
  });

  it('falls back to the project model when the row has none', () => {
    expect(resolveRowModelId(null, PROJECT_MODEL)).toBe(PROJECT_MODEL);
    expect(resolveRowModelId(undefined, PROJECT_MODEL)).toBe(PROJECT_MODEL);
  });

  it('treats an empty-string row model as "no model" and falls back', () => {
    expect(resolveRowModelId('', PROJECT_MODEL)).toBe(PROJECT_MODEL);
  });

  it('returns the row model even when there is no fallback', () => {
    expect(resolveRowModelId(ROW_MODEL, null)).toBe(ROW_MODEL);
    expect(resolveRowModelId(ROW_MODEL, undefined)).toBe(ROW_MODEL);
  });

  it('returns null when neither is available', () => {
    expect(resolveRowModelId(null, null)).toBeNull();
    expect(resolveRowModelId(undefined, undefined)).toBeNull();
    expect(resolveRowModelId('', '')).toBeNull();
  });
});

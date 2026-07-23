// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { describe, it, expect } from 'vitest';
import {
  PRESETS,
  getUniversalPresets,
  getRegionalPresets,
  isUniversalPreset,
  UNIVERSAL_PRESET_IDS,
  type ColumnPreset,
} from '../index';

describe('BOQ preset registry', () => {
  it('exposes 14 presets total', () => {
    expect(PRESETS).toHaveLength(14);
  });

  it('partitions cleanly into universal (7) + regional (7)', () => {
    expect(getUniversalPresets()).toHaveLength(7);
    expect(getRegionalPresets()).toHaveLength(7);
    expect(getUniversalPresets().length + getRegionalPresets().length).toBe(PRESETS.length);
  });

  it('every preset has a unique id', () => {
    const ids = PRESETS.map((p) => p.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('every preset has at least one column', () => {
    for (const p of PRESETS) {
      expect(p.columns.length).toBeGreaterThan(0);
    }
  });

  it('every column inside a preset has a unique name', () => {
    for (const p of PRESETS) {
      const names = p.columns.map((c) => c.name);
      expect(new Set(names).size).toBe(names.length);
    }
  });

  it('column names are snake_case-ish (lower / digits / underscore only)', () => {
    const valid = /^[a-z][a-z0-9_]*$/;
    for (const p of PRESETS) {
      for (const c of p.columns) {
        expect(c.name, `${p.id}.${c.name}`).toMatch(valid);
      }
    }
  });

  it('select-type columns include non-empty options', () => {
    for (const p of PRESETS) {
      for (const c of p.columns) {
        if (c.column_type === 'select') {
          expect(c.options, `${p.id}.${c.name}`).toBeDefined();
          expect(c.options!.length).toBeGreaterThan(0);
        }
      }
    }
  });

  it('column_type stays in the supported set', () => {
    const allowed = new Set(['text', 'number', 'date', 'select']);
    for (const p of PRESETS) {
      for (const c of p.columns) {
        expect(allowed.has(c.column_type)).toBe(true);
      }
    }
  });

  it('region is one of the documented values', () => {
    const allowedRegions = new Set([
      'universal',
      'germany',
      'austria',
      'usa',
      'australia',
      'brazil',
      'uk',
      'integration',
    ]);
    for (const p of PRESETS) {
      expect(allowedRegions.has(p.region), `${p.id} → ${p.region}`).toBe(true);
    }
  });

  it('isUniversalPreset agrees with the region tag', () => {
    for (const p of PRESETS) {
      expect(isUniversalPreset(p)).toBe(p.region === 'universal');
    }
  });

  it('UNIVERSAL_PRESET_IDS lists exactly the universal presets', () => {
    const expected = new Set(getUniversalPresets().map((p) => p.id));
    expect(UNIVERSAL_PRESET_IDS).toEqual(expected);
  });

  it('keeps existing preset ids stable (no rename of v1.x presets)', () => {
    // Renaming a preset id silently invalidates anything that referenced
    // it (saved templates, telemetry, screenshots). Lock the existing
    // ids so a rename has to be deliberate.
    const ids = new Set(PRESETS.map((p) => p.id));
    for (const legacy of [
      'procurement',
      'notes',
      'quality',
      'sustainability',
      'gaeb_ava',
      'oenorm_brz',
      'bim',
    ]) {
      expect(ids.has(legacy), `legacy preset id removed: ${legacy}`).toBe(true);
    }
  });

  it('every regional preset has a non-universal region tag', () => {
    for (const p of getRegionalPresets()) {
      expect(p.region).not.toBe('universal');
    }
  });

  it('exposes the new v2.7.0 universal presets (status, tendering, schedule)', () => {
    const ids = new Set(getUniversalPresets().map((p) => p.id));
    expect(ids.has('status_scope')).toBe(true);
    expect(ids.has('tendering')).toBe(true);
    expect(ids.has('schedule')).toBe(true);
  });

  it('exposes the new v2.7.0 country presets (USA / AU / BR / UK)', () => {
    const ids = new Set(getRegionalPresets().map((p) => p.id));
    expect(ids.has('csi_masterformat')).toBe(true);
    expect(ids.has('aiqs_australia')).toBe(true);
    expect(ids.has('sinapi_brazil')).toBe(true);
    expect(ids.has('nrm2_uk')).toBe(true);
  });

  it('preset shape conforms to ColumnPreset (smoke type-test)', () => {
    const p: ColumnPreset | undefined = PRESETS[0];
    expect(p).toBeDefined();
    expect(p).toHaveProperty('id');
    expect(p).toHaveProperty('region');
    expect(p).toHaveProperty('icon');
    expect(p).toHaveProperty('columns');
  });
});

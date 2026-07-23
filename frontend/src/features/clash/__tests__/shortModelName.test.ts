// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { describe, expect, it } from 'vitest';
import { shortModelName } from '../ClashDetectionPage';

describe('shortModelName', () => {
  it('strips the exact project-name prefix when known', () => {
    expect(
      shortModelName(
        'Edifício Comercial Faria Lima - São Paulo - Modelo Estrutural Revit',
        'Edifício Comercial Faria Lima',
      ),
    ).toBe('Modelo Estrutural Revit');
  });

  it('collapses to the discipline tail even WITHOUT a project name', () => {
    // The bug: ctxProjectName is often empty on direct nav / ?project=
    // deep-link, so two such models read as "two projects".
    expect(
      shortModelName(
        'Edifício Comercial Faria Lima - São Paulo - Modelo Estrutural Revit',
        '',
      ),
    ).toBe('Modelo Estrutural Revit');
    expect(
      shortModelName(
        'Edifício Comercial Faria Lima - São Paulo - Modelo Arquitectónico IFC',
        null,
      ),
    ).toBe('Modelo Arquitectónico IFC');
  });

  it('handles en-dash, pipe and spaced-hyphen separators', () => {
    expect(shortModelName('Tower A – Level 3 – Structural')).toBe(
      'Structural',
    );
    expect(shortModelName('Proj | City | MEP IFC')).toBe('MEP IFC');
    expect(shortModelName('Proj - City - Architectural')).toBe(
      'Architectural',
    );
  });

  it('leaves a single-segment name untouched', () => {
    expect(shortModelName('Structural Model')).toBe('Structural Model');
  });

  it('falls back to the full name when stripping would empty it', () => {
    expect(shortModelName('   ')).toBe('');
    expect(shortModelName('Solo')).toBe('Solo');
  });
});

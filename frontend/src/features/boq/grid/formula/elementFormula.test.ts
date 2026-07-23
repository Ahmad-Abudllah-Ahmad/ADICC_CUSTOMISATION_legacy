// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { describe, it, expect } from 'vitest';
import rawVectors from '@/shared/lib/__fixtures__/elementFormula.vectors.json';
import {
  normalizeVarName,
  isNumericValue,
  buildElementVars,
  evaluateElementFormula,
} from './elementFormula';

// Issue #347 - these vectors are shared with the backend
// (backend/tests/unit/test_quantity_formula.py). Both sides run them so the
// normaliser, numeric test, variable builder and formula evaluator stay
// identical FE (float) and BE (Decimal).

interface Vectors {
  paramNames: { raw: string; normalized: string }[];
  numeric: { value: unknown; numeric: boolean }[];
  buildVars: {
    quantities: Record<string, unknown>;
    properties: Record<string, unknown>;
    expected: Record<string, number>;
  }[];
  formulaEval: { formula: string; vars: Record<string, number>; expected: number }[];
  formulaError: { formula: string; vars: Record<string, number>; reason: string }[];
}

const vectors = rawVectors as unknown as Vectors;

function toMap(vars: Record<string, number>): Map<string, number> {
  return new Map(Object.entries(vars).map(([k, n]) => [k, Number(n)]));
}

describe('elementFormula - shared parity vectors', () => {
  it('normalizeVarName matches every paramNames vector', () => {
    for (const v of vectors.paramNames) {
      expect(normalizeVarName(v.raw)).toBe(v.normalized);
    }
  });

  it('isNumericValue matches every numeric vector', () => {
    for (const v of vectors.numeric) {
      expect(isNumericValue(v.value)).toBe(v.numeric);
    }
  });

  it('buildElementVars matches every buildVars vector', () => {
    for (const v of vectors.buildVars) {
      const got = buildElementVars(v.quantities, v.properties);
      const obj: Record<string, number> = {};
      for (const [k, val] of got) obj[k] = val;
      expect(obj).toEqual(v.expected);
    }
  });

  it('evaluateElementFormula matches every formulaEval vector', () => {
    for (const v of vectors.formulaEval) {
      const got = evaluateElementFormula(v.formula, toMap(v.vars));
      expect(Math.abs(got - v.expected)).toBeLessThan(1e-9);
    }
  });

  it('evaluateElementFormula throws on every formulaError vector', () => {
    for (const v of vectors.formulaError) {
      expect(() => evaluateElementFormula(v.formula, toMap(v.vars))).toThrow();
    }
  });
});

describe('elementFormula - engine integration', () => {
  it('resolves a bare identifier from elementVars', () => {
    expect(evaluateElementFormula('area_m2 + 1', new Map([['area_m2', 9]]))).toBe(10);
  });

  it('still rejects an identifier that is not a supplied element variable', () => {
    expect(() => evaluateElementFormula('nope * 2', new Map([['area_m2', 9]]))).toThrow();
  });

  it('leaves the legacy engine behaviour intact when no elementVars are given', () => {
    // buildElementVars over an empty element yields an empty map; a bare name
    // then has nowhere to resolve and must throw (no silent zero).
    expect(() => evaluateElementFormula('area_m2', buildElementVars({}, {}))).toThrow();
  });
});

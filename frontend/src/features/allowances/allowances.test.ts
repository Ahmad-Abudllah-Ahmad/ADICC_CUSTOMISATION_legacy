// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for the pure allowances register helpers in ./api. These are DB- and
// DOM-free: they assert the canonical type ordering, the type-label key mapping,
// the AllowanceType guard, and that groupAllowancesByType sections a register by
// type in canonical order, keeping input order within a section and emitting a
// section only for a type that is actually present.

import { describe, it, expect } from 'vitest';
import {
  ALLOWANCE_TYPES,
  ALLOWANCE_TYPE_DEFAULT_LABELS,
  allowanceTypeLabelKey,
  groupAllowancesByType,
  isAllowanceType,
  type Allowance,
  type AllowanceType,
} from './api';

function makeAllowance(id: string, type: AllowanceType, remaining = '0.00'): Allowance {
  return {
    id,
    project_id: 'p1',
    label: `Allowance ${id}`,
    allowance_type: type,
    held_amount: '1000.00',
    currency: 'USD',
    notes: null,
    drawn: '0.00',
    remaining,
    overdrawn: false,
    drawdown_count: 0,
    created_by: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  };
}

describe('ALLOWANCE_TYPES', () => {
  it('lists the three register types in canonical order', () => {
    expect(ALLOWANCE_TYPES).toEqual(['provisional_sum', 'pc_sum', 'contingency']);
  });

  it('has a default label for every type', () => {
    for (const type of ALLOWANCE_TYPES) {
      expect(ALLOWANCE_TYPE_DEFAULT_LABELS[type]).toBeTruthy();
    }
  });
});

describe('allowanceTypeLabelKey', () => {
  it('namespaces the i18n key under allowances.type_', () => {
    expect(allowanceTypeLabelKey('contingency')).toBe('allowances.type_contingency');
    expect(allowanceTypeLabelKey('pc_sum')).toBe('allowances.type_pc_sum');
  });
});

describe('isAllowanceType', () => {
  it('accepts known types and rejects anything else', () => {
    expect(isAllowanceType('provisional_sum')).toBe(true);
    expect(isAllowanceType('contingency')).toBe(true);
    expect(isAllowanceType('markup')).toBe(false);
    expect(isAllowanceType('')).toBe(false);
  });
});

describe('groupAllowancesByType', () => {
  it('returns no sections for an empty register', () => {
    expect(groupAllowancesByType([])).toEqual([]);
  });

  it('emits a section only for types that are present, in canonical order', () => {
    const items = [
      makeAllowance('c', 'contingency'),
      makeAllowance('p', 'provisional_sum'),
    ];
    const groups = groupAllowancesByType(items);
    expect(groups.map((g) => g.type)).toEqual(['provisional_sum', 'contingency']);
    // pc_sum has no allowances, so it produces no section.
    expect(groups.some((g) => g.type === 'pc_sum')).toBe(false);
  });

  it('keeps every allowance and preserves input order within a section', () => {
    const items = [
      makeAllowance('a', 'contingency'),
      makeAllowance('b', 'contingency'),
      makeAllowance('c', 'provisional_sum'),
    ];
    const groups = groupAllowancesByType(items);
    const contingency = groups.find((g) => g.type === 'contingency');
    expect(contingency?.items.map((a) => a.id)).toEqual(['a', 'b']);
    const total = groups.reduce((n, g) => n + g.items.length, 0);
    expect(total).toBe(items.length);
  });
});

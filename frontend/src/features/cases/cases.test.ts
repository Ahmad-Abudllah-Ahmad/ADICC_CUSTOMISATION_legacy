// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Unit tests for the Cases feature: the pure progress helpers (the heart of
// the stepper) and the auto-discovery glob shape (the contract the parallel
// data-file authors write against).

import { describe, it, expect } from 'vitest';
import {
  clampStepIndex,
  completedCount,
  emptyProgress,
  isPlaybookDone,
  isStepDone,
  nextStepIndex,
  progressPct,
  resolveStepRoute,
  runKey,
  toggleStep,
} from './progress';
import { PLAYBOOKS, getPlaybook } from './playbooks';
import { CATEGORY_META } from './categories';
import { COMPANY_TYPE_META } from './companyTypes';
import type { Playbook, PlaybookProgress } from './types';

/** A small synthetic playbook so the helper tests do not depend on shipped content. */
function makePlaybook(stepIds: string[]): Playbook {
  return {
    id: 'test-pb',
    order: 1,
    category: 'estimating',
    companyTypes: ['general-contractor'],
    titleKey: 'x.title',
    titleDefault: 'Test',
    descKey: 'x.desc',
    descDefault: 'Test case',
    estMinutes: 5,
    steps: stepIds.map((id) => ({
      id,
      titleKey: `x.${id}.title`,
      titleDefault: id,
      whatKey: `x.${id}.what`,
      whatDefault: 'what',
      whyKey: `x.${id}.why`,
      whyDefault: 'why',
      moduleLabel: 'Module',
      to: '/somewhere',
    })),
  };
}

const prog = (completedStepIds: string[], currentStepIndex = 0): PlaybookProgress => ({
  completedStepIds,
  currentStepIndex,
});

describe('runKey', () => {
  it('is the bare playbook id when unscoped', () => {
    expect(runKey('pb')).toBe('pb');
    expect(runKey('pb', null)).toBe('pb');
    expect(runKey('pb', '')).toBe('pb');
  });

  it('namespaces by project id when scoped', () => {
    expect(runKey('pb', 'proj-123')).toBe('pb::proj-123');
  });
});

describe('isStepDone', () => {
  it('reflects membership in the completed set', () => {
    const p = prog(['a', 'c']);
    expect(isStepDone(p, 'a')).toBe(true);
    expect(isStepDone(p, 'b')).toBe(false);
  });
});

describe('completedCount', () => {
  it('counts only the playbook own steps', () => {
    const pb = makePlaybook(['a', 'b', 'c']);
    expect(completedCount(prog(['a', 'b']), pb)).toBe(2);
  });

  it('ignores stale ids no longer in the playbook', () => {
    const pb = makePlaybook(['a', 'b', 'c']);
    // 'zz' was completed under an older version of the data file.
    expect(completedCount(prog(['a', 'zz']), pb)).toBe(1);
  });

  it('is 0 for empty progress', () => {
    const pb = makePlaybook(['a', 'b']);
    expect(completedCount(emptyProgress(), pb)).toBe(0);
  });
});

describe('isPlaybookDone', () => {
  it('is true only when every step is complete', () => {
    const pb = makePlaybook(['a', 'b']);
    expect(isPlaybookDone(prog(['a']), pb)).toBe(false);
    expect(isPlaybookDone(prog(['a', 'b']), pb)).toBe(true);
  });

  it('is false for an empty playbook', () => {
    expect(isPlaybookDone(prog([]), makePlaybook([]))).toBe(false);
  });
});

describe('nextStepIndex', () => {
  it('returns the first incomplete step index', () => {
    const pb = makePlaybook(['a', 'b', 'c']);
    expect(nextStepIndex(prog(['a']), pb)).toBe(1);
    expect(nextStepIndex(prog(['a', 'b']), pb)).toBe(2);
  });

  it('returns 0 when nothing is done', () => {
    expect(nextStepIndex(emptyProgress(), makePlaybook(['a', 'b']))).toBe(0);
  });

  it('clamps to the last step when everything is done', () => {
    const pb = makePlaybook(['a', 'b', 'c']);
    expect(nextStepIndex(prog(['a', 'b', 'c']), pb)).toBe(2);
  });

  it('is 0 for an empty playbook', () => {
    expect(nextStepIndex(emptyProgress(), makePlaybook([]))).toBe(0);
  });
});

describe('progressPct', () => {
  it('is a whole-number percentage', () => {
    const pb = makePlaybook(['a', 'b', 'c', 'd']);
    expect(progressPct(prog(['a']), pb)).toBe(25);
    expect(progressPct(prog(['a', 'b', 'c']), pb)).toBe(75);
  });

  it('is 0 for an empty playbook (no divide-by-zero)', () => {
    expect(progressPct(emptyProgress(), makePlaybook([]))).toBe(0);
  });
});

describe('toggleStep', () => {
  it('adds a step and does not mutate the input', () => {
    const before = prog(['a']);
    const after = toggleStep(before, 'b');
    expect(after.completedStepIds).toEqual(['a', 'b']);
    // Immutability: original untouched.
    expect(before.completedStepIds).toEqual(['a']);
    expect(after).not.toBe(before);
  });

  it('removes a step that was already done', () => {
    const after = toggleStep(prog(['a', 'b']), 'a');
    expect(after.completedStepIds).toEqual(['b']);
  });

  it('preserves currentStepIndex', () => {
    const after = toggleStep(prog(['a'], 3), 'b');
    expect(after.currentStepIndex).toBe(3);
  });
});

describe('clampStepIndex', () => {
  it('clamps into [0, total-1]', () => {
    expect(clampStepIndex(-2, 5)).toBe(0);
    expect(clampStepIndex(9, 5)).toBe(4);
    expect(clampStepIndex(2, 5)).toBe(2);
  });

  it('is 0 for an empty list', () => {
    expect(clampStepIndex(3, 0)).toBe(0);
  });
});

describe('resolveStepRoute', () => {
  it('fills the :projectId slot when a project is chosen', () => {
    expect(resolveStepRoute('/projects/:projectId/boq', 'p1')).toBe('/projects/p1/boq');
    expect(resolveStepRoute('/projects/:projectId/files', 'abc')).toBe('/projects/abc/files');
  });

  it('strips the project segment when unscoped', () => {
    expect(resolveStepRoute('/projects/:projectId/boq', null)).toBe('/boq');
    expect(resolveStepRoute('/projects/:projectId', null)).toBe('/');
  });

  it('returns routes without a slot unchanged, query preserved', () => {
    expect(resolveStepRoute('/takeoff?tab=measurements', null)).toBe('/takeoff?tab=measurements');
    expect(resolveStepRoute('/validation', 'p1')).toBe('/validation');
  });
});

/* ── Auto-discovery contract ────────────────────────────────────────────── */

describe('playbook auto-discovery (import.meta.glob)', () => {
  it('discovers at least the reference case', () => {
    expect(Array.isArray(PLAYBOOKS)).toBe(true);
    expect(PLAYBOOKS.length).toBeGreaterThan(0);
    expect(PLAYBOOKS.some((p) => p.id === 'price-from-pdf')).toBe(true);
  });

  it('is sorted by order ascending', () => {
    const orders = PLAYBOOKS.map((p) => p.order);
    const sorted = [...orders].sort((a, b) => a - b);
    expect(orders).toEqual(sorted);
  });

  it('has unique ids', () => {
    const ids = PLAYBOOKS.map((p) => p.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('every playbook matches the required shape', () => {
    for (const pb of PLAYBOOKS) {
      expect(typeof pb.id).toBe('string');
      expect(typeof pb.order).toBe('number');
      expect(typeof pb.titleKey).toBe('string');
      expect(typeof pb.titleDefault).toBe('string');
      expect(typeof pb.descKey).toBe('string');
      expect(typeof pb.descDefault).toBe('string');
      expect(typeof pb.estMinutes).toBe('number');
      expect(Array.isArray(pb.steps)).toBe(true);
      expect(pb.steps.length).toBeGreaterThan(0);
      for (const step of pb.steps) {
        expect(typeof step.id).toBe('string');
        expect(typeof step.titleKey).toBe('string');
        expect(typeof step.titleDefault).toBe('string');
        expect(typeof step.whatKey).toBe('string');
        expect(typeof step.whatDefault).toBe('string');
        expect(typeof step.whyKey).toBe('string');
        expect(typeof step.whyDefault).toBe('string');
        expect(typeof step.moduleLabel).toBe('string');
        expect(typeof step.to).toBe('string');
        expect(step.to.startsWith('/')).toBe(true);
      }
      // Step ids are unique within a playbook (progress is keyed by them).
      const stepIds = pb.steps.map((s) => s.id);
      expect(new Set(stepIds).size).toBe(stepIds.length);
    }
  });

  it('getPlaybook resolves a known id and rejects unknown', () => {
    expect(getPlaybook('price-from-pdf')?.id).toBe('price-from-pdf');
    expect(getPlaybook('does-not-exist')).toBeUndefined();
    expect(getPlaybook(undefined)).toBeUndefined();
  });
});

/* ── Shipped-content integrity: every case must be usable end to end ─────── */

const VALID_CATEGORIES = new Set(CATEGORY_META.map((c) => c.id));
const VALID_COMPANY_TYPES = new Set(COMPANY_TYPE_META.map((c) => c.id));

describe('shipped cases integrity', () => {
  it('ships the full expected catalogue', () => {
    // Guards against a data file silently dropping out of the glob.
    expect(PLAYBOOKS.length).toBeGreaterThanOrEqual(50);
  });

  it('every case has a known category and a positive time estimate', () => {
    for (const pb of PLAYBOOKS) {
      expect(VALID_CATEGORIES.has(pb.category)).toBe(true);
      expect(pb.estMinutes).toBeGreaterThan(0);
    }
  });

  it('every case declares at least one known company type', () => {
    for (const pb of PLAYBOOKS) {
      expect(Array.isArray(pb.companyTypes)).toBe(true);
      expect(pb.companyTypes.length).toBeGreaterThan(0);
      for (const id of pb.companyTypes) {
        expect(VALID_COMPANY_TYPES.has(id), `unknown company type "${id}" on "${pb.id}"`).toBe(
          true,
        );
      }
    }
  });

  it('orders are unique so the list is deterministic', () => {
    const orders = PLAYBOOKS.map((p) => p.order);
    expect(new Set(orders).size).toBe(orders.length);
  });

  it('every step route resolves to a usable path, scoped and unscoped', () => {
    for (const pb of PLAYBOOKS) {
      for (const step of pb.steps) {
        // A project slot may only appear as the standard prefix.
        if (step.to.includes(':projectId')) {
          expect(step.to.startsWith('/projects/:projectId')).toBe(true);
        }
        // Both resolutions must yield a clean absolute path with no leftover
        // slot and no doubled slashes.
        for (const pid of ['p1', null] as const) {
          const r = resolveStepRoute(step.to, pid);
          expect(r.startsWith('/')).toBe(true);
          expect(r).not.toContain(':projectId');
          expect(r).not.toContain('//');
        }
      }
    }
  });

  it('all copy is plain ASCII with no long dashes or smart quotes', () => {
    // en/em dashes, curly quotes and ellipsis - the no-long-dash rule applies
    // to shipped copy too, and this catches stray non-ASCII. Escapes keep this
    // source file itself ASCII-clean.
    const badChar = /[\u2010-\u2015\u2018\u2019\u201C\u201D\u2026]/;
    for (const pb of PLAYBOOKS) {
      const strings = [pb.titleDefault, pb.descDefault];
      if (pb.longDescDefault) strings.push(pb.longDescDefault);
      for (const step of pb.steps) {
        strings.push(step.titleDefault, step.whatDefault, step.whyDefault, step.moduleLabel);
      }
      for (const s of strings) {
        expect(badChar.test(s), `bad character in "${s}"`).toBe(false);
      }
    }
  });
});

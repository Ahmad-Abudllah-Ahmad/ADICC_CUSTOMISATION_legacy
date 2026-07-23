// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
// OpenConstructionERP — DataDrivenConstruction (DDC)
// Tests for the conversational-intake pure helpers (no React, no network).
import { describe, expect, it } from 'vitest';
import {
  serializeAnswerValue,
  serializeAnswers,
  unansweredRequired,
  seedDraftFromQuestions,
  mapDependencyWarnings,
  deriveRoundView,
  isFinalRound,
  coverageVariant,
  coverageTally,
  groupPackagesByStage,
  primaryStage,
  scorePercent,
  typeConfidenceLabel,
  isOfflineMode,
  degradedMessage,
  MAX_INTAKE_ROUNDS,
} from '../helpers';
import type {
  ComposedPackage,
  DependencyWarning,
  IntakeQuestion,
  IntakeState,
} from '../types';

// ── Fixtures ─────────────────────────────────────────────────────────────────

function q(partial: Partial<IntakeQuestion>): IntakeQuestion {
  return {
    param_key: 'floor_area_m2',
    kind: 'number',
    unit: 'm2',
    required: false,
    options: [],
    prompt: 'How big?',
    why: 'aiest.why.floor_area_m2',
    current_value: null,
    ...partial,
  };
}

function pkg(partial: Partial<ComposedPackage>): ComposedPackage {
  return {
    package_key: 'wall_tiling',
    trade: 'finishing',
    selected: true,
    stages: ['finish'],
    group_ids: [],
    coverage: 'grounded',
    best_score: 0.8,
    quantity: 12,
    unit: 'm2',
    estimated: false,
    ...partial,
  };
}

function state(partial: Partial<IntakeState>): IntakeState {
  return {
    run_id: 'run-1',
    mode: 'ai',
    phase: 'clarify_round_1',
    round_idx: 0,
    rounds_remaining: 3,
    detected_type: 'kitchen_reno',
    type_confidence: 0.7,
    params: {},
    questions: [],
    packages: [],
    dependency_warnings: [],
    transcript: [],
    ai_connected: true,
    vector_ready: true,
    degraded_reason: null,
    summary: null,
    ...partial,
  };
}

// ── serializeAnswerValue ─────────────────────────────────────────────────────

describe('serializeAnswerValue', () => {
  it('parses numeric strings (and comma decimals) for number/length kinds', () => {
    expect(serializeAnswerValue('number', '12')).toBe(12);
    expect(serializeAnswerValue('length', '2,7')).toBe(2.7);
    expect(serializeAnswerValue('number', 8)).toBe(8);
  });

  it('returns null for blank or unparseable numbers (never zero)', () => {
    expect(serializeAnswerValue('number', '')).toBeNull();
    expect(serializeAnswerValue('number', '   ')).toBeNull();
    expect(serializeAnswerValue('number', 'abc')).toBeNull();
    expect(serializeAnswerValue('number', null)).toBeNull();
  });

  it('coerces booleans from toggle values and string forms', () => {
    expect(serializeAnswerValue('bool', true)).toBe(true);
    expect(serializeAnswerValue('bool', false)).toBe(false);
    expect(serializeAnswerValue('bool', 'true')).toBe(true);
    expect(serializeAnswerValue('bool', 'no')).toBe(false);
    expect(serializeAnswerValue('bool', '')).toBeNull();
  });

  it('keeps choice strings and nulls an empty choice', () => {
    expect(serializeAnswerValue('choice', 'standard')).toBe('standard');
    expect(serializeAnswerValue('choice', '')).toBeNull();
  });
});

// ── serializeAnswers ─────────────────────────────────────────────────────────

describe('serializeAnswers', () => {
  it('only serializes keys present in the current question batch', () => {
    const questions = [q({ param_key: 'floor_area_m2', kind: 'number' })];
    const draft = { floor_area_m2: '12', stale_key: 'x' };
    expect(serializeAnswers(questions, draft)).toEqual({ floor_area_m2: 12 });
  });

  it('omits null (unanswered) values rather than sending blanks', () => {
    const questions = [
      q({ param_key: 'floor_area_m2', kind: 'number' }),
      q({ param_key: 'finish_level', kind: 'choice' }),
    ];
    const draft = { floor_area_m2: '', finish_level: 'premium' };
    expect(serializeAnswers(questions, draft)).toEqual({ finish_level: 'premium' });
  });

  it('serializes a boolean false (a real answer, not a blank)', () => {
    const questions = [q({ param_key: 'demolition', kind: 'bool' })];
    expect(serializeAnswers(questions, { demolition: false })).toEqual({ demolition: false });
  });
});

// ── unansweredRequired ───────────────────────────────────────────────────────

describe('unansweredRequired', () => {
  it('flags required questions with no value in draft or current_value', () => {
    const questions = [
      q({ param_key: 'floor_area_m2', kind: 'number', required: true }),
      q({ param_key: 'ceiling_height_m', kind: 'length', required: false }),
    ];
    expect(unansweredRequired(questions, {})).toEqual(['floor_area_m2']);
  });

  it('treats a prefilled current_value as answered', () => {
    const questions = [
      q({ param_key: 'floor_area_m2', kind: 'number', required: true, current_value: 120 }),
    ];
    expect(unansweredRequired(questions, {})).toEqual([]);
  });

  it('returns empty when every required question is answered in the draft', () => {
    const questions = [q({ param_key: 'floor_area_m2', kind: 'number', required: true })];
    expect(unansweredRequired(questions, { floor_area_m2: '12' })).toEqual([]);
  });
});

// ── seedDraftFromQuestions ───────────────────────────────────────────────────

describe('seedDraftFromQuestions', () => {
  it('seeds only defined current_values', () => {
    const questions = [
      q({ param_key: 'floor_area_m2', current_value: 120 }),
      q({ param_key: 'ceiling_height_m', current_value: null }),
    ];
    expect(seedDraftFromQuestions(questions)).toEqual({ floor_area_m2: 120 });
  });
});

// ── mapDependencyWarnings ────────────────────────────────────────────────────

describe('mapDependencyWarnings', () => {
  it('maps each warning to the i18n key with prereq interpolation params', () => {
    const warnings: DependencyWarning[] = [
      {
        code: 'aiest.dep.missing_prereq',
        successor: 'wall_tiling',
        prerequisite: 'wall_plaster',
        successor_stage: 'finish',
        prerequisite_stage: 'close',
      },
    ];
    const mapped = mapDependencyWarnings(warnings);
    expect(mapped).toHaveLength(1);
    const first = mapped[0]!;
    expect(first.i18nKey).toBe('aiest.dep.missing_prereq');
    expect(first.params.prereq).toBe('wall_plaster');
    expect(first.id).toBe('wall_tiling::wall_plaster');
    expect(first.defaultValue).toContain('{{prereq}}');
  });

  it('falls back to the canonical key when code is missing', () => {
    const mapped = mapDependencyWarnings([
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      { successor: 'a', prerequisite: 'b', successor_stage: 'finish', prerequisite_stage: 'close' } as any,
    ]);
    expect(mapped[0]!.i18nKey).toBe('aiest.dep.missing_prereq');
  });

  it('returns an empty array for null / non-array input', () => {
    expect(mapDependencyWarnings(null)).toEqual([]);
    expect(mapDependencyWarnings(undefined)).toEqual([]);
  });
});

// ── deriveRoundView / isFinalRound ───────────────────────────────────────────

describe('deriveRoundView', () => {
  it('returns a safe default for a null state', () => {
    const v = deriveRoundView(null);
    expect(v.inRound).toBe(false);
    expect(v.roundNumber).toBe(1);
    expect(v.maxRounds).toBe(MAX_INTAKE_ROUNDS);
  });

  it('reports the active round as round_idx + 1 (1-based)', () => {
    const v = deriveRoundView(state({ phase: 'clarify_round_2', round_idx: 1, questions: [q({})] }));
    expect(v.inRound).toBe(true);
    expect(v.roundNumber).toBe(2);
    expect(v.questions).toHaveLength(1);
  });

  it('never renders a round number above the 3-round cap', () => {
    const v = deriveRoundView(state({ phase: 'clarify_round_3', round_idx: 9 }));
    expect(v.roundNumber).toBe(MAX_INTAKE_ROUNDS);
  });

  it('detects the parameter sheet and group board phases', () => {
    expect(deriveRoundView(state({ phase: 'parameter_sheet' })).onParameterSheet).toBe(true);
    expect(deriveRoundView(state({ phase: 'group_board' })).onGroupBoard).toBe(true);
  });

  it('treats extract/compose with no questions as working', () => {
    expect(deriveRoundView(state({ phase: 'extract', questions: [] })).isWorking).toBe(true);
    expect(deriveRoundView(state({ phase: 'compose_groups', questions: [] })).isWorking).toBe(true);
  });

  it('hides questions when off-round', () => {
    const v = deriveRoundView(state({ phase: 'parameter_sheet', questions: [q({})] }));
    expect(v.questions).toEqual([]);
  });
});

describe('isFinalRound', () => {
  it('is true when one clarification round remains', () => {
    expect(isFinalRound(state({ phase: 'clarify_round_3', rounds_remaining: 1 }))).toBe(true);
  });
  it('is false with rounds to spare', () => {
    expect(isFinalRound(state({ phase: 'clarify_round_1', rounds_remaining: 3 }))).toBe(false);
  });
  it('is false outside a clarification round', () => {
    expect(isFinalRound(state({ phase: 'parameter_sheet', rounds_remaining: 0 }))).toBe(false);
  });
});

// ── coverage / scoring ───────────────────────────────────────────────────────

describe('coverage helpers', () => {
  it('maps coverage bands to badge variants', () => {
    expect(coverageVariant('grounded')).toBe('success');
    expect(coverageVariant('weak')).toBe('warning');
    expect(coverageVariant('gap')).toBe('error');
  });

  it('tallies coverage across selected packages only', () => {
    const packages = [
      pkg({ coverage: 'grounded' }),
      pkg({ package_key: 'p2', coverage: 'weak' }),
      pkg({ package_key: 'p3', coverage: 'gap' }),
      pkg({ package_key: 'p4', coverage: 'grounded', selected: false }),
    ];
    expect(coverageTally(packages)).toEqual({ total: 3, grounded: 1, weak: 1, gap: 1 });
  });

  it('formats a real score as a percent and null as a dash', () => {
    expect(scorePercent(0.781)).toBe('78%');
    expect(scorePercent(null)).toBe('—');
    expect(scorePercent(undefined)).toBe('—');
    expect(scorePercent(Number.NaN)).toBe('—');
  });

  it('labels type confidence: percent when real, "selected" when null', () => {
    expect(typeConfidenceLabel(0.7).defaultValue).toBe('70%');
    expect(typeConfidenceLabel(0.7).i18nKey).toBeNull();
    expect(typeConfidenceLabel(null).i18nKey).toBe('aiest.type.selected');
  });
});

// ── stage grouping ───────────────────────────────────────────────────────────

describe('groupPackagesByStage', () => {
  it('picks the earliest foreman stage a package spans', () => {
    expect(primaryStage(pkg({ stages: ['close', 'finish'] }))).toBe('close');
    expect(primaryStage(pkg({ stages: ['demo', 'rough'] }))).toBe('demo');
  });

  it('orders stages in foreman build order and drops empty stages', () => {
    const packages = [
      pkg({ package_key: 'tiling', stages: ['finish'] }),
      pkg({ package_key: 'strip', stages: ['demo'] }),
      pkg({ package_key: 'wiring', stages: ['rough'] }),
    ];
    const groups = groupPackagesByStage(packages);
    expect(groups.map((g) => g.stage)).toEqual(['demo', 'rough', 'finish']);
  });

  it('within a stage sorts grounded before weak before gap', () => {
    const packages = [
      pkg({ package_key: 'a', stages: ['finish'], coverage: 'gap' }),
      pkg({ package_key: 'b', stages: ['finish'], coverage: 'grounded' }),
      pkg({ package_key: 'c', stages: ['finish'], coverage: 'weak' }),
    ];
    const [finishGroup] = groupPackagesByStage(packages);
    expect(finishGroup!.packages.map((p) => p.coverage)).toEqual(['grounded', 'weak', 'gap']);
  });
});

// ── mode / degradation ───────────────────────────────────────────────────────

describe('mode + degradation helpers', () => {
  it('detects offline mode by mode flag or no_ai_key degradation', () => {
    expect(isOfflineMode(state({ mode: 'offline' }))).toBe(true);
    expect(isOfflineMode(state({ mode: 'ai', degraded_reason: 'no_ai_key' }))).toBe(true);
    expect(isOfflineMode(state({ mode: 'ai', degraded_reason: null }))).toBe(false);
    expect(isOfflineMode(null)).toBe(false);
  });

  it('maps known degraded reasons to a message key, null otherwise', () => {
    expect(degradedMessage('no_ai_key')?.i18nKey).toBe('aiest.degraded.no_ai_key');
    expect(degradedMessage('no_vectors')?.i18nKey).toBe('aiest.degraded.no_vectors');
    expect(degradedMessage('no_catalogue')?.i18nKey).toBe('aiest.degraded.no_catalogue');
    expect(degradedMessage(null)).toBeNull();
    expect(degradedMessage('something_else')).toBeNull();
  });
});

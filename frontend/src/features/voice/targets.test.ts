// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Unit tests for the voice target field schemas + pure helpers. These guard the
// contract with the backend voice.structuring specs: the field names and enum
// choices must match exactly, because the review UI renders from these and the
// confirmed values are saved through each target's own create endpoint.

import { describe, expect, it } from 'vitest';

import { VOICE_TARGETS, getField, humanizeToken, voiceTargetDef } from './targets';

describe('humanizeToken', () => {
  it('turns an enum token into a readable label', () => {
    expect(humanizeToken('fire_safety')).toBe('Fire safety');
    expect(humanizeToken('task')).toBe('Task');
    expect(humanizeToken('')).toBe('');
  });
});

describe('getField', () => {
  it('reads a present field and tolerates a missing one', () => {
    expect(getField({ title: 'Cracked wall' }, 'title')).toBe('Cracked wall');
    expect(getField({}, 'title')).toBe('');
  });
});

describe('voiceTargetDef', () => {
  it('exposes exactly the three supported targets', () => {
    expect(Object.keys(VOICE_TARGETS).sort()).toEqual(['defect', 'diary_note', 'task']);
  });

  it('every target has a title and description field', () => {
    for (const target of ['diary_note', 'defect', 'task'] as const) {
      const names = voiceTargetDef(target).fields.map((f) => f.name);
      expect(names).toContain('title');
      expect(names).toContain('description');
    }
  });

  it('defect fields match the backend punchlist shape', () => {
    const names = voiceTargetDef('defect').fields.map((f) => f.name);
    expect(names).toEqual(['title', 'description', 'location', 'trade', 'category', 'priority']);
    const priority = voiceTargetDef('defect').fields.find((f) => f.name === 'priority');
    expect(priority?.choices).toEqual(['low', 'medium', 'high', 'critical']);
  });

  it('task priority uses the task-module enum (normal, not medium)', () => {
    const priority = voiceTargetDef('task').fields.find((f) => f.name === 'priority');
    expect(priority?.choices).toEqual(['low', 'normal', 'high', 'urgent']);
    const due = voiceTargetDef('task').fields.find((f) => f.name === 'due_date');
    expect(due?.kind).toBe('date');
  });

  it('diary entry_type is an enum defaulting into the diary options', () => {
    const entryType = voiceTargetDef('diary_note').fields.find((f) => f.name === 'entry_type');
    expect(entryType?.kind).toBe('enum');
    expect(entryType?.choices).toContain('general');
    expect(entryType?.choices).toContain('delivery');
  });

  it('enum option keys reuse each target module i18n namespace', () => {
    const category = voiceTargetDef('defect').fields.find((f) => f.name === 'category');
    expect(category?.optionKey?.('structural')).toBe('punch.category_structural');
    const taskPriority = voiceTargetDef('task').fields.find((f) => f.name === 'priority');
    expect(taskPriority?.optionKey?.('high')).toBe('tasks.priority_high');
  });
});

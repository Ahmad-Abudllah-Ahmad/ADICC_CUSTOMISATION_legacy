// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
// OpenConstructionERP — DataDrivenConstruction (DDC)
// Tests for the built-in example-prompt catalogue.
import { describe, expect, it } from 'vitest';
import { useTranslation } from 'react-i18next';
import { EXAMPLE_PROMPTS, getExamplePromptById } from '../examplePrompts';

describe('EXAMPLE_PROMPTS catalogue', () => {
  it('contains exactly six entries (one per region demo in the spec)', () => {
    expect(EXAMPLE_PROMPTS).toHaveLength(6);
  });

  it('every id is unique', () => {
    const ids = EXAMPLE_PROMPTS.map((p) => p.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('every entry has a non-empty prompt and label fields', () => {
    for (const p of EXAMPLE_PROMPTS) {
      expect(p.id).toMatch(/^[a-z0-9-]+$/);
      expect(p.labelKey).toMatch(/^ai\./);
      expect(p.labelFallback.length).toBeGreaterThan(0);
      expect(p.prompt.length).toBeGreaterThan(10);
    }
  });

  it('every label resolves to a non-empty string through the translation hook', () => {
    // The vitest setup mocks useTranslation to echo opts.defaultValue
    // (mirroring the production fallback behaviour). Threading every
    // entry through it proves the labels never resolve to empty strings.
    const { t } = useTranslation();
    for (const p of EXAMPLE_PROMPTS) {
      const label = t(p.labelKey, { defaultValue: p.labelFallback }) as string;
      expect(label.length).toBeGreaterThan(0);
    }
  });

  it('prompts stay in English so the LLM gets the highest-quality input', () => {
    // Cheap heuristic: the fallback labels mention an English placename,
    // and the prompt itself should contain that placename. The point is
    // to catch accidental localisation of the prompt body (which would
    // tank model quality on smaller LLMs).
    for (const p of EXAMPLE_PROMPTS) {
      const placename = p.labelFallback.split(',').pop()?.trim() ?? '';
      if (placename.length > 0) {
        // Strip diacritics so 'São Paulo' matches 'Sao Paulo' if someone
        // normalises the prompt later — we only care that the city is
        // referenced, not how the accent is encoded.
        const normalize = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '');
        expect(normalize(p.prompt).toLowerCase()).toContain(
          normalize(placename).toLowerCase(),
        );
      }
    }
  });
});

describe('getExamplePromptById', () => {
  it('returns the entry for a known id', () => {
    expect(getExamplePromptById('apartment-berlin')?.prompt).toContain('Berlin');
  });

  it('returns undefined for an unknown id', () => {
    expect(getExamplePromptById('does-not-exist')).toBeUndefined();
  });
});

// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
// OpenConstructionERP — DataDrivenConstruction (DDC)
// Tests for normalizePackLocale: maps a partner pack's BCP-47 default_locale to
// a supported base UI language, so an active pack forces the right language
// (batimatech-ca -> fr) and never an unsupported one.
import { describe, expect, it } from 'vitest';

import { normalizePackLocale } from '../i18n';

describe('normalizePackLocale', () => {
  it('strips the region subtag to a supported base language', () => {
    expect(normalizePackLocale('fr-CA')).toBe('fr'); // batimatech-ca
    expect(normalizePackLocale('en-GB')).toBe('en'); // uk-jct
    expect(normalizePackLocale('en-US')).toBe('en'); // us-rsmeans
    expect(normalizePackLocale('en-AU')).toBe('en'); // aus
    expect(normalizePackLocale('en-NZ')).toBe('en'); // nzs
  });

  it('passes through base codes the UI ships', () => {
    expect(normalizePackLocale('de')).toBe('de'); // bimhessen-de, doker-formwork
    expect(normalizePackLocale('pt')).toBe('pt'); // brazil-sinapi
    expect(normalizePackLocale('ar')).toBe('ar'); // saudi-vision2030 (RTL)
    expect(normalizePackLocale('en')).toBe('en'); // india-cpwd, modular-prefab
  });

  it('is case-insensitive and trims', () => {
    expect(normalizePackLocale('FR-ca')).toBe('fr');
    expect(normalizePackLocale(' de ')).toBe('de');
  });

  it('falls back to English for unsupported or empty locales', () => {
    expect(normalizePackLocale('xx-YY')).toBe('en');
    expect(normalizePackLocale('')).toBe('en');
    expect(normalizePackLocale(null)).toBe('en');
    expect(normalizePackLocale(undefined)).toBe('en');
  });
});

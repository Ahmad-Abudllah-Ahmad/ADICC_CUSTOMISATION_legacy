// @ts-nocheck
import { describe, it, expect } from 'vitest';
import {
  COUNTRY_TEMPLATES,
  REGIONAL_IMPORT_ENDPOINT,
  getRegionalTemplate,
  getRegionalTemplateBySlug,
  getRegionalTemplateIds,
  getRegionalRouteSlugs,
  importDispatcher,
} from './regionalRegistry';

describe('regionalRegistry - COUNTRY_TEMPLATES', () => {
  it('exposes exactly 20 country templates', () => {
    // Wave 5 Epic I scope: au, br, ca, cn, cz, de, es, fr, in, it, jp, kr,
    // nl, nordic, pl, ru, tr, uae, uk, us. Adding country #21 means a new
    // entry + a new tradeSections array — nothing else.
    expect(COUNTRY_TEMPLATES.length).toBe(20);
  });

  it('every template has the load-bearing fields', () => {
    for (const tpl of COUNTRY_TEMPLATES) {
      expect(tpl.id).toBeTruthy();
      expect(tpl.routeSlug).toBeTruthy();
      expect(tpl.countryCode).toMatch(/^[A-Z]{2}$/);
      expect(tpl.flag.length).toBeGreaterThan(0);
      expect(tpl.label.length).toBeGreaterThan(0);
      expect(tpl.formatHint.length).toBeGreaterThan(0);
      expect(tpl.importEndpoint).toBe(REGIONAL_IMPORT_ENDPOINT);
      expect(Array.isArray(tpl.validatorPacks)).toBe(true);
      expect(tpl.validatorPacks).toContain('boq_quality');
      expect(tpl.excelTemplate).toBeDefined();
      expect(tpl.excelTemplate.requiredColumns).toContain('description');
      expect(tpl.excelTemplate.requiredColumns).toContain('quantity');
      expect(Array.isArray(tpl.tradeSections)).toBe(true);
      // every regional standard ships at least a handful of code/label rows
      expect(tpl.tradeSections.length).toBeGreaterThan(5);
    }
  });

  it('ids and routeSlugs are globally unique', () => {
    const ids = COUNTRY_TEMPLATES.map((t) => t.id);
    const slugs = COUNTRY_TEMPLATES.map((t) => t.routeSlug);
    expect(new Set(ids).size).toBe(ids.length);
    expect(new Set(slugs).size).toBe(slugs.length);
  });

  it('every routeSlug ends with -exchange (back-compat with v4.x bookmarks)', () => {
    for (const tpl of COUNTRY_TEMPLATES) {
      expect(tpl.routeSlug.endsWith('-exchange')).toBe(true);
    }
  });

  it('importDispatcher substitutes the BOQ id into the URL pattern', () => {
    const url = importDispatcher('boq-abc-123');
    expect(url).toBe('/v1/boq/boqs/boq-abc-123/import/auto/');
  });

  it('the four design-mandated samples are present (es-pbc / it-computo / uk-nrm / us-masterformat)', () => {
    const es = COUNTRY_TEMPLATES.find((t) => t.id === 'es-pbc');
    const it = COUNTRY_TEMPLATES.find((t) => t.id === 'it-computo');
    const uk = COUNTRY_TEMPLATES.find((t) => t.id === 'uk-nrm');
    const us = COUNTRY_TEMPLATES.find((t) => t.id === 'us-masterformat');
    expect(es?.sampleFile).toBe('/templates/es-pbc-sample.bc3');
    expect(it?.sampleFile).toBe('/templates/it-computo-sample.csv');
    expect(uk?.sampleFile).toBe('/templates/nrm-sample.csv');
    expect(us?.sampleFile).toBe('/templates/masterformat-sample.csv');
  });

  it('Spanish PBC template accepts .bc3 in addition to Excel', () => {
    const es = COUNTRY_TEMPLATES.find((t) => t.id === 'es-pbc');
    expect(es).toBeDefined();
    expect(es!.excelTemplate.acceptedExtensions).toContain('.bc3');
    expect(es!.excelTemplate.acceptedExtensions).toContain('.xlsx');
    expect(es!.validatorPacks).toContain('bc3');
  });

  it('UK NRM and US MasterFormat both use the masterformat / nrm validator packs', () => {
    const uk = COUNTRY_TEMPLATES.find((t) => t.id === 'uk-nrm');
    const us = COUNTRY_TEMPLATES.find((t) => t.id === 'us-masterformat');
    expect(uk!.validatorPacks).toContain('nrm');
    expect(us!.validatorPacks).toContain('masterformat');
  });
});

describe('regionalRegistry - lookup helpers', () => {
  it('getRegionalTemplate resolves a known id', () => {
    const tpl = getRegionalTemplate('de-din276');
    expect(tpl).toBeDefined();
    expect(tpl!.countryCode).toBe('DE');
    expect(tpl!.label).toMatch(/DIN 276/);
  });

  it('getRegionalTemplate returns undefined for unknown id', () => {
    expect(getRegionalTemplate('xx-fake')).toBeUndefined();
  });

  it('getRegionalTemplateBySlug resolves a known old-route slug', () => {
    const tpl = getRegionalTemplateBySlug('es-pbc-exchange');
    expect(tpl).toBeDefined();
    expect(tpl!.id).toBe('es-pbc');
    expect(tpl!.countryCode).toBe('ES');
  });

  it('getRegionalTemplateBySlug returns undefined for unknown slug', () => {
    expect(getRegionalTemplateBySlug('xx-fake-exchange')).toBeUndefined();
  });

  it('getRegionalTemplateIds returns all 20 country ids', () => {
    const ids = getRegionalTemplateIds();
    expect(ids).toHaveLength(20);
    expect(ids).toContain('au-acmm');
    expect(ids).toContain('br-sinapi');
    expect(ids).toContain('ca-masterformat');
    expect(ids).toContain('cn-gbt50500');
    expect(ids).toContain('cz-urs');
    expect(ids).toContain('de-din276');
    expect(ids).toContain('es-pbc');
    expect(ids).toContain('fr-dpgf');
    expect(ids).toContain('in-cpwd');
    expect(ids).toContain('it-computo');
    expect(ids).toContain('jp-sekisan');
    expect(ids).toContain('kr-poomsem');
    expect(ids).toContain('nl-stabu');
    expect(ids).toContain('nordic-ns3420');
    expect(ids).toContain('pl-knr');
    expect(ids).toContain('ru-gesn');
    expect(ids).toContain('tr-birimfiyat');
    expect(ids).toContain('uae-fidic');
    expect(ids).toContain('uk-nrm');
    expect(ids).toContain('us-masterformat');
  });

  it('getRegionalRouteSlugs returns all 20 old back-compat slugs', () => {
    const slugs = getRegionalRouteSlugs();
    expect(slugs).toHaveLength(20);
    expect(slugs).toContain('es-pbc-exchange');
    expect(slugs).toContain('uk-nrm-exchange');
    expect(slugs).toContain('us-masterformat-exchange');
    expect(slugs).toContain('de-din276-exchange');
  });
});

describe('regionalRegistry - validator regex', () => {
  it('Spanish PBC validator accepts chapter codes like "03", "03.001"', () => {
    const es = COUNTRY_TEMPLATES.find((t) => t.id === 'es-pbc');
    expect(es!.validateCode!('03')).toBe(true);
    expect(es!.validateCode!('03.001')).toBe(true);
    expect(es!.validateCode!('not-a-code')).toBe(false);
  });

  it('DIN 276 validator only accepts 3-digit Kostengruppen 100–799', () => {
    const de = COUNTRY_TEMPLATES.find((t) => t.id === 'de-din276');
    expect(de!.validateCode!('300')).toBe(true);
    expect(de!.validateCode!('330')).toBe(true);
    expect(de!.validateCode!('800')).toBe(false);
    expect(de!.validateCode!('30')).toBe(false);
  });

  it('MasterFormat validator accepts space-separated 2-digit codes', () => {
    const us = COUNTRY_TEMPLATES.find((t) => t.id === 'us-masterformat');
    expect(us!.validateCode!('03 30 00')).toBe(true);
    expect(us!.validateCode!('03')).toBe(true);
    expect(us!.validateCode!('not-a-code')).toBe(false);
  });

  it('NRM validator accepts dotted numeric element codes', () => {
    const uk = COUNTRY_TEMPLATES.find((t) => t.id === 'uk-nrm');
    expect(uk!.validateCode!('2.6.1')).toBe(true);
    expect(uk!.validateCode!('1')).toBe(true);
    expect(uk!.validateCode!('abc')).toBe(false);
  });

  it('GESN validator accepts dash-separated 2-digit Russian codes', () => {
    const ru = COUNTRY_TEMPLATES.find((t) => t.id === 'ru-gesn');
    expect(ru!.validateCode!('06-01-001')).toBe(true);
    expect(ru!.validateCode!('06')).toBe(true);
    expect(ru!.validateCode!('not-a-code')).toBe(false);
  });
});

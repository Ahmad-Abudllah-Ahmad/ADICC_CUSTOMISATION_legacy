// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Regional BOQ exchange registry — Wave 5 Epic I.
 *
 * Replaces 20 country-specific frontend modules (au, br, ca, cn, cz, de,
 * es, fr, in, it, jp, kr, nl, nordic, pl, ru, tr, uae, uk, us) with a
 * single polymorphic page driven by these entries.
 *
 * Each entry is a `RegionalTemplate`: it bundles the column mapping
 * (delegated to the existing `CountryTemplate`), the flag, the
 * native-language nav label, the format hint shown in the upload zone,
 * the trade-section reference table, an optional per-country code
 * validator, and a sample-file path served from `/public/templates/`.
 *
 * The `importEndpoint` points at the new dispatcher endpoint added by
 * the parallel backend Epic I-A wave. The endpoint expects `multipart/
 * form-data` with the raw file; the dispatcher auto-detects format and
 * the active country pack. For now the registry just supplies the URL
 * string — the polymorphic page POSTs to it.
 *
 * Adding a new country = adding one entry + one trade-section array.
 * No new React component, no new test file, no new manifest.
 */

import type { CountryTemplate } from '../_shared/templateTypes';

import type { TradeSection } from './data/tradeSections';
import {
  AU_TRADE_SECTIONS,
  BR_TRADE_SECTIONS,
  CA_TRADE_SECTIONS,
  CN_TRADE_SECTIONS,
  CZ_TRADE_SECTIONS,
  DE_TRADE_SECTIONS,
  ES_TRADE_SECTIONS,
  FR_TRADE_SECTIONS,
  IN_TRADE_SECTIONS,
  IT_TRADE_SECTIONS,
  JP_TRADE_SECTIONS,
  KR_TRADE_SECTIONS,
  MF_DIVISIONS,
  NL_TRADE_SECTIONS,
  NORDIC_TRADE_SECTIONS,
  NRM_ELEMENTS,
  PL_TRADE_SECTIONS,
  RU_TRADE_SECTIONS,
  TR_TRADE_SECTIONS,
  UAE_TRADE_SECTIONS,
} from './data/tradeSections';

/* ── Validators ─────────────────────────────────────────────────────────
 * Per-country classification-code regex validators. Each takes a string
 * and returns true if it matches the standard's canonical form. Used by
 * a future Validation@Import hook; kept colocated with the template so
 * country specialists can read pattern + validator side-by-side.
 */

const validators = {
  acmm: (code: string) => /^[A-Z](\d{1,4})?$/.test(code.trim()),
  sinapi: (code: string) => /^\d{2}(\.\d{1,5})?$/.test(code.trim()),
  caMasterformat: (code: string) => {
    const clean = code.replace(/\s+/g, ' ').trim();
    return /^\d{2}(\s\d{2}){0,2}$/.test(clean) || /^\d+(\.\d+){0,3}$/.test(clean);
  },
  gbt: (code: string) => /^(0[1-9]|1[0-5])$/.test(code.trim()),
  cz: (code: string) => /^\d{1,3}(\.\d{1,4}){0,3}(-\d{1,4})?$/.test(code.trim()),
  din276: (code: string) => /^[1-7]\d{2}$/.test(code.trim()),
  pbc: (code: string) => /^\d{2}(\.\d{1,4})?$/.test(code.trim()),
  lot: (code: string) => {
    const num = parseInt(code, 10);
    return !isNaN(num) && num >= 1 && num <= 99;
  },
  cpwd: (code: string) => /^(0[1-9]|1[0-7])$/.test(code.trim()),
  computo: (code: string) => /^\d{2}(\.\d{1,6})?$/.test(code.trim()),
  sekisan: (code: string) => /^\d{2}(\.\d{1,6})?$/.test(code.trim()),
  poomsem: (code: string) => /^\d{2}(\.\d{1,4})?$/.test(code.trim()),
  stabu: (code: string) => /^\d{2}(\.\d{1,4})?$/.test(code.trim()),
  nordic: (code: string) => {
    const clean = code.trim().toUpperCase();
    return /^[A-R]\d{0,2}(\.\d{1,3}){0,3}$/.test(clean) || /^AMA\.\d{2}(\.\d{1,3}){0,2}$/.test(clean);
  },
  knr: (code: string) => /^\d{2}(-\d{1,4})?$/.test(code.trim()),
  gesn: (code: string) => /^\d{2}(-\d{2}(-\d{3}(-\d{1,2})?)?)?$/.test(code.trim()),
  birimfiyat: (code: string) => /^\d{2}(\.\d{1,6})?$/.test(code.trim()),
  uae: (code: string) => {
    if (!code || code.trim().length === 0) return false;
    if (/^[A-Q](\.\d{1,3})*$/.test(code.trim())) return true;
    const parts = code.trim().split('.');
    if (parts.length === 0 || parts.length > 4) return false;
    return parts.every((p) => /^\d+$/.test(p));
  },
  nrm: (code: string) => {
    const parts = code.split('.');
    if (parts.length === 0 || parts.length > 4) return false;
    return parts.every((p) => /^\d+$/.test(p));
  },
  masterformat: (code: string) => {
    const clean = code.replace(/\s+/g, ' ').trim();
    return /^\d{2}(\s\d{2}){0,2}$/.test(clean);
  },
};

/* ── Registry entry shape ───────────────────────────────────────────── */

export interface RegionalTemplate {
  /** Stable ID used in deep-link routes (e.g. 'es-pbc'). */
  id: string;
  /** Old-route slug for back-compat (e.g. 'es-pbc-exchange'). */
  routeSlug: string;
  /** ISO 3166-1 alpha-2 country / regional code. */
  countryCode: string;
  /** Flag emoji shown in headers / nav (Nordic = Norwegian flag). */
  flag: string;
  /** Native nav label, e.g. 'Spain PBC / BC3'. */
  label: string;
  /** One-line hint shown in the file-drop zone (e.g. 'BC3 native or Excel template'). */
  formatHint: string;
  /**
   * Backend dispatcher URL — appended after the BOQ id. The polymorphic
   * page resolves `${importEndpoint}` with the target BOQ id substituted.
   *
   * The new endpoint `/v1/boq/boqs/{id}/import/auto/` is being delivered
   * by the parallel Epic I-A backend agent.
   */
  importEndpoint: string;
  /**
   * Validator packs to enable at import-time, by id. The backend reads
   * these and runs the matching ValidationRule set; the frontend just
   * forwards the list.
   */
  validatorPacks: string[];
  /** Excel column mapping (delegated to the existing `CountryTemplate`). */
  excelTemplate: CountryTemplate;
  /** Trade sections / chapters / divisions table shown after parse. */
  tradeSections: TradeSection[];
  /** Optional regex validator for the standard's classification code. */
  validateCode?: (code: string) => boolean;
  /** Public URL for a downloadable sample file (served from /public/templates/). */
  sampleFile?: string;
}

/* ── Country templates ──────────────────────────────────────────────── */

const baseColumns: CountryTemplate['defaultColumns'] = {
  ordinal: '0',
  description: '1',
  unit: '2',
  quantity: '3',
  unitRate: '4',
  total: '5',
  classification: '6',
};

function makeTemplate(
  id: string,
  name: string,
  country: string,
  countryCode: string,
  currency: string,
  currencySymbol: string,
  classification: string,
  overrides: Partial<CountryTemplate> = {},
): CountryTemplate {
  return {
    id,
    name,
    country,
    countryCode,
    currency,
    currencySymbol,
    classification,
    defaultColumns: baseColumns,
    requiredColumns: ['description', 'quantity'],
    acceptedExtensions: ['.csv', '.tsv', '.xlsx'],
    ...overrides,
  };
}

/* ── Registry ────────────────────────────────────────────────────────── */

const importDispatcher = (boqId: string): string =>
  `/v1/boq/boqs/${boqId}/import/auto/`;

/** New dispatcher endpoint pattern — the polymorphic page builds this URL per import. */
export const REGIONAL_IMPORT_ENDPOINT = '/v1/boq/boqs/{id}/import/auto/';

export { importDispatcher };

export const COUNTRY_TEMPLATES: RegionalTemplate[] = [
  {
    id: 'au-acmm',
    routeSlug: 'au-boq-exchange',
    countryCode: 'AU',
    flag: '🇦🇺',
    label: 'Australia ACMM / ANZSMM',
    formatHint: 'Excel / CSV with ACMM trade sections',
    importEndpoint: REGIONAL_IMPORT_ENDPOINT,
    validatorPacks: ['boq_quality', 'acmm'],
    excelTemplate: makeTemplate(
      'au-acmm',
      'Australian ACMM/ANZSMM',
      'Australia',
      'AU',
      'AUD',
      'A$',
      'ACMM',
    ),
    tradeSections: AU_TRADE_SECTIONS,
    validateCode: validators.acmm,
  },
  {
    id: 'br-sinapi',
    routeSlug: 'br-sinapi-exchange',
    countryCode: 'BR',
    flag: '🇧🇷',
    label: 'Brazil SINAPI / TCPO',
    formatHint: 'Excel / CSV in SINAPI / TCPO format',
    importEndpoint: REGIONAL_IMPORT_ENDPOINT,
    validatorPacks: ['boq_quality', 'sinapi'],
    excelTemplate: makeTemplate(
      'br-sinapi',
      'SINAPI / TCPO',
      'Brazil',
      'BR',
      'BRL',
      'R$',
      'SINAPI',
    ),
    tradeSections: BR_TRADE_SECTIONS,
    validateCode: validators.sinapi,
  },
  {
    id: 'ca-masterformat',
    routeSlug: 'ca-boq-exchange',
    countryCode: 'CA',
    flag: '🇨🇦',
    label: 'Canada MasterFormat / CIQS',
    formatHint: 'Excel / CSV in MasterFormat / CIQS format',
    importEndpoint: REGIONAL_IMPORT_ENDPOINT,
    validatorPacks: ['boq_quality', 'masterformat'],
    excelTemplate: makeTemplate(
      'ca-masterformat',
      'Canada MasterFormat/CIQS',
      'Canada',
      'CA',
      'CAD',
      'C$',
      'MasterFormat/CIQS',
    ),
    tradeSections: CA_TRADE_SECTIONS,
    validateCode: validators.caMasterformat,
  },
  {
    id: 'cn-gbt50500',
    routeSlug: 'cn-boq-exchange',
    countryCode: 'CN',
    flag: '🇨🇳',
    label: 'China GB/T 50500',
    formatHint: 'Excel / CSV in GB/T 50500 工程量清单 format',
    importEndpoint: REGIONAL_IMPORT_ENDPOINT,
    validatorPacks: ['boq_quality', 'gbt50500'],
    excelTemplate: makeTemplate(
      'cn-gbt50500',
      'GB/T 50500 工程量清单',
      'China',
      'CN',
      'CNY',
      '¥',
      'GB/T50500',
    ),
    tradeSections: CN_TRADE_SECTIONS,
    validateCode: validators.gbt,
  },
  {
    id: 'cz-urs',
    routeSlug: 'cz-boq-exchange',
    countryCode: 'CZ',
    flag: '🇨🇿',
    label: 'Czech URS / TSKP',
    formatHint: 'Excel / CSV in URS / TSKP format',
    importEndpoint: REGIONAL_IMPORT_ENDPOINT,
    validatorPacks: ['boq_quality', 'urs'],
    excelTemplate: makeTemplate(
      'cz-urs',
      'URS / TSKP',
      'Czech Republic',
      'CZ',
      'CZK',
      'Kč',
      'URS',
    ),
    tradeSections: CZ_TRADE_SECTIONS,
    validateCode: validators.cz,
  },
  {
    id: 'de-din276',
    routeSlug: 'de-din276-exchange',
    countryCode: 'DE',
    flag: '🇩🇪',
    label: 'Germany DIN 276 / ÖNORM / SIA',
    formatHint: 'Excel / CSV with DIN 276 Kostengruppen',
    importEndpoint: REGIONAL_IMPORT_ENDPOINT,
    validatorPacks: ['boq_quality', 'din276'],
    excelTemplate: makeTemplate(
      'de-din276',
      'DIN 276 / ÖNORM / SIA',
      'Germany/Austria/Switzerland',
      'DE',
      'EUR',
      '€',
      'DIN276',
    ),
    tradeSections: DE_TRADE_SECTIONS,
    validateCode: validators.din276,
  },
  {
    id: 'es-pbc',
    routeSlug: 'es-pbc-exchange',
    countryCode: 'ES',
    flag: '🇪🇸',
    label: 'Spanish PBC / BC3',
    formatHint: 'BC3 native or Excel template',
    importEndpoint: REGIONAL_IMPORT_ENDPOINT,
    validatorPacks: ['boq_quality', 'pbc', 'bc3'],
    excelTemplate: makeTemplate(
      'es-pbc',
      'PBC / Base de Precios',
      'Spain',
      'ES',
      'EUR',
      '€',
      'PBC',
      { acceptedExtensions: ['.csv', '.tsv', '.xlsx', '.bc3'] },
    ),
    tradeSections: ES_TRADE_SECTIONS,
    validateCode: validators.pbc,
    sampleFile: '/templates/es-pbc-sample.bc3',
  },
  {
    id: 'fr-dpgf',
    routeSlug: 'fr-dpgf-exchange',
    countryCode: 'FR',
    flag: '🇫🇷',
    label: 'France DPGF / DQE',
    formatHint: 'Excel / CSV in DPGF / DQE format with Lots techniques',
    importEndpoint: REGIONAL_IMPORT_ENDPOINT,
    validatorPacks: ['boq_quality', 'dpgf'],
    excelTemplate: makeTemplate(
      'fr-dpgf',
      'France DPGF/DQE',
      'France',
      'FR',
      'EUR',
      '€',
      'Lots',
      {
        defaultColumns: {
          ordinal: '0',
          description: '1',
          unit: '2',
          quantity: '3',
          unitRate: '4',
          total: '5',
          section: '6',
        },
      },
    ),
    tradeSections: FR_TRADE_SECTIONS,
    validateCode: validators.lot,
  },
  {
    id: 'in-cpwd',
    routeSlug: 'in-boq-exchange',
    countryCode: 'IN',
    flag: '🇮🇳',
    label: 'India CPWD / IS 1200 / SOR',
    formatHint: 'Excel / CSV in CPWD / IS 1200 / SOR format',
    importEndpoint: REGIONAL_IMPORT_ENDPOINT,
    validatorPacks: ['boq_quality', 'cpwd'],
    excelTemplate: makeTemplate(
      'in-cpwd',
      'CPWD / IS 1200 / SOR',
      'India',
      'IN',
      'INR',
      '₹',
      'CPWD',
    ),
    tradeSections: IN_TRADE_SECTIONS,
    validateCode: validators.cpwd,
  },
  {
    id: 'it-computo',
    routeSlug: 'it-computo-exchange',
    countryCode: 'IT',
    flag: '🇮🇹',
    label: 'Italy Computo Metrico / Prezzario DEI',
    formatHint: 'Excel / CSV in Computo Metrico format',
    importEndpoint: REGIONAL_IMPORT_ENDPOINT,
    validatorPacks: ['boq_quality', 'computo'],
    excelTemplate: makeTemplate(
      'it-computo',
      'Computo Metrico / Prezzario DEI',
      'Italy',
      'IT',
      'EUR',
      '€',
      'ComputoMetrico',
    ),
    tradeSections: IT_TRADE_SECTIONS,
    validateCode: validators.computo,
    sampleFile: '/templates/it-computo-sample.csv',
  },
  {
    id: 'jp-sekisan',
    routeSlug: 'jp-sekisan-exchange',
    countryCode: 'JP',
    flag: '🇯🇵',
    label: 'Japan 積算基準 (Sekisan Kijun)',
    formatHint: 'Excel / CSV in 積算基準 format',
    importEndpoint: REGIONAL_IMPORT_ENDPOINT,
    validatorPacks: ['boq_quality', 'sekisan'],
    excelTemplate: makeTemplate(
      'jp-sekisan',
      '積算基準 (Sekisan Kijun)',
      'Japan',
      'JP',
      'JPY',
      '¥',
      'Sekisan',
    ),
    tradeSections: JP_TRADE_SECTIONS,
    validateCode: validators.sekisan,
  },
  {
    id: 'kr-poomsem',
    routeSlug: 'kr-boq-exchange',
    countryCode: 'KR',
    flag: '🇰🇷',
    label: 'Korea 표준품셈 (Standard Estimating)',
    formatHint: 'Excel / CSV in 표준품셈 format',
    importEndpoint: REGIONAL_IMPORT_ENDPOINT,
    validatorPacks: ['boq_quality', 'poomsem'],
    excelTemplate: makeTemplate(
      'kr-poomsem',
      '표준품셈 (Standard Estimating)',
      'South Korea',
      'KR',
      'KRW',
      '₩',
      'Poomsem',
    ),
    tradeSections: KR_TRADE_SECTIONS,
    validateCode: validators.poomsem,
  },
  {
    id: 'nl-stabu',
    routeSlug: 'nl-stabu-exchange',
    countryCode: 'NL',
    flag: '🇳🇱',
    label: 'Netherlands STABU / RAW',
    formatHint: 'Excel / CSV in STABU / RAW format',
    importEndpoint: REGIONAL_IMPORT_ENDPOINT,
    validatorPacks: ['boq_quality', 'stabu'],
    excelTemplate: makeTemplate(
      'nl-stabu',
      'STABU / RAW',
      'Netherlands',
      'NL',
      'EUR',
      '€',
      'STABU',
    ),
    tradeSections: NL_TRADE_SECTIONS,
    validateCode: validators.stabu,
  },
  {
    id: 'nordic-ns3420',
    routeSlug: 'nordic-ns3420-exchange',
    countryCode: 'NO',
    flag: '🇳🇴',
    label: 'Nordic NS 3420 / AMA / V&S',
    formatHint: 'Excel / CSV in NS 3420 / AMA / V&S format',
    importEndpoint: REGIONAL_IMPORT_ENDPOINT,
    validatorPacks: ['boq_quality', 'ns3420'],
    excelTemplate: makeTemplate(
      'nordic-ns3420',
      'NS 3420 / AMA / V&S',
      'Nordic Countries',
      'NO',
      'NOK',
      'kr',
      'NS3420',
    ),
    tradeSections: NORDIC_TRADE_SECTIONS,
    validateCode: validators.nordic,
  },
  {
    id: 'pl-knr',
    routeSlug: 'pl-knr-exchange',
    countryCode: 'PL',
    flag: '🇵🇱',
    label: 'Poland KNR / KNNR',
    formatHint: 'Excel / CSV in KNR / KNNR format',
    importEndpoint: REGIONAL_IMPORT_ENDPOINT,
    validatorPacks: ['boq_quality', 'knr'],
    excelTemplate: makeTemplate(
      'pl-knr',
      'KNR / KNNR',
      'Poland',
      'PL',
      'PLN',
      'zł',
      'KNR',
    ),
    tradeSections: PL_TRADE_SECTIONS,
    validateCode: validators.knr,
  },
  {
    id: 'ru-gesn',
    routeSlug: 'ru-gesn-exchange',
    countryCode: 'RU',
    flag: '🇷🇺',
    label: 'Russia ГЭСН / ФЕР / ТЕР',
    formatHint: 'Excel / CSV in GESN / FER / TER format',
    importEndpoint: REGIONAL_IMPORT_ENDPOINT,
    validatorPacks: ['boq_quality', 'gesn'],
    excelTemplate: makeTemplate(
      'ru-gesn',
      'ГЭСН / ФЕР / ТЕР',
      'Russia',
      'RU',
      'RUB',
      '₽',
      'GESN',
    ),
    tradeSections: RU_TRADE_SECTIONS,
    validateCode: validators.gesn,
  },
  {
    id: 'tr-birimfiyat',
    routeSlug: 'tr-birimfiyat-exchange',
    countryCode: 'TR',
    flag: '🇹🇷',
    label: 'Turkey Bayındırlık Birim Fiyat',
    formatHint: 'Excel / CSV in Bayındırlık Birim Fiyat format',
    importEndpoint: REGIONAL_IMPORT_ENDPOINT,
    validatorPacks: ['boq_quality', 'birimfiyat'],
    excelTemplate: makeTemplate(
      'tr-birimfiyat',
      'Bayindirlik Birim Fiyat',
      'Turkey',
      'TR',
      'TRY',
      '₺',
      'BirimFiyat',
    ),
    tradeSections: TR_TRADE_SECTIONS,
    validateCode: validators.birimfiyat,
  },
  {
    id: 'uae-fidic',
    routeSlug: 'uae-boq-exchange',
    countryCode: 'AE',
    flag: '🇦🇪',
    label: 'UAE FIDIC / NRM-POMI',
    formatHint: 'Excel / CSV in FIDIC / NRM-POMI format',
    importEndpoint: REGIONAL_IMPORT_ENDPOINT,
    validatorPacks: ['boq_quality', 'nrm'],
    excelTemplate: makeTemplate(
      'uae-fidic',
      'UAE FIDIC / NRM-POMI',
      'United Arab Emirates',
      'AE',
      'AED',
      'د.إ',
      'NRM/POMI',
    ),
    tradeSections: UAE_TRADE_SECTIONS,
    validateCode: validators.uae,
  },
  {
    id: 'uk-nrm',
    routeSlug: 'uk-nrm-exchange',
    countryCode: 'GB',
    flag: '🇬🇧',
    label: 'United Kingdom NRM 1/2',
    formatHint: 'NRM 1/2 Excel template (UK cost-index compatible)',
    importEndpoint: REGIONAL_IMPORT_ENDPOINT,
    validatorPacks: ['boq_quality', 'nrm'],
    excelTemplate: makeTemplate(
      'uk-nrm',
      'UK NRM 1/2',
      'United Kingdom',
      'GB',
      'GBP',
      '£',
      'NRM',
    ),
    tradeSections: NRM_ELEMENTS,
    validateCode: validators.nrm,
    sampleFile: '/templates/nrm-sample.csv',
  },
  {
    id: 'us-masterformat',
    routeSlug: 'us-masterformat-exchange',
    countryCode: 'US',
    flag: '🇺🇸',
    label: 'United States CSI MasterFormat',
    formatHint: 'CSI MasterFormat Excel template',
    importEndpoint: REGIONAL_IMPORT_ENDPOINT,
    validatorPacks: ['boq_quality', 'masterformat'],
    excelTemplate: makeTemplate(
      'us-masterformat',
      'US MasterFormat',
      'United States',
      'US',
      'USD',
      '$',
      'MasterFormat',
    ),
    tradeSections: MF_DIVISIONS,
    validateCode: validators.masterformat,
    sampleFile: '/templates/masterformat-sample.csv',
  },
];

/* ── Lookup helpers ─────────────────────────────────────────────────── */

/** Resolve a registry entry by its `id` (e.g. 'es-pbc'). */
export function getRegionalTemplate(id: string): RegionalTemplate | undefined {
  return COUNTRY_TEMPLATES.find((t) => t.id === id);
}

/** Resolve a registry entry by old-route slug (e.g. 'es-pbc-exchange'). */
export function getRegionalTemplateBySlug(slug: string): RegionalTemplate | undefined {
  return COUNTRY_TEMPLATES.find((t) => t.routeSlug === slug);
}

/** All registered country IDs — useful for tests and routing. */
export function getRegionalTemplateIds(): string[] {
  return COUNTRY_TEMPLATES.map((t) => t.id);
}

/** All registered deep-link slugs — used by the compat-shim manifest. */
export function getRegionalRouteSlugs(): string[] {
  return COUNTRY_TEMPLATES.map((t) => t.routeSlug);
}

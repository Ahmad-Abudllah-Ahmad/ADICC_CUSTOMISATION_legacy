// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Construction cost benchmark data.
 *
 * Sources (typical planning benchmarks compiled from public datasets, not a live feed):
 * - German building-cost benchmark 2024 (Germany)
 * - Statistik Austria Baukostenindex 2024 (Austria)
 * - SIA / BFS Schweiz 2024 (Switzerland)
 * - UK construction cost index 2024 (United Kingdom)
 * - US construction cost index 2024 (United States)
 * - French unit-price reference 2024 (France)
 * - Bouwkosten Kompas 2024 (Netherlands)
 * - ITeC BEDEC 2024 (Spain)
 * - DEI Tipologie Edilizie 2024 (Italy)
 * - Rawlinsons Construction Handbook 2024 (Australia)
 * - Altus Construction Cost Guide 2024 (Canada)
 *
 * All values are cost per m2 GFA (gross floor area) for DIN 276 KG300+400
 * (construction works plus technical building systems). The KG300 vs KG400
 * split, the per-unit secondary metrics and the sample sizes are typical
 * planning values, not survey output. Actual costs vary by location,
 * specification and market conditions.
 */

export type BuildingType =
  | 'office'
  | 'hospital'
  | 'school'
  | 'residential_single'
  | 'residential_multi'
  | 'industrial'
  | 'retail'
  | 'hotel'
  | 'warehouse'
  | 'data_center'
  | 'laboratory'
  | 'car_park'
  | 'sports_facility'
  | 'senior_care';

export type BenchmarkRegion = 'DE' | 'AT' | 'CH' | 'UK' | 'US' | 'FR' | 'NL' | 'ES' | 'IT' | 'AU' | 'CA';

export type CurrencyCode = 'EUR' | 'CHF' | 'GBP' | 'USD' | 'AUD' | 'CAD';

/** DIN 276 KG300 (construction) vs KG400 (technical systems) split of the median. */
export interface CostGroupSplit {
  /** KG300 share of KG300+400, 0..1. */
  kg300Pct: number;
  /** KG400 share of KG300+400, 0..1. kg300Pct + kg400Pct === 1. */
  kg400Pct: number;
}

/** Per-unit secondary metric for a cell, when the unit is standard for the type. */
export interface SecondaryMetric {
  /** machine id, e.g. 'bed' | 'room' | 'pupil' | 'dwelling' */
  unitId: string;
  /** plain English label used as a t() defaultValue at render time */
  label: string;
  /** typical cost per secondary unit in the cell currency */
  median: number;
  /** typical area in m2 GFA assumed per secondary unit (basis for the median) */
  areaPerUnit: number;
  /** typical count assumed for a reference project of this type */
  typicalCount?: number;
}

export interface BenchmarkRange {
  /** Minimum observed cost/m2 */
  min: number;
  /** 25th percentile */
  q1: number;
  /** Median (50th percentile) */
  median: number;
  /** 75th percentile */
  q3: number;
  /** Maximum observed cost/m2 */
  max: number;

  /** KG300 vs KG400 split for this cell. */
  split: CostGroupSplit;
  /** per-unit secondary metric for this cell, when meaningful. */
  secondary?: SecondaryMetric;

  /** number of reference projects behind the cell. */
  sampleSize: number;
  /** confidence label derived from sampleSize + range spread + recency. */
  confidence: 'high' | 'medium' | 'low';

  /** provenance, e.g. 'German building-cost benchmark (2024)' */
  source: string;
  /** survey or publication year */
  sourceYear: number;
  /** currency of the values in this cell */
  currency: CurrencyCode;
}

export interface BuildingTypeInfo {
  id: BuildingType;
  label: string;
  description: string;
  /** plain English scope note rendered with a t() defaultValue. */
  scopeNote: string;
  /** machine id of the secondary unit this type carries, if any. */
  secondaryUnitId?: string;
  /** Typical unit label for secondary KPI (e.g. per bed, per pupil) */
  secondaryUnit?: string;
}

export const BUILDING_TYPES: BuildingTypeInfo[] = [
  {
    id: 'office',
    label: 'Office Building',
    description: 'Standard office, air-conditioned',
    scopeNote: 'KG300+400 per m2 GFA for a mid-spec air-conditioned office. Fit-out to shell-and-core standard.',
  },
  {
    id: 'hospital',
    label: 'Hospital',
    description: 'General hospital incl. surgery',
    scopeNote: 'General acute hospital with surgery and imaging. Per bed assumes about 85 m2 GFA per bed.',
    secondaryUnitId: 'bed',
    secondaryUnit: 'per bed',
  },
  {
    id: 'school',
    label: 'School / University',
    description: 'Education facility',
    scopeNote: 'Primary or secondary education facility. Per pupil place assumes about 10 m2 GFA per place.',
    secondaryUnitId: 'pupil',
    secondaryUnit: 'per pupil place',
  },
  {
    id: 'residential_single',
    label: 'Single Family House',
    description: 'Detached/semi-detached',
    scopeNote: 'Detached or semi-detached house. Per dwelling assumes about 140 m2 GFA per home.',
    secondaryUnitId: 'dwelling',
    secondaryUnit: 'per dwelling',
  },
  {
    id: 'residential_multi',
    label: 'Multi-Family Residential',
    description: 'Apartment building 4+ units',
    scopeNote: 'Apartment building of four units or more. Per dwelling assumes about 75 m2 GFA per flat.',
    secondaryUnitId: 'dwelling',
    secondaryUnit: 'per dwelling',
  },
  {
    id: 'industrial',
    label: 'Industrial / Factory',
    description: 'Light manufacturing',
    scopeNote: 'Light manufacturing hall with office annex. KG300-heavy, low technical share.',
  },
  {
    id: 'retail',
    label: 'Retail / Shopping',
    description: 'Retail space, shopping center',
    scopeNote: 'Retail or shopping space, shell plus base fit-out. Tenant fit-out excluded.',
  },
  {
    id: 'hotel',
    label: 'Hotel',
    description: '3-4 star hotel',
    scopeNote: '3 to 4 star hotel. Per room assumes about 48 m2 GFA per key incl. common areas.',
    secondaryUnitId: 'room',
    secondaryUnit: 'per room',
  },
  {
    id: 'warehouse',
    label: 'Warehouse / Logistics',
    description: 'Storage, distribution center',
    scopeNote: 'Storage or distribution shed. Mostly structure and envelope, minimal technical systems.',
  },
  {
    id: 'data_center',
    label: 'Data Center',
    description: 'Colocation / hyperscale',
    scopeNote:
      'Colocation or hyperscale data center. Power and cooling dominate the cost, so the technical share (KG400) is the highest of any type. Per m2 GFA of white space plus support areas.',
  },
  {
    id: 'laboratory',
    label: 'Laboratory / Research',
    description: 'Wet & dry labs, cleanrooms',
    scopeNote:
      'Research or teaching laboratory with fume extraction, gas and process services. Services-heavy; excludes movable lab equipment.',
  },
  {
    id: 'car_park',
    label: 'Car Park',
    description: 'Multi-storey / underground',
    scopeNote:
      'Multi-storey or underground parking structure. Mostly frame, deck and ramps with minimal services. Per space assumes about 30 m2 GFA per bay incl. circulation.',
    secondaryUnitId: 'space',
    secondaryUnit: 'per space',
  },
  {
    id: 'sports_facility',
    label: 'Sports & Leisure',
    description: 'Sports hall, pool, gym',
    scopeNote:
      'Indoor sports hall, pool or leisure center. Long spans and, for pools, heavy ventilation and water treatment lift the technical share.',
  },
  {
    id: 'senior_care',
    label: 'Senior Care Home',
    description: 'Assisted living, nursing',
    scopeNote:
      'Residential care or nursing home. Residential in form but with nurse call, higher servicing and accessibility. Per bed assumes about 55 m2 GFA per resident room incl. common areas.',
    secondaryUnitId: 'bed',
    secondaryUnit: 'per bed',
  },
];

export const BENCHMARK_REGIONS: { id: BenchmarkRegion; label: string; currency: CurrencyCode }[] = [
  { id: 'DE', label: 'Germany', currency: 'EUR' },
  { id: 'AT', label: 'Austria', currency: 'EUR' },
  { id: 'CH', label: 'Switzerland', currency: 'CHF' },
  { id: 'UK', label: 'United Kingdom', currency: 'GBP' },
  { id: 'US', label: 'United States', currency: 'USD' },
  { id: 'FR', label: 'France', currency: 'EUR' },
  { id: 'NL', label: 'Netherlands', currency: 'EUR' },
  { id: 'ES', label: 'Spain', currency: 'EUR' },
  { id: 'IT', label: 'Italy', currency: 'EUR' },
  { id: 'AU', label: 'Australia', currency: 'AUD' },
  { id: 'CA', label: 'Canada', currency: 'CAD' },
];

/* ── Modeling constants ─────────────────────────────────────────────────
 *
 * The dataset below is generated from the existing region x type medians and
 * a small set of typical-planning assumptions so the numbers stay internally
 * consistent: the KG split always sums to the median, and each secondary
 * metric is the median times a typical area per unit. Quartiles, source,
 * year and currency keep the original, reasonable values.
 */

/** Source quartiles per region x type (the original, reasonable ranges). */
const QUARTILES: Record<BenchmarkRegion, Record<BuildingType, [number, number, number, number, number]>> = {
  DE: {
    office: [1800, 2200, 2650, 3200, 4500],
    hospital: [3200, 3800, 4500, 5400, 7500],
    school: [2000, 2400, 2850, 3400, 4200],
    residential_single: [1600, 2000, 2400, 2900, 4000],
    residential_multi: [1800, 2100, 2500, 3000, 3800],
    industrial: [800, 1100, 1450, 1900, 2800],
    retail: [1200, 1600, 2000, 2500, 3500],
    hotel: [2200, 2800, 3400, 4200, 6000],
    warehouse: [500, 700, 950, 1300, 2000],
    data_center: [4500, 5800, 7000, 8800, 12000],
    laboratory: [2800, 3500, 4200, 5200, 7000],
    car_park: [500, 650, 800, 1050, 1500],
    sports_facility: [1700, 2100, 2600, 3300, 4600],
    senior_care: [2000, 2450, 2900, 3600, 4800],
  },
  AT: {
    office: [1900, 2350, 2800, 3400, 4800],
    hospital: [3400, 4000, 4700, 5600, 7800],
    school: [2100, 2550, 3000, 3600, 4500],
    residential_single: [1700, 2100, 2550, 3100, 4200],
    residential_multi: [1900, 2250, 2650, 3200, 4000],
    industrial: [850, 1150, 1500, 2000, 2900],
    retail: [1300, 1700, 2100, 2650, 3700],
    hotel: [2400, 3000, 3600, 4400, 6300],
    warehouse: [550, 750, 1000, 1350, 2100],
    data_center: [4700, 6000, 7300, 9100, 12500],
    laboratory: [2950, 3650, 4400, 5450, 7300],
    car_park: [530, 690, 850, 1100, 1600],
    sports_facility: [1800, 2200, 2750, 3450, 4800],
    senior_care: [2100, 2600, 3050, 3800, 5000],
  },
  CH: {
    office: [3200, 3900, 4600, 5500, 7500],
    hospital: [5500, 6500, 7800, 9200, 12000],
    school: [3500, 4200, 4900, 5800, 7200],
    residential_single: [2800, 3400, 4100, 5000, 7000],
    residential_multi: [3000, 3600, 4300, 5200, 6500],
    industrial: [1400, 1900, 2500, 3200, 4500],
    retail: [2200, 2800, 3400, 4200, 5800],
    hotel: [3800, 4600, 5600, 6800, 9500],
    warehouse: [900, 1200, 1600, 2100, 3200],
    data_center: [7500, 9500, 11500, 14000, 19000],
    laboratory: [4800, 6000, 7200, 8800, 11500],
    car_park: [900, 1150, 1450, 1850, 2700],
    sports_facility: [3000, 3700, 4500, 5500, 7500],
    senior_care: [3400, 4200, 5000, 6100, 8200],
  },
  UK: {
    office: [1500, 1850, 2200, 2700, 3800],
    hospital: [2800, 3300, 3900, 4700, 6500],
    school: [1700, 2050, 2400, 2900, 3600],
    residential_single: [1300, 1650, 2000, 2450, 3400],
    residential_multi: [1500, 1800, 2150, 2600, 3300],
    industrial: [650, 900, 1200, 1600, 2400],
    retail: [1000, 1350, 1700, 2150, 3000],
    hotel: [1900, 2400, 2900, 3600, 5100],
    warehouse: [400, 600, 800, 1100, 1700],
    data_center: [4000, 5100, 6200, 7800, 10500],
    laboratory: [2500, 3100, 3800, 4700, 6300],
    car_park: [450, 580, 720, 950, 1400],
    sports_facility: [1500, 1850, 2300, 2900, 4100],
    senior_care: [1750, 2150, 2600, 3200, 4300],
  },
  US: {
    office: [1800, 2300, 2800, 3500, 5000],
    hospital: [3500, 4200, 5000, 6000, 8500],
    school: [2000, 2500, 3000, 3600, 4500],
    residential_single: [1400, 1800, 2200, 2800, 4000],
    residential_multi: [1600, 2000, 2400, 3000, 3800],
    industrial: [800, 1100, 1500, 2000, 3000],
    retail: [1100, 1500, 1900, 2400, 3400],
    hotel: [2200, 2800, 3500, 4300, 6200],
    warehouse: [500, 700, 1000, 1400, 2200],
    data_center: [5000, 6500, 8000, 10000, 14000],
    laboratory: [3000, 3800, 4700, 5800, 7800],
    car_park: [500, 680, 850, 1150, 1700],
    sports_facility: [1700, 2150, 2700, 3400, 4800],
    senior_care: [2000, 2500, 3050, 3800, 5200],
  },
  FR: {
    office: [1650, 2050, 2450, 3000, 4200],
    hospital: [3000, 3600, 4300, 5200, 7200],
    school: [1900, 2300, 2750, 3300, 4100],
    residential_single: [1500, 1900, 2300, 2800, 3900],
    residential_multi: [1700, 2000, 2400, 2900, 3700],
    industrial: [750, 1050, 1400, 1850, 2700],
    retail: [1150, 1550, 1950, 2450, 3400],
    hotel: [2100, 2700, 3300, 4100, 5800],
    warehouse: [480, 680, 920, 1250, 1950],
    data_center: [4300, 5500, 6700, 8400, 11500],
    laboratory: [2700, 3350, 4050, 5000, 6800],
    car_park: [480, 620, 770, 1000, 1450],
    sports_facility: [1650, 2050, 2500, 3200, 4500],
    senior_care: [1900, 2350, 2800, 3500, 4700],
  },
  NL: {
    office: [1750, 2150, 2550, 3100, 4300],
    hospital: [3100, 3700, 4400, 5300, 7300],
    school: [1950, 2350, 2800, 3400, 4200],
    residential_single: [1550, 1950, 2350, 2850, 3950],
    residential_multi: [1750, 2050, 2450, 2950, 3750],
    industrial: [780, 1080, 1420, 1880, 2750],
    retail: [1200, 1600, 2000, 2500, 3450],
    hotel: [2150, 2750, 3350, 4150, 5850],
    warehouse: [500, 700, 950, 1300, 2000],
    data_center: [4400, 5600, 6800, 8500, 11700],
    laboratory: [2750, 3400, 4100, 5100, 6900],
    car_park: [500, 640, 800, 1050, 1500],
    sports_facility: [1700, 2100, 2600, 3300, 4600],
    senior_care: [1950, 2400, 2900, 3600, 4800],
  },
  ES: {
    office: [1150, 1400, 1700, 2150, 3000],
    hospital: [2100, 2550, 3050, 3700, 5200],
    school: [1300, 1600, 1950, 2400, 3100],
    residential_single: [1050, 1300, 1600, 2000, 2800],
    residential_multi: [1150, 1400, 1700, 2100, 2700],
    industrial: [550, 750, 1000, 1350, 2000],
    retail: [800, 1100, 1400, 1800, 2500],
    hotel: [1500, 1950, 2400, 3000, 4300],
    warehouse: [350, 480, 660, 920, 1450],
    data_center: [3200, 4100, 5000, 6300, 8700],
    laboratory: [1900, 2400, 2950, 3650, 5000],
    car_park: [350, 460, 580, 770, 1150],
    sports_facility: [1150, 1450, 1800, 2300, 3300],
    senior_care: [1350, 1700, 2050, 2600, 3500],
  },
  IT: {
    office: [1300, 1600, 1900, 2400, 3300],
    hospital: [2400, 2900, 3450, 4200, 5800],
    school: [1450, 1800, 2150, 2650, 3400],
    residential_single: [1150, 1450, 1750, 2200, 3050],
    residential_multi: [1300, 1600, 1900, 2350, 3000],
    industrial: [600, 850, 1150, 1500, 2250],
    retail: [900, 1250, 1600, 2050, 2850],
    hotel: [1700, 2200, 2700, 3400, 4800],
    warehouse: [400, 560, 760, 1050, 1650],
    data_center: [3600, 4600, 5600, 7000, 9600],
    laboratory: [2200, 2750, 3350, 4150, 5650],
    car_park: [400, 520, 660, 870, 1300],
    sports_facility: [1300, 1650, 2050, 2600, 3700],
    senior_care: [1550, 1950, 2350, 2950, 3950],
  },
  AU: {
    office: [2400, 2950, 3500, 4300, 5800],
    hospital: [4200, 5100, 6100, 7400, 10000],
    school: [2600, 3200, 3850, 4650, 5900],
    residential_single: [2000, 2500, 3050, 3750, 5100],
    residential_multi: [2300, 2800, 3350, 4050, 5200],
    industrial: [1050, 1450, 1900, 2500, 3600],
    retail: [1600, 2100, 2650, 3350, 4600],
    hotel: [2900, 3700, 4500, 5600, 7900],
    warehouse: [650, 900, 1250, 1700, 2600],
    data_center: [6000, 7700, 9400, 11800, 16000],
    laboratory: [3700, 4600, 5600, 6900, 9400],
    car_park: [650, 850, 1050, 1400, 2000],
    sports_facility: [2250, 2800, 3450, 4400, 6100],
    senior_care: [2600, 3250, 3900, 4850, 6500],
  },
  CA: {
    office: [2200, 2650, 3150, 3900, 5300],
    hospital: [3800, 4600, 5500, 6700, 9200],
    school: [2350, 2900, 3450, 4200, 5300],
    residential_single: [1800, 2250, 2750, 3400, 4700],
    residential_multi: [2050, 2500, 3000, 3650, 4700],
    industrial: [950, 1300, 1700, 2250, 3300],
    retail: [1450, 1900, 2400, 3000, 4200],
    hotel: [2600, 3300, 4050, 5000, 7100],
    warehouse: [580, 800, 1100, 1500, 2350],
    data_center: [5400, 6900, 8400, 10500, 14500],
    laboratory: [3300, 4100, 5000, 6200, 8400],
    car_park: [580, 760, 950, 1250, 1850],
    sports_facility: [2000, 2500, 3100, 3950, 5500],
    senior_care: [2300, 2900, 3500, 4350, 5850],
  },
};

/**
 * Typical DIN 276 KG400 (technical systems) share of KG300+400 by building
 * type. Same split applied across regions for a given type. These are
 * documented planning shares, not survey output. KG300 share is the
 * complement. Higher for services-dense buildings (hospitals), lower for
 * sheds (warehouse, industrial).
 */
const KG400_SHARE: Record<BuildingType, number> = {
  office: 0.28,
  hospital: 0.45,
  school: 0.3,
  residential_single: 0.22,
  residential_multi: 0.27,
  industrial: 0.16,
  retail: 0.24,
  hotel: 0.32,
  warehouse: 0.13,
  data_center: 0.55,
  laboratory: 0.42,
  car_park: 0.1,
  sports_facility: 0.3,
  senior_care: 0.3,
};

/** Typical m2 GFA per secondary unit, used to derive the per-unit median. */
const AREA_PER_UNIT: Partial<Record<BuildingType, { unitId: string; label: string; area: number; typicalCount: number }>> = {
  hospital: { unitId: 'bed', label: 'per bed', area: 85, typicalCount: 300 },
  hotel: { unitId: 'room', label: 'per room', area: 48, typicalCount: 150 },
  school: { unitId: 'pupil', label: 'per pupil place', area: 10, typicalCount: 600 },
  residential_single: { unitId: 'dwelling', label: 'per dwelling', area: 140, typicalCount: 1 },
  residential_multi: { unitId: 'dwelling', label: 'per dwelling', area: 75, typicalCount: 24 },
  car_park: { unitId: 'space', label: 'per space', area: 30, typicalCount: 400 },
  senior_care: { unitId: 'bed', label: 'per bed', area: 55, typicalCount: 80 },
};

/** Provenance per region (source string, year, currency). */
const PROVENANCE: Record<BenchmarkRegion, { source: string; sourceYear: number; currency: CurrencyCode }> = {
  DE: { source: 'German building-cost benchmark (2024)', sourceYear: 2024, currency: 'EUR' },
  AT: { source: 'Statistik Austria Baukostenindex 2024', sourceYear: 2024, currency: 'EUR' },
  CH: { source: 'SIA / BFS Schweiz 2024', sourceYear: 2024, currency: 'CHF' },
  UK: { source: 'UK construction cost index 2024', sourceYear: 2024, currency: 'GBP' },
  US: { source: 'US construction cost index (2024)', sourceYear: 2024, currency: 'USD' },
  FR: { source: 'French unit-price reference (2024)', sourceYear: 2024, currency: 'EUR' },
  NL: { source: 'Bouwkosten Kompas 2024', sourceYear: 2024, currency: 'EUR' },
  ES: { source: 'ITeC BEDEC 2024', sourceYear: 2024, currency: 'EUR' },
  IT: { source: 'DEI Tipologie Edilizie 2024', sourceYear: 2024, currency: 'EUR' },
  AU: { source: 'Rawlinsons Construction Handbook 2024', sourceYear: 2024, currency: 'AUD' },
  CA: { source: 'Altus Construction Cost Guide 2024', sourceYear: 2024, currency: 'CAD' },
};

/**
 * Plain-language cost drivers per region: why the numbers sit where they do.
 * Rendered as t() defaultValues. Not survey output, just orientation for a
 * reader comparing one market against another, referencing the standards and
 * conditions that actually move the numbers.
 */
export const REGION_DRIVERS: Record<BenchmarkRegion, string> = {
  DE: 'High labour cost and strict energy standards (GEG) hold the mid-band firm, while strong prefabrication and trade competition cap the top.',
  AT: 'Tracks Germany a little higher, with alpine logistics and high finishing standards in the western provinces.',
  CH: 'The most expensive market here: very high wages, a strong currency, seismic and comfort standards, and a small high-spec supplier base.',
  UK: 'A wide spread driven by London against the regions; labour availability and Part L energy upgrades push the technical share.',
  US: 'A large regional swing between coastal metros and inland; union versus open-shop labour and code (IBC) differences dominate.',
  FR: 'RE2020 low-carbon rules lift the technical band; costs sit a touch below Germany outside Paris.',
  NL: 'High ground and foundation costs (piling, high water table) and strict energy rules (BENG), plus dense-market logistics.',
  ES: 'Lower labour cost sets a lower base; seismic zones in the south and coastal exposure raise structural cost locally.',
  IT: 'Seismic design across much of the country and heritage constraints widen the range; labour below the north-European band.',
  AU: 'High wages, long supply lines and cyclone provisions in the north; a strong swing between metro and remote sites.',
  CA: 'Cold-climate envelope and mechanical loads, plus remoteness in the north; metro Toronto and Vancouver sit at the top.',
};

/**
 * Typical planning sample size per region x type. National published datasets
 * are large for common types, thinner for specialty buildings and smaller
 * markets. These are honest orders of magnitude, not exact survey counts.
 */
const SAMPLE_BASE: Record<BuildingType, number> = {
  office: 180,
  hospital: 55,
  school: 140,
  residential_single: 200,
  residential_multi: 170,
  industrial: 90,
  retail: 110,
  hotel: 60,
  warehouse: 120,
  data_center: 35,
  laboratory: 45,
  car_park: 95,
  sports_facility: 70,
  senior_care: 85,
};

/** Market-size factor on the sample base (bigger datasets in larger markets). */
const SAMPLE_REGION_FACTOR: Record<BenchmarkRegion, number> = {
  DE: 1.0,
  US: 1.0,
  UK: 0.85,
  AT: 0.55,
  CH: 0.45,
  FR: 0.8,
  NL: 0.6,
  ES: 0.65,
  IT: 0.7,
  AU: 0.6,
  CA: 0.6,
};

/* ── Derived helpers ────────────────────────────────────────────────── */

/**
 * Confidence label from sample size, range spread and source recency.
 * A large recent sample with a tight spread is high confidence. A thin or
 * dated sample, or a very wide spread, is low confidence.
 */
export function deriveConfidence(
  sampleSize: number,
  sourceYear: number,
  spread?: number,
): 'high' | 'medium' | 'low' {
  const currentYear = new Date().getFullYear();
  const age = Math.max(0, currentYear - sourceYear);

  let score = 0;
  if (sampleSize >= 120) score += 2;
  else if (sampleSize >= 60) score += 1;

  if (age <= 2) score += 1;
  else if (age >= 5) score -= 1;

  // spread is (max - min) / median; a wide band lowers confidence.
  if (spread !== undefined) {
    if (spread <= 1.2) score += 1;
    else if (spread >= 2.0) score -= 1;
  }

  if (score >= 3) return 'high';
  if (score >= 1) return 'medium';
  return 'low';
}

/** Split a cost/m2 figure into KG300 and KG400 components for a cell. */
export function splitByCostGroup(
  costPerM2: number,
  split: CostGroupSplit,
): { kg300: number; kg400: number } {
  const kg400 = costPerM2 * split.kg400Pct;
  return { kg300: costPerM2 - kg400, kg400 };
}

/* ── DIN 276 element-level breakdown ──────────────────────────────────────
 *
 * One level deeper than the KG300/KG400 split: the typical distribution of a
 * cost/m2 across the DIN 276 second-level element groups (310..390 within
 * KG300, 410..490 within KG400). These are documented *typical planning*
 * shares, not survey output - they let an estimator see roughly where the
 * money sits (facade vs slabs vs HVAC vs electrical) instead of a single bar.
 *
 * To stay honest and maintainable the shares are grouped into a handful of
 * building "profiles" rather than a full type x region matrix: a shed (heavy
 * structure, minimal services), a services-dense building (hospital/hotel),
 * residential, and a default (office/school/retail). Each profile's KG300 and
 * KG400 shares sum to 1.0.
 */

export type ElementProfile = 'default' | 'shed' | 'services_dense' | 'residential';

/** A DIN 276 element group share within its parent cost group (KG300 or KG400). */
export interface ElementShare {
  /** DIN 276 element code, e.g. '330'. */
  code: string;
  /** Plain English label, rendered via a t() defaultValue. */
  label: string;
  /** Share of the parent KG group, 0..1. */
  pct: number;
}

/** One element row of a concrete breakdown (already multiplied out to cost/m2). */
export interface ElementBreakdownRow {
  /** Parent cost group. */
  kg: 'KG300' | 'KG400';
  code: string;
  label: string;
  /** Share of the *total* KG300+400 cost/m2, 0..1. */
  pct: number;
  /** Cost per m2 attributed to this element group. */
  value: number;
}

const KG300_ELEMENTS: Record<ElementProfile, ElementShare[]> = {
  default: [
    { code: '310', label: 'Excavation & earthworks', pct: 0.05 },
    { code: '320', label: 'Foundations & substructure', pct: 0.12 },
    { code: '330', label: 'Exterior walls & facade', pct: 0.25 },
    { code: '340', label: 'Interior walls & partitions', pct: 0.15 },
    { code: '350', label: 'Floors, ceilings & slabs', pct: 0.2 },
    { code: '360', label: 'Roofs', pct: 0.1 },
    { code: '370', label: 'Built-in fixtures', pct: 0.05 },
    { code: '390', label: 'Other construction', pct: 0.08 },
  ],
  shed: [
    { code: '310', label: 'Excavation & earthworks', pct: 0.06 },
    { code: '320', label: 'Foundations & substructure', pct: 0.16 },
    { code: '330', label: 'Exterior walls & facade', pct: 0.3 },
    { code: '340', label: 'Interior walls & partitions', pct: 0.06 },
    { code: '350', label: 'Floors, ceilings & slabs', pct: 0.2 },
    { code: '360', label: 'Roofs', pct: 0.16 },
    { code: '370', label: 'Built-in fixtures', pct: 0.02 },
    { code: '390', label: 'Other construction', pct: 0.04 },
  ],
  services_dense: [
    { code: '310', label: 'Excavation & earthworks', pct: 0.04 },
    { code: '320', label: 'Foundations & substructure', pct: 0.11 },
    { code: '330', label: 'Exterior walls & facade', pct: 0.22 },
    { code: '340', label: 'Interior walls & partitions', pct: 0.18 },
    { code: '350', label: 'Floors, ceilings & slabs', pct: 0.21 },
    { code: '360', label: 'Roofs', pct: 0.08 },
    { code: '370', label: 'Built-in fixtures', pct: 0.08 },
    { code: '390', label: 'Other construction', pct: 0.08 },
  ],
  residential: [
    { code: '310', label: 'Excavation & earthworks', pct: 0.04 },
    { code: '320', label: 'Foundations & substructure', pct: 0.12 },
    { code: '330', label: 'Exterior walls & facade', pct: 0.24 },
    { code: '340', label: 'Interior walls & partitions', pct: 0.16 },
    { code: '350', label: 'Floors, ceilings & slabs', pct: 0.22 },
    { code: '360', label: 'Roofs', pct: 0.12 },
    { code: '370', label: 'Built-in fixtures', pct: 0.04 },
    { code: '390', label: 'Other construction', pct: 0.06 },
  ],
};

const KG400_ELEMENTS: Record<ElementProfile, ElementShare[]> = {
  default: [
    { code: '410', label: 'Plumbing, water & gas', pct: 0.16 },
    { code: '420', label: 'Heating', pct: 0.18 },
    { code: '430', label: 'Ventilation & cooling', pct: 0.2 },
    { code: '440', label: 'Electrical & power', pct: 0.22 },
    { code: '450', label: 'Telecom & IT', pct: 0.08 },
    { code: '460', label: 'Lifts & conveying', pct: 0.08 },
    { code: '480', label: 'Building automation', pct: 0.05 },
    { code: '490', label: 'Other technical', pct: 0.03 },
  ],
  shed: [
    { code: '410', label: 'Plumbing, water & gas', pct: 0.12 },
    { code: '420', label: 'Heating', pct: 0.14 },
    { code: '430', label: 'Ventilation & cooling', pct: 0.12 },
    { code: '440', label: 'Electrical & power', pct: 0.38 },
    { code: '450', label: 'Telecom & IT', pct: 0.06 },
    { code: '460', label: 'Lifts & conveying', pct: 0.04 },
    { code: '480', label: 'Building automation', pct: 0.04 },
    { code: '490', label: 'Other technical', pct: 0.1 },
  ],
  services_dense: [
    { code: '410', label: 'Plumbing, water & gas', pct: 0.14 },
    { code: '420', label: 'Heating', pct: 0.12 },
    { code: '430', label: 'Ventilation & cooling', pct: 0.26 },
    { code: '440', label: 'Electrical & power', pct: 0.22 },
    { code: '450', label: 'Telecom & IT', pct: 0.07 },
    { code: '460', label: 'Lifts & conveying', pct: 0.07 },
    { code: '470', label: 'Process / use-specific', pct: 0.06 },
    { code: '480', label: 'Building automation', pct: 0.04 },
    { code: '490', label: 'Other technical', pct: 0.02 },
  ],
  residential: [
    { code: '410', label: 'Plumbing, water & gas', pct: 0.22 },
    { code: '420', label: 'Heating', pct: 0.26 },
    { code: '430', label: 'Ventilation & cooling', pct: 0.1 },
    { code: '440', label: 'Electrical & power', pct: 0.2 },
    { code: '450', label: 'Telecom & IT', pct: 0.08 },
    { code: '460', label: 'Lifts & conveying', pct: 0.08 },
    { code: '480', label: 'Building automation', pct: 0.03 },
    { code: '490', label: 'Other technical', pct: 0.03 },
  ],
};

/** Map each building type to an element-distribution profile. */
const TYPE_ELEMENT_PROFILE: Record<BuildingType, ElementProfile> = {
  office: 'default',
  hospital: 'services_dense',
  school: 'default',
  residential_single: 'residential',
  residential_multi: 'residential',
  industrial: 'shed',
  retail: 'default',
  hotel: 'services_dense',
  warehouse: 'shed',
  data_center: 'services_dense',
  laboratory: 'services_dense',
  car_park: 'shed',
  sports_facility: 'default',
  senior_care: 'residential',
};

/**
 * Break a cost/m2 figure into DIN 276 element groups (310..490) using the
 * building type's typical element profile and its KG300/KG400 split. The row
 * values sum back to ``costPerM2``; ``pct`` is each element's share of the
 * total. Rows are returned in DIN code order; callers may re-sort by value.
 */
export function breakdownByElement(
  costPerM2: number,
  type: BuildingType,
  split: CostGroupSplit,
): ElementBreakdownRow[] {
  const profile = TYPE_ELEMENT_PROFILE[type];
  const kg300Total = costPerM2 * split.kg300Pct;
  const kg400Total = costPerM2 * split.kg400Pct;
  const rows: ElementBreakdownRow[] = [];
  for (const el of KG300_ELEMENTS[profile]) {
    const value = kg300Total * el.pct;
    rows.push({ kg: 'KG300', code: el.code, label: el.label, pct: costPerM2 > 0 ? value / costPerM2 : 0, value });
  }
  for (const el of KG400_ELEMENTS[profile]) {
    const value = kg400Total * el.pct;
    rows.push({ kg: 'KG400', code: el.code, label: el.label, pct: costPerM2 > 0 ? value / costPerM2 : 0, value });
  }
  return rows;
}

/**
 * Confidence label for a user value versus a cell: how trustworthy the
 * comparison is. Driven by the cell confidence, which already folds in
 * sample size, spread and recency.
 */
export function comparisonConfidence(range: BenchmarkRange): { label: string; key: string } {
  switch (range.confidence) {
    case 'high':
      return {
        key: 'benchmarks.cmp_conf_high',
        label: 'High, the reference cell rests on a broad recent sample',
      };
    case 'medium':
      return {
        key: 'benchmarks.cmp_conf_medium',
        label: 'Medium, treat the position as indicative',
      };
    default:
      return {
        key: 'benchmarks.cmp_conf_low',
        label: 'Low, the reference sample is thin or the spread is wide',
      };
  }
}

/* ── Build the BENCHMARKS table ─────────────────────────────────────── */

function buildRange(region: BenchmarkRegion, type: BuildingType): BenchmarkRange {
  const [min, q1, median, q3, max] = QUARTILES[region][type];
  const prov = PROVENANCE[region];

  const kg400Pct = KG400_SHARE[type];
  const kg300Pct = Math.round((1 - kg400Pct) * 100) / 100;

  const sampleSize = Math.round(SAMPLE_BASE[type] * SAMPLE_REGION_FACTOR[region]);
  const spread = median > 0 ? (max - min) / median : 0;
  const confidence = deriveConfidence(sampleSize, prov.sourceYear, spread);

  const range: BenchmarkRange = {
    min,
    q1,
    median,
    q3,
    max,
    split: { kg300Pct, kg400Pct },
    sampleSize,
    confidence,
    source: prov.source,
    sourceYear: prov.sourceYear,
    currency: prov.currency,
  };

  const unit = AREA_PER_UNIT[type];
  if (unit) {
    range.secondary = {
      unitId: unit.unitId,
      label: unit.label,
      median: Math.round(median * unit.area),
      areaPerUnit: unit.area,
      typicalCount: unit.typicalCount,
    };
  }

  return range;
}

const REGION_IDS: BenchmarkRegion[] = ['DE', 'AT', 'CH', 'UK', 'US', 'FR', 'NL', 'ES', 'IT', 'AU', 'CA'];
const TYPE_IDS: BuildingType[] = [
  'office',
  'hospital',
  'school',
  'residential_single',
  'residential_multi',
  'industrial',
  'retail',
  'hotel',
  'warehouse',
  'data_center',
  'laboratory',
  'car_park',
  'sports_facility',
  'senior_care',
];

/**
 * Benchmark data: BENCHMARKS[region][buildingType] = BenchmarkRange.
 * Values in the cell currency per m2 GFA.
 */
export const BENCHMARKS: Record<BenchmarkRegion, Record<BuildingType, BenchmarkRange>> = REGION_IDS.reduce(
  (acc, region) => {
    acc[region] = TYPE_IDS.reduce(
      (typeAcc, type) => {
        typeAcc[type] = buildRange(region, type);
        return typeAcc;
      },
      {} as Record<BuildingType, BenchmarkRange>,
    );
    return acc;
  },
  {} as Record<BenchmarkRegion, Record<BuildingType, BenchmarkRange>>,
);

/** Calculate percentile position of a value within a benchmark range (0-100). */
export function calculatePercentile(value: number, range: BenchmarkRange): number {
  if (value <= range.min) return 0;
  if (value >= range.max) return 100;

  // Piecewise linear interpolation between the 5 percentile points
  const points = [
    { pct: 0, val: range.min },
    { pct: 25, val: range.q1 },
    { pct: 50, val: range.median },
    { pct: 75, val: range.q3 },
    { pct: 100, val: range.max },
  ];

  for (let i = 1; i < points.length; i++) {
    const curr = points[i]!;
    if (value <= curr.val) {
      const prev = points[i - 1]!;
      const ratio = (value - prev.val) / (curr.val - prev.val);
      return prev.pct + ratio * (curr.pct - prev.pct);
    }
  }

  return 100;
}

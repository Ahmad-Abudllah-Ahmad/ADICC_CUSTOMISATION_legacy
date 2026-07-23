// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

/**
 * Global FX rates store — keyed by ISO 4217 currency code, values are
 * "1 unit of <code> in USD". Persists to localStorage so an estimator's
 * tweaks (or downloaded snapshot) survive across BOQs.
 *
 * The rates here are SEED defaults — approximate, deliberately not
 * live-fetched. An estimator who needs accuracy can edit any rate
 * inline from a resource row, and the new value sticks for every BOQ
 * on this device. A future patch can add a "refresh from upstream"
 * action if the team wires up a rates API.
 *
 * Project-level `fx_rates` (per-BOQ, set by the BOQ owner) still take
 * priority for conversion — this store is only the fallback.
 */
const SEED_RATES_VS_USD: Record<string, number> = {
  USD: 1.0,
  EUR: 1.07,
  GBP: 1.27,
  CHF: 1.13,
  JPY: 0.0064,
  CNY: 0.139,
  RUB: 0.011,
  INR: 0.012,
  CAD: 0.73,
  AUD: 0.66,
  NZD: 0.61,
  SGD: 0.74,
  HKD: 0.128,
  KRW: 0.00074,
  BRL: 0.197,
  MXN: 0.058,
  ZAR: 0.054,
  TRY: 0.029,
  PLN: 0.252,
  CZK: 0.043,
  HUF: 0.0028,
  SEK: 0.094,
  NOK: 0.092,
  DKK: 0.144,
  RON: 0.215,
  AED: 0.272,
  SAR: 0.267,
  QAR: 0.275,
  ILS: 0.273,
  THB: 0.029,
  IDR: 0.0000631,
  MYR: 0.221,
  PHP: 0.0177,
  VND: 0.0000405,
  // Approximate reference rates for the remaining picker currencies.
  // These exist only so the inversion sanity check has a magnitude to
  // compare against — they are rough mid-2020s figures, not for conversion.
  BGN: 0.556, // ~1.8 per USD
  HRK: 0.143, // ~7.0 per USD
  ISK: 0.00725, // ~138 per USD
  ARS: 0.001, // ~1000 per USD
  CLP: 0.00105, // ~950 per USD
  PEN: 0.267, // ~3.75 per USD
  COP: 0.00025, // ~4000 per USD
  BHD: 2.63, // ~0.38 per USD
  KWD: 3.23, // ~0.31 per USD
  OMR: 2.63, // ~0.38 per USD
  TWD: 0.0313, // ~32 per USD
  JOD: 1.41, // ~0.71 per USD
  LBP: 0.0000112, // ~89000 per USD
  PKR: 0.0036, // ~278 per USD
  BDT: 0.00909, // ~110 per USD
  LKR: 0.00333, // ~300 per USD
  EGP: 0.0208, // ~48 per USD
  NGN: 0.000667, // ~1500 per USD
  KES: 0.00775, // ~129 per USD
  MAD: 0.1, // ~10 per USD
  TND: 0.323, // ~3.1 per USD
  GHS: 0.0667, // ~15 per USD
  TZS: 0.000385, // ~2600 per USD
  UGX: 0.000263, // ~3800 per USD
  ETB: 0.0175, // ~57 per USD
  FJD: 0.444, // ~2.25 per USD
};

interface FxRatesState {
  /** Rate for 1 unit of `code` expressed in USD. */
  ratesVsUsd: Record<string, number>;
  setRate: (code: string, ratePerUsd: number) => void;
  removeRate: (code: string) => void;
  reset: () => void;
}

export const useFxRatesStore = create<FxRatesState>()(
  persist(
    (set) => ({
      ratesVsUsd: { ...SEED_RATES_VS_USD },
      setRate: (code, ratePerUsd) =>
        set((s) => ({
          ratesVsUsd: { ...s.ratesVsUsd, [code.toUpperCase()]: ratePerUsd },
        })),
      removeRate: (code) =>
        set((s) => {
          const next = { ...s.ratesVsUsd };
          delete next[code.toUpperCase()];
          return { ratesVsUsd: next };
        }),
      reset: () => set({ ratesVsUsd: { ...SEED_RATES_VS_USD } }),
    }),
    {
      name: 'oe-fx-rates-v1',
      // Builds up to v8.1.0 seeded ~34 currencies under this same key. zustand's
      // default persist merge is a shallow top-level spread, so a returning
      // user's stored ratesVsUsd map wholly replaces the expanded seed on
      // rehydration: the currencies added later (ARS, CLP, COP, LBP, ...) would
      // be absent, getFxRate returns undefined for them and the inversion guard
      // silently skips the very rates it was built to catch. Bump the version
      // and backfill any seed code the stored map lacks, without overwriting a
      // rate the user set themselves.
      version: 1,
      migrate: (persisted: unknown) => {
        const prev = (persisted ?? {}) as Partial<FxRatesState>;
        const stored = (prev.ratesVsUsd ?? {}) as Record<string, number>;
        return { ...prev, ratesVsUsd: { ...SEED_RATES_VS_USD, ...stored } };
      },
    },
  ),
);

/**
 * Get the rate for converting `from` → `to` using the global store.
 * Returns undefined when either currency has no entry.
 *
 * Math: rate(from→to) = rateVsUsd(from) / rateVsUsd(to)
 *   so 1 unit of `from` = (that result) units of `to`.
 */
export function getFxRate(
  from: string,
  to: string,
  ratesVsUsd: Record<string, number>,
): number | undefined {
  if (from === to) return 1;
  const fromUsd = ratesVsUsd[from];
  const toUsd = ratesVsUsd[to];
  if (typeof fromUsd !== 'number' || typeof toUsd !== 'number' || toUsd === 0) {
    return undefined;
  }
  return fromUsd / toUsd;
}

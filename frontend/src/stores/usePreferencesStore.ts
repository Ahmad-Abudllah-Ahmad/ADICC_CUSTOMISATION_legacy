// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * User preferences store.
 *
 * Centralizes regional/formatting settings used across the app:
 * currency, measurement system, date format, number format.
 *
 * Persists to localStorage so preferences survive page reloads, and hydrates
 * from the user's ACCOUNT on the server on boot (issue #335) so a preference
 * set on one device (e.g. imperial units) is honoured after a fresh login on
 * another. localStorage remains the offline cache.
 */

import { create } from 'zustand';
import { apiGet } from '@/shared/lib/api';

const STORAGE_KEY = 'oe_preferences';

export type MeasurementSystem = 'metric' | 'imperial';
export type DateFormat = 'DD.MM.YYYY' | 'MM/DD/YYYY' | 'YYYY-MM-DD';
export type NumberLocale = 'de-DE' | 'en-US' | 'en-GB' | 'fr-FR' | 'ru-RU' | 'ar-SA' | 'ja-JP' | 'zh-CN' | 'es-MX';

interface Preferences {
  currency: string;
  measurementSystem: MeasurementSystem;
  dateFormat: DateFormat;
  numberLocale: NumberLocale;
  vatRate: number;
  defaultRegion: string;
  defaultCurrency: string;
  defaultStandard: string;
}

const DEFAULTS: Preferences = {
  currency: 'EUR',
  measurementSystem: 'metric',
  dateFormat: 'DD.MM.YYYY',
  numberLocale: 'de-DE',
  vatRate: 19,
  defaultRegion: 'DACH',
  defaultCurrency: 'EUR',
  defaultStandard: 'din276',
};

function readPreferences(): Preferences {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULTS;
    return { ...DEFAULTS, ...JSON.parse(raw) };
  } catch {
    return DEFAULTS;
  }
}

function persist(prefs: Preferences) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
  } catch { /* ignore */ }
}

/* ── Server hydration (issue #335) ────────────────────────────────────── */

/** Shape of GET /v1/users/me/preferences/ (the account-level regional prefs). */
interface ServerPreferences {
  measurement_system?: string;
  date_format?: string;
  number_format?: string;
  currency_code?: string;
}

// Allow-lists so a server value is applied ONLY when it matches a value the
// store actually understands - a stray or future server value is skipped, never
// forced into the union.
const MEASUREMENT_SYSTEMS: readonly MeasurementSystem[] = ['metric', 'imperial'];
const DATE_FORMATS: readonly DateFormat[] = ['DD.MM.YYYY', 'MM/DD/YYYY', 'YYYY-MM-DD'];
// The account stores the number format as a display PATTERN, not a BCP-47
// locale; map the known patterns onto the locale the store formats with.
const NUMBER_FORMAT_TO_LOCALE: Record<string, NumberLocale> = {
  '1.234,56': 'de-DE',
  '1,234.56': 'en-US',
  '1 234,56': 'fr-FR',
};

interface PreferencesState extends Preferences {
  setPreference: <K extends keyof Preferences>(key: K, value: Preferences[K]) => void;
  setPreferences: (updates: Partial<Preferences>) => void;
  resetPreferences: () => void;
  /**
   * Load the account-level regional preferences from the server (issue #335)
   * and apply the ones this store understands, keeping localStorage as the
   * write-through offline cache. Safe to call once at boot; swallows any error
   * (offline / desktop without a reachable server) so the local cache stays
   * authoritative. A server value that does not match a known option is skipped
   * rather than forced in.
   */
  hydrateFromServer: () => Promise<void>;

  /** Format a number as currency using current settings */
  formatCurrency: (amount: number) => string;
  /** Format a number using current locale */
  formatNumber: (value: number, decimals?: number) => string;
}

export const usePreferencesStore = create<PreferencesState>((set, get) => ({
  ...readPreferences(),

  setPreference: (key, value) => {
    const next = { ...readPreferences(), [key]: value };
    persist(next);
    set({ [key]: value });
  },

  setPreferences: (updates) => {
    const current = get();
    const next = { ...current, ...updates };
    persist(next);
    set(updates);
  },

  resetPreferences: () => {
    persist(DEFAULTS);
    set(DEFAULTS);
  },

  hydrateFromServer: async () => {
    try {
      const r = await apiGet<ServerPreferences>('/v1/users/me/preferences/');
      const updates: Partial<Preferences> = {};
      if (r.measurement_system && (MEASUREMENT_SYSTEMS as readonly string[]).includes(r.measurement_system)) {
        updates.measurementSystem = r.measurement_system as MeasurementSystem;
      }
      if (r.date_format && (DATE_FORMATS as readonly string[]).includes(r.date_format)) {
        updates.dateFormat = r.date_format as DateFormat;
      }
      const mappedLocale = r.number_format ? NUMBER_FORMAT_TO_LOCALE[r.number_format] : undefined;
      if (mappedLocale) updates.numberLocale = mappedLocale;
      // An empty currency_code means "not chosen" on the account; only a real
      // ISO-4217 code overrides the local currency.
      if (r.currency_code && /^[A-Z]{3}$/.test(r.currency_code)) {
        updates.currency = r.currency_code;
        updates.defaultCurrency = r.currency_code;
      }
      if (Object.keys(updates).length === 0) return;
      // Write through to localStorage AND state, reusing the existing setter so
      // the persisted cache and the in-memory store stay in lockstep.
      get().setPreferences(updates);
    } catch {
      /* offline / desktop without a reachable server - keep the local cache */
    }
  },

  formatCurrency: (amount: number) => {
    const { currency, numberLocale } = get();
    const safe = /^[A-Z]{3}$/.test(currency) ? currency : 'EUR';
    try {
      return new Intl.NumberFormat(numberLocale, {
        style: 'currency',
        currency: safe,
        minimumFractionDigits: 0,
        maximumFractionDigits: 2,
      }).format(amount);
    } catch {
      return `${amount.toFixed(2)} ${safe}`;
    }
  },

  formatNumber: (value: number, decimals = 2) => {
    const { numberLocale } = get();
    try {
      return new Intl.NumberFormat(numberLocale, {
        minimumFractionDigits: 0,
        maximumFractionDigits: decimals,
      }).format(value);
    } catch {
      return value.toFixed(decimals);
    }
  },
}));

// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Canonical money primitives for the Decimal-as-string backend contract.
 *
 * The backend serialises every monetary value as a JSON *string* (a
 * `decimal.Decimal` rendered verbatim, e.g. `"1234.56"`) so large totals
 * round-trip without float precision loss and stay locale-neutral. The
 * TypeScript response types frequently declare these fields as `number`,
 * which is a lie: at runtime they arrive as strings. Calling `.toFixed()`
 * on that string throws (`"…".toFixed is not a function`), and a binary
 * `+` concatenates instead of adding. That mismatch is the single most
 * common money bug in this codebase (hundreds of historical `.toFixed`
 * crash sites).
 *
 * `toNum` is the one safe coercion primitive: it accepts whatever the wire
 * actually delivers (string | number | null | undefined), and never returns
 * `NaN`/`Infinity` — those degrade to `0` so downstream arithmetic and
 * `Intl.NumberFormat` can never blow up or render "NaN".
 *
 * `formatCurrency` is the locale-aware display formatter built on top of it.
 * Unlike a naive formatter it never hard-falls-back to EUR: rendering a
 * USD/BRL/JPY amount with a Euro sign actively misinforms the operator, so
 * an unknown/blank currency yields a plain grouped number with no symbol.
 */
import { getIntlLocale } from './formatters';

/** Options controlling the fraction-digit policy of {@link formatCurrency}. */
export interface FormatCurrencyOptions {
  /** Minimum fraction digits. Defaults to the currency's natural minor units. */
  minimumFractionDigits?: number;
  /** Maximum fraction digits. Defaults to the currency's natural minor units. */
  maximumFractionDigits?: number;
}

const CURRENCY_CODE_RE = /^[A-Z]{3}$/;

/**
 * Coerce a backend money value to a finite `number`, NaN-guarded.
 *
 * Accepts the Decimal-as-string the wire actually carries as well as a
 * genuine `number`. `null`, `undefined`, empty string, and any value that
 * does not parse to a finite number all collapse to `0` — never `NaN` or
 * `Infinity`, so callers can safely do arithmetic and `.toFixed()` on the
 * result.
 *
 * @param v The raw value (string | number | null | undefined).
 * @returns A finite number (`0` when the input is missing or unparseable).
 */
export function toNum(v: string | number | null | undefined): number {
  const n = typeof v === 'number' ? v : Number(v);
  return Number.isFinite(n) ? n : 0;
}

/**
 * Format a monetary value for display in the current (or given) locale.
 *
 * Coerces `v` via {@link toNum} first, so a Decimal-as-string is safe input.
 *
 * - A valid ISO 4217 `currency` renders with its symbol and (by default)
 *   its own minor-unit count (2 for EUR/USD, 0 for JPY, 3 for KWD…).
 * - A blank / unknown / malformed `currency` renders a plain grouped number
 *   with no symbol — never a wrong-currency symbol.
 * - `options` overrides the fraction-digit policy (e.g. whole-number
 *   summaries pass `{ maximumFractionDigits: 0 }`).
 * - Any `Intl` error falls back to a hand-rolled string so this never throws.
 *
 * @param v The value (Decimal-string or number).
 * @param currency Optional ISO 4217 code.
 * @param locale Optional BCP-47 locale tag; defaults to the active UI locale.
 * @param options Optional fraction-digit overrides.
 */
export function formatCurrency(
  v: string | number | null | undefined,
  currency?: string | null,
  locale?: string,
  options?: FormatCurrencyOptions,
): string {
  const amount = toNum(v);
  const loc = locale || getIntlLocale();
  const code = (currency || '').trim().toUpperCase();
  const isValid = CURRENCY_CODE_RE.test(code);

  if (!isValid) {
    // No reliable currency: grouped number, no symbol. Defaults to 2 fraction
    // digits (the common money case) unless the caller overrides.
    return new Intl.NumberFormat(loc, {
      minimumFractionDigits: options?.minimumFractionDigits ?? 2,
      maximumFractionDigits: options?.maximumFractionDigits ?? 2,
    }).format(amount);
  }

  try {
    return new Intl.NumberFormat(loc, {
      style: 'currency',
      currency: code,
      // Omitting both lets Intl use the currency's natural minor units.
      minimumFractionDigits: options?.minimumFractionDigits,
      maximumFractionDigits: options?.maximumFractionDigits,
    }).format(amount);
  } catch {
    const digits = options?.maximumFractionDigits ?? 2;
    return `${amount.toFixed(digits)} ${code}`;
  }
}

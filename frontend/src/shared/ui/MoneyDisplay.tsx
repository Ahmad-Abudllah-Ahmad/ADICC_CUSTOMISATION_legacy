// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import clsx from 'clsx';
import { useRef } from 'react';
import { usePreferencesStore } from '../../stores/usePreferencesStore';
import { currencyMinorUnits } from './currencyMinorUnits';

export interface MoneyDisplayProps {
  amount: number | string | null | undefined;
  currency?: string;
  compact?: boolean;
  showCode?: boolean;
  className?: string;
  colorize?: boolean;
}

/**
 * Locale-aware monetary value display.
 *
 * Uses the user's preferred locale and currency from the preferences store.
 * Supports compact notation (e.g. 1.2M), currency code suffix, and
 * colorized output (green/red) for positive/negative values.
 *
 * Audit I1-I3 fix: respects ISO-4217 minor-unit counts so JPY/KRW/IDR
 * render without decimals, BHD/KWD/OMR/TND render with three. The old
 * implementation hardcoded ``minimumFractionDigits=2``, which turned
 * "100 JPY" into "100.00 JPY" and "100 KWD" into "100.00 KWD" (losing
 * a fils of precision for the latter). When the browser's ``Intl``
 * has up-to-date currency data this would be a no-op — but we can't
 * rely on every supported browser/Node version having the latest
 * tables, hence the explicit overrides.
 *
 * Strict-currency policy (UX-audit fix): when neither the caller nor
 * the user preferences provide a currency, we no longer fall back to
 * EUR silently — a Saudi user with no project currency configured
 * would otherwise see Euros on every card. Instead the component
 * renders an em-dash with a "Currency not set" tooltip, surfacing the
 * configuration gap. In dev builds we also emit a single console
 * warning per component instance so call sites can be flushed out
 * organically.
 */
export function MoneyDisplay({
  amount,
  currency,
  compact = false,
  showCode = false,
  className,
  colorize = false,
}: MoneyDisplayProps) {
  // Selector-scoped read for numberLocale — without it the component
  // re-renders on every unrelated preferences-store mutation (v4.3 audit).
  // Note: we no longer read `currency` from the prefs store. The
  // user-preferences default (always 'EUR' for a fresh install) was
  // the source of the silent-EUR-fallback bug a Saudi user would hit
  // on every money cell. Caller must supply a `currency` prop.
  const numberLocale = usePreferencesStore((s) => s.numberLocale);

  // Dev-only one-shot warning when no currency is supplied by the caller.
  // Tracked per-instance so we don't spam the console on every re-render.
  const warnedMissingCurrencyRef = useRef(false);

  if (amount == null) {
    return <span className={clsx('text-content-tertiary', className)}>&mdash;</span>;
  }

  const numericValue = typeof amount === 'string' ? parseFloat(amount) : amount;

  if (Number.isNaN(numericValue)) {
    return <span className={clsx('text-content-tertiary', className)}>&mdash;</span>;
  }

  // Strict currency resolution — no silent EUR fallback. Treat
  // null / undefined / empty-string `currency` prop as "currency not
  // set" and surface an em-dash so the configuration gap is visible
  // rather than masked by a wrong currency symbol (a Saudi user with
  // no project currency configured would otherwise see Euros).
  const trimmedCurrency = typeof currency === 'string' ? currency.trim() : currency;
  if (!trimmedCurrency) {
    if (import.meta.env.DEV && !warnedMissingCurrencyRef.current) {
      warnedMissingCurrencyRef.current = true;
      // eslint-disable-next-line no-console
      console.warn('[MoneyDisplay] missing currency prop');
    }
    return (
      <span
        className={clsx('text-content-tertiary', className)}
        title="Currency not set"
      >
        &mdash;
      </span>
    );
  }

  // Validate ISO-4217 shape; a non-matching value (e.g. "us" lowercased,
  // or a numeric code) still means "misconfigured" so we surface the
  // same em-dash rather than guess at EUR.
  if (!/^[A-Z]{3}$/.test(trimmedCurrency)) {
    if (import.meta.env.DEV && !warnedMissingCurrencyRef.current) {
      warnedMissingCurrencyRef.current = true;
      // eslint-disable-next-line no-console
      console.warn(`[MoneyDisplay] invalid currency code: ${trimmedCurrency}`);
    }
    return (
      <span
        className={clsx('text-content-tertiary', className)}
        title="Currency not set"
      >
        &mdash;
      </span>
    );
  }

  const safeCurrency = trimmedCurrency;

  // Resolve the ISO-4217 minor-unit count. Falls back to 2 for currencies
  // we don't have an explicit override for — matching pre-fix behaviour
  // for the long tail of legacy/local-only currencies.
  const minorUnits = currencyMinorUnits(safeCurrency);

  let formatted: string;
  try {
    if (showCode) {
      // Format number without currency, then append ISO code
      const numFmt = new Intl.NumberFormat(numberLocale, {
        minimumFractionDigits: compact ? 0 : minorUnits,
        maximumFractionDigits: compact ? 1 : minorUnits,
        ...(compact ? { notation: 'compact' as const } : {}),
      });
      formatted = `${numFmt.format(numericValue)} ${safeCurrency}`;
    } else {
      const opts: Intl.NumberFormatOptions = {
        style: 'currency',
        currency: safeCurrency,
        minimumFractionDigits: compact ? 0 : minorUnits,
        maximumFractionDigits: compact ? 1 : minorUnits,
      };
      if (compact) {
        opts.notation = 'compact';
      }
      formatted = new Intl.NumberFormat(numberLocale, opts).format(numericValue);
    }
  } catch {
    // numericValue is guaranteed numeric (parseFloat above) but be paranoid
    // — Number.isFinite guards against ±Infinity sneaking past the NaN gate.
    const n = Number.isFinite(numericValue) ? numericValue : 0;
    formatted = `${n.toFixed(minorUnits)} ${safeCurrency}`;
  }

  const colorClass = colorize
    ? numericValue > 0
      ? 'text-semantic-success'
      : numericValue < 0
        ? 'text-semantic-error'
        : ''
    : '';

  return <span className={clsx(colorClass, className)}>{formatted}</span>;
}

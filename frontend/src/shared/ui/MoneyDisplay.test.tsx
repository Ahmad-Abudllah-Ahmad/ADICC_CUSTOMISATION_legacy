// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for <MoneyDisplay> — strict-currency formatter (Wave 2).
//
// Covers:
//   * Em-dash placeholder when amount is null / undefined / NaN.
//   * Em-dash placeholder when currency is missing or invalid
//     (Strict-currency policy — no silent EUR fallback).
//   * String-typed amount is parsed correctly (Decimal-as-string).
//   * amount=0 and negative amounts format correctly.
//   * Locale-aware formatting:
//       - en-US for USD → $1,234.56
//       - de-DE for EUR → uses comma separators (intl test environment
//         supplies the canonical Intl tables for these two pairs).
//   * Dev-mode console.warn fires exactly once per instance (re-render
//     does not re-warn) for missing or invalid currency.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';

import { MoneyDisplay } from './MoneyDisplay';
import { usePreferencesStore } from '@/stores/usePreferencesStore';

// Helper — set the locale on the store before render. The component
// reads numberLocale via a selector, so updates take effect on the
// next render.
function setLocale(locale: 'en-US' | 'de-DE' | 'ar-SA' | 'ja-JP') {
  usePreferencesStore.setState({ numberLocale: locale });
}

beforeEach(() => {
  // Default to en-US so most tests have a predictable comma/period
  // formatting that doesn't depend on the host's locale.
  setLocale('en-US');
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('MoneyDisplay - em-dash placeholders', () => {
  it('renders em-dash when amount is null', () => {
    const { container } = render(<MoneyDisplay amount={null} currency="USD" />);
    expect(container.textContent).toBe('—');
  });

  it('renders em-dash when amount is undefined', () => {
    const { container } = render(<MoneyDisplay amount={undefined} currency="USD" />);
    expect(container.textContent).toBe('—');
  });

  it('renders em-dash when amount is NaN (non-numeric string)', () => {
    const { container } = render(<MoneyDisplay amount="not-a-number" currency="USD" />);
    expect(container.textContent).toBe('—');
  });

  it('renders em-dash when currency is null', () => {
    const { container } = render(
      <MoneyDisplay amount={100} currency={null as unknown as string} />,
    );
    expect(container.textContent).toBe('—');
  });

  it('renders em-dash when currency is undefined', () => {
    const { container } = render(<MoneyDisplay amount={100} />);
    expect(container.textContent).toBe('—');
  });

  it('renders em-dash when currency is empty string', () => {
    const { container } = render(<MoneyDisplay amount={100} currency="" />);
    expect(container.textContent).toBe('—');
  });

  it('renders em-dash when currency is non-ISO shape (3 letters required)', () => {
    const { container } = render(<MoneyDisplay amount={100} currency="us" />);
    expect(container.textContent).toBe('—');
  });

  it('attaches a "Currency not set" tooltip when the gap is surfaced', () => {
    render(<MoneyDisplay amount={100} currency="" />);
    const span = screen.getByTitle('Currency not set');
    expect(span).toBeInTheDocument();
  });
});

describe('MoneyDisplay - valid currency formatting', () => {
  it('formats a positive integer amount with USD', () => {
    render(<MoneyDisplay amount={1234.56} currency="USD" />);
    // Intl renders "$1,234.56" — any whitespace variants from a future
    // CLDR are tolerated via regex.
    expect(screen.getByText(/\$1,234\.56/)).toBeInTheDocument();
  });

  it('formats amount=0 (does not get treated as "missing")', () => {
    render(<MoneyDisplay amount={0} currency="USD" />);
    expect(screen.getByText(/\$0\.00/)).toBeInTheDocument();
  });

  it('formats negative amounts with the minus sign', () => {
    render(<MoneyDisplay amount={-42} currency="USD" />);
    // en-US Intl renders negative as "-$42.00" (no space).
    expect(screen.getByText(/-\$42\.00/)).toBeInTheDocument();
  });

  it('accepts amount as a string (Decimal-as-string) and parses it', () => {
    render(<MoneyDisplay amount="1234.5" currency="USD" />);
    expect(screen.getByText(/\$1,234\.50/)).toBeInTheDocument();
  });

  it('uses de-DE locale separators when numberLocale = de-DE + EUR', () => {
    setLocale('de-DE');
    render(<MoneyDisplay amount={1234.56} currency="EUR" />);
    // de-DE EUR: "1.234,56 €" — match the digits + decimal comma.
    expect(screen.getByText(/1\.234,56/)).toBeInTheDocument();
  });

  it('respects ISO minor-units for JPY (0 decimals)', () => {
    render(<MoneyDisplay amount={1234} currency="JPY" />);
    // en-US: "¥1,234" with no decimal portion.
    expect(screen.getByText(/¥1,234/)).toBeInTheDocument();
    // Negative sanity: ensure no ".00" was appended.
    expect(screen.queryByText(/¥1,234\.00/)).toBeNull();
  });

  it('respects ISO minor-units for KWD (3 decimals)', () => {
    render(<MoneyDisplay amount={1.234} currency="KWD" showCode />);
    // showCode renders "<formatted> KWD"; KWD has 3 decimals.
    expect(screen.getByText(/1\.234 KWD/)).toBeInTheDocument();
  });

  it('appends the ISO code when showCode=true', () => {
    render(<MoneyDisplay amount={100} currency="USD" showCode />);
    expect(screen.getByText(/100\.00 USD/)).toBeInTheDocument();
  });

  it('colorizes positive amounts when colorize=true', () => {
    const { container } = render(
      <MoneyDisplay amount={50} currency="USD" colorize />,
    );
    expect(container.querySelector('.text-semantic-success')).not.toBeNull();
  });

  it('colorizes negative amounts with the error class when colorize=true', () => {
    const { container } = render(
      <MoneyDisplay amount={-50} currency="USD" colorize />,
    );
    expect(container.querySelector('.text-semantic-error')).not.toBeNull();
  });

  it('does NOT colorize zero (neutral)', () => {
    const { container } = render(
      <MoneyDisplay amount={0} currency="USD" colorize />,
    );
    expect(container.querySelector('.text-semantic-success')).toBeNull();
    expect(container.querySelector('.text-semantic-error')).toBeNull();
  });

  it('trims whitespace inside the currency prop', () => {
    render(<MoneyDisplay amount={100} currency="  USD  " />);
    expect(screen.getByText(/\$100\.00/)).toBeInTheDocument();
  });
});

describe('MoneyDisplay - dev console warnings (one-shot)', () => {
  it('emits exactly one console.warn when currency is missing, even on re-render', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const { rerender } = render(<MoneyDisplay amount={100} />);
    // Re-render the same component instance — the per-instance ref
    // should suppress further warnings.
    rerender(<MoneyDisplay amount={200} />);
    rerender(<MoneyDisplay amount={300} />);

    const calls = warn.mock.calls.filter((args) =>
      String(args[0] ?? '').includes('[MoneyDisplay]'),
    );
    expect(calls.length).toBe(1);
  });

  it('emits one warn for an invalid currency code, mentioning the offending value', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    render(<MoneyDisplay amount={100} currency="us" />);
    const calls = warn.mock.calls.filter((args) =>
      String(args[0] ?? '').includes('[MoneyDisplay]'),
    );
    expect(calls.length).toBe(1);
    expect(String(calls[0]?.[0] ?? '')).toContain('us');
  });

  it('does NOT emit a warning when a valid currency is supplied', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    render(<MoneyDisplay amount={100} currency="USD" />);
    const calls = warn.mock.calls.filter((args) =>
      String(args[0] ?? '').includes('[MoneyDisplay]'),
    );
    expect(calls.length).toBe(0);
  });
});

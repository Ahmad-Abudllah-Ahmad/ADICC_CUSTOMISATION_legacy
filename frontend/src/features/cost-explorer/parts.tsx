// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Small shared presentational helpers for the Cost Explorer tabs: money and
// percentage formatting, a compact 0..1 meter bar, and the region selector.

import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { getIntlLocale } from '@/shared/lib/formatters';
import { listRegions } from './api';

/**
 * Format a Decimal-as-string (or number) for display, optionally suffixed with
 * its currency code.
 *
 * Money and quantities arrive from the API as Decimal-compatible strings; this
 * coerces for DISPLAY only (never arithmetic) and groups the number in the
 * user's ACTIVE app locale via {@link getIntlLocale} - the same locale
 * primitive the shared formatCurrency / fmtNumber helpers use - so a German or
 * Turkish user sees "1.234,5" instead of the browser-default "1,234.5". A
 * missing value renders a dash (clearer than "0"); a non-numeric value is
 * echoed back untouched rather than shown as "NaN".
 */
export function fmtMoney(value: string | number | null | undefined, currency?: string): string {
  if (value === null || value === undefined || value === '') return currency ? `- ${currency}` : '-';
  const n = typeof value === 'number' ? value : Number(value);
  const body = Number.isFinite(n)
    ? new Intl.NumberFormat(getIntlLocale(), { maximumFractionDigits: 2 }).format(n)
    : String(value);
  return currency ? `${body} ${currency}` : body;
}

/** A 0..1 fraction as a whole percentage. */
export function pct(fraction: number): string {
  const f = Number.isFinite(fraction) ? fraction : 0;
  return `${Math.round(f * 100)}%`;
}

/** A signed percentage (already in percent units, e.g. -10 -> "-10%"). */
export function signedPct(value: number): string {
  const v = Number.isFinite(value) ? value : 0;
  const rounded = Math.round(v * 10) / 10;
  return `${rounded > 0 ? '+' : ''}${rounded}%`;
}

export type MeterTone = 'blue' | 'green' | 'amber';

/** Compact horizontal bar for a 0..1 value with a trailing label. */
export function Meter({ value, label, tone = 'blue' }: { value: number; label: string; tone?: MeterTone }) {
  const safe = Number.isFinite(value) ? value : 0;
  const w = Math.max(0, Math.min(1, safe)) * 100;
  const bar = tone === 'green' ? 'bg-semantic-success' : tone === 'amber' ? 'bg-semantic-warning' : 'bg-oe-blue';
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 shrink-0 overflow-hidden rounded-full bg-surface-tertiary">
        <div className={`h-full rounded-full ${bar}`} style={{ width: `${w}%` }} />
      </div>
      <span className="text-xs tabular-nums text-content-tertiary">{label}</span>
    </div>
  );
}

/** React Query hook for the loaded price bases. */
export function useRegions() {
  return useQuery({
    queryKey: ['cost-explorer', 'regions'],
    queryFn: listRegions,
    staleTime: 5 * 60_000,
  });
}

export interface RegionSelectProps {
  value: string;
  onChange: (region: string) => void;
  /** Label shown for the "no filter" option. */
  allLabel?: string;
  id?: string;
}

/** Dropdown of the loaded regions with an "All bases" option (value=''). */
export function RegionSelect({ value, onChange, allLabel, id }: RegionSelectProps) {
  const { t } = useTranslation();
  const { data: regions } = useRegions();
  return (
    <select
      id={id}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="h-9 w-full rounded-lg border border-border bg-surface-primary px-3 text-sm text-content-primary hover:border-content-tertiary focus:border-oe-blue focus:outline-none focus:ring-2 focus:ring-oe-blue/30"
      aria-label={t('costExplorer.region.label', { defaultValue: 'Price base region' })}
    >
      <option value="">{allLabel ?? t('costExplorer.region.all', { defaultValue: 'All bases' })}</option>
      {(regions ?? []).map((r) => (
        <option key={r} value={r}>
          {r}
        </option>
      ))}
    </select>
  );
}

/** Muted inline meta line: code · region · unit (skips empties). */
export function MetaLine({ parts }: { parts: Array<string | null | undefined> }) {
  const shown = parts.filter((p): p is string => Boolean(p && p.trim()));
  return <span className="text-xs text-content-tertiary">{shown.join('  ·  ')}</span>;
}

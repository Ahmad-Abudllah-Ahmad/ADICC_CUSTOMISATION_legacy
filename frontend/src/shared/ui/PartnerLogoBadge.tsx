// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * PartnerLogoBadge — co-branding strip shown on every page when a
 * partner pack is active.
 *
 * Variants:
 *  - "nav"      — slim chip with partner logo + "in partnership with X",
 *                 mounted in the top nav-bar center where space allows.
 *  - "dashboard" — wider banner with logo + powered-by line, mounted at
 *                 the top of the dashboard.
 *
 * Clicking the badge opens the in-app Partner Packs page
 * (``/modules?tab=partner-packs``) so the user can see what the active pack
 * configures, switch it, or reach the partner's website/contact shown there.
 *
 * Dismiss behaviour: the user can hide the badge for the current session
 * via a small ✕. We persist the dismissal to ``sessionStorage`` so it
 * comes back on next browser launch — matches the product spec ("logo
 * can be hidden but reappears on next launch").
 */

import { X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { usePartnerPack, partnerLogoUrl } from '@/shared/hooks/usePartnerPack';

const SESSION_DISMISS_KEY = 'partner-pack:dismissed';

/** In-app destination for the co-brand badge. */
const PACKS_ROUTE = '/modules?tab=partner-packs';

interface PartnerLogoBadgeProps {
  variant: 'nav' | 'dashboard';
  className?: string;
}

/** Two-letter monogram from the partner name, for the no-logo fallback. */
function partnerInitials(name: string): string {
  const words = name.trim().split(/[\s._-]+/).filter(Boolean);
  const letters =
    words.length >= 2
      ? `${words[0]?.[0] ?? ''}${words[1]?.[0] ?? ''}`
      : name.trim().slice(0, 2);
  return letters.toUpperCase() || '?';
}

export function PartnerLogoBadge({ variant, className = '' }: PartnerLogoBadgeProps) {
  const packQ = usePartnerPack();
  const [logoBroken, setLogoBroken] = useState(false);
  const [dismissed, setDismissed] = useState<boolean>(() => {
    try {
      return sessionStorage.getItem(SESSION_DISMISS_KEY) === '1';
    } catch {
      return false;
    }
  });

  useEffect(() => {
    if (dismissed) {
      try {
        sessionStorage.setItem(SESSION_DISMISS_KEY, '1');
      } catch {
        /* ignore — sessionStorage may be unavailable */
      }
    }
  }, [dismissed]);

  if (packQ.isLoading || !packQ.data?.active || dismissed) return null;

  const m = packQ.data.manifest!;
  // Brand colour (pack's primary). Only an exact 6-digit hex can synthesize the
  // alpha-tinted banner background; otherwise fall back to the app accent token
  // (a CSS var can't carry an alpha suffix).
  const brand = m.branding.primary_color || '';
  const isHex = /^#[0-9a-f]{6}$/i.test(brand);
  const accent = isHex ? brand : 'var(--accent)';
  const accentEnd = /^#[0-9a-f]{6}$/i.test(m.branding.accent_color ?? '')
    ? m.branding.accent_color!
    : accent;
  // Clearly-visible, brand-tinted background for the dashboard banner.
  const dashBg = isHex
    ? `linear-gradient(90deg, ${brand}26, ${brand}0d 55%, transparent)`
    : undefined;
  // Show the logo image only when the pack declares one AND it actually loads;
  // a declared-but-unreadable logo falls back to a brand-gradient monogram.
  const showLogo = m.branding.has_logo && !logoBroken;
  const initials = partnerInitials(m.partner_name);

  if (variant === 'nav') {
    return (
      <div
        className={`inline-flex items-center gap-2 rounded-full bg-surface-secondary/60 px-2.5 py-1 text-xs text-content-secondary backdrop-blur ${className}`}
        data-testid="partner-logo-nav"
      >
        <Link
          to={PACKS_ROUTE}
          className="inline-flex items-center gap-1.5 hover:text-content-primary"
          title={m.branding.powered_by_text}
        >
          {showLogo ? (
            <img
              src={partnerLogoUrl(m.slug)}
              alt={`${m.partner_name} logo`}
              className="h-5 w-5 shrink-0 rounded-[5px] object-contain"
              onError={() => setLogoBroken(true)}
            />
          ) : (
            <span
              className="flex h-5 w-5 shrink-0 items-center justify-center rounded-[5px] text-[9px] font-bold text-white"
              style={{ background: `linear-gradient(135deg, ${accent}, ${accentEnd})` }}
            >
              {initials}
            </span>
          )}
          <span className="max-w-[10rem] truncate font-medium">{m.partner_name}</span>
        </Link>
        <button
          type="button"
          aria-label="Hide partner badge"
          onClick={() => setDismissed(true)}
          className="rounded p-0.5 text-content-tertiary hover:text-content-primary hover:bg-surface-tertiary"
        >
          <X size={12} />
        </button>
      </div>
    );
  }

  // variant === 'dashboard'
  return (
    <div
      className={`flex items-center justify-between gap-3 rounded-lg border border-border border-l-[3px] bg-surface-secondary px-4 py-3 text-sm shadow-sm ${className}`}
      style={{ borderLeftColor: accent, backgroundImage: dashBg }}
      data-testid="partner-logo-dashboard"
    >
      <Link
        to={PACKS_ROUTE}
        className="flex min-w-0 items-center gap-3 hover:opacity-90"
        title={m.branding.powered_by_text}
      >
        {showLogo ? (
          <img
            src={partnerLogoUrl(m.slug)}
            alt={`${m.partner_name} logo`}
            className="h-11 w-11 shrink-0 rounded-xl object-contain shadow-sm ring-1 ring-black/5"
            onError={() => setLogoBroken(true)}
          />
        ) : (
          <span
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-base font-bold text-white shadow-sm"
            style={{ background: `linear-gradient(135deg, ${accent}, ${accentEnd})` }}
          >
            {initials}
          </span>
        )}
        <div className="min-w-0 leading-tight">
          <div className="text-sm font-semibold text-content-primary">{m.partner_name}</div>
          <div className="mt-0.5 text-2xs uppercase tracking-wide text-content-tertiary">
            {m.branding.powered_by_text}
          </div>
          {m.description && (
            <div className="mt-0.5 max-w-2xl truncate text-xs text-content-secondary">
              {m.description}
            </div>
          )}
        </div>
      </Link>
      <button
        type="button"
        aria-label="Hide partner badge"
        onClick={() => setDismissed(true)}
        className="shrink-0 rounded p-1 text-content-tertiary hover:text-content-primary hover:bg-surface-tertiary"
      >
        <X size={14} />
      </button>
    </div>
  );
}

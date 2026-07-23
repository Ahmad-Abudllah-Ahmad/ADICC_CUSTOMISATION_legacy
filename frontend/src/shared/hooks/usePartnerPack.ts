// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * usePartnerPack — read the active partner pack manifest.
 *
 * Returns ``{ active: false }`` when no pack is installed; otherwise
 * returns the manifest the backend exposes at
 * ``/api/v1/partner-pack/current``. Cached for 5 minutes — the active
 * pack only changes when the operator changes ``OE_PARTNER_PACK`` and
 * restarts.
 */

import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/shared/lib/api';

export interface PartnerPackBranding {
  primary_color: string;
  accent_color: string | null;
  has_logo: boolean;
  has_favicon: boolean;
  powered_by_text: string;
}

export interface PartnerPackManifest {
  slug: string;
  partner_name: string;
  partner_url: string | null;
  pack_version: string;
  description: string;
  default_locale: string;
  additional_locales: string[];
  cwicr_regions: string[];
  default_currency: string;
  default_tax_template: string | null;
  validation_rule_packs: string[];
  default_modules: string[];
  hidden_modules: string[];
  branding: PartnerPackBranding;
  has_onboarding_script: boolean;
  metadata: Record<string, unknown>;
}

export interface PartnerPackResponse {
  active: boolean;
  manifest?: PartnerPackManifest;
}

export function usePartnerPack() {
  return useQuery<PartnerPackResponse>({
    queryKey: ['partner-pack', 'current'],
    queryFn: () => apiGet<PartnerPackResponse>('/v1/partner-pack/current'),
    staleTime: 5 * 60_000,
    gcTime: 30 * 60_000,
    refetchOnWindowFocus: false,
  });
}

/**
 * Direct URL helper for the partner logo (no auth needed).
 *
 * Pass the active pack's ``slug`` to hit the by-slug endpoint, which resolves
 * the logo for BOTH pip-installed and source-checkout (in-app installed) packs.
 * The arg-less ``/logo`` endpoint only resolves pip-installed packs, so an
 * in-app one-click install would 404 and the badge ``<img>`` would break on
 * every page. Always pass the slug when you have it.
 */
export function partnerLogoUrl(slug?: string): string {
  return slug
    ? `/api/v1/partner-pack/logo/${encodeURIComponent(slug)}`
    : '/api/v1/partner-pack/logo';
}

// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * usePartnerPackLocale — force the active partner pack's UI language.
 *
 * A partner pack declares a ``default_locale`` (batimatech-ca ships ``fr-CA``
 * for French Canada). When the pack is active the whole app should present in
 * that language. This hook applies the pack's normalized locale once per
 * activation: it switches i18next, persists the choice, and records a marker so
 * it does not fight a user who later picks a different language from the header.
 *
 * Deactivation is handled by ``PartnerPackDeactivateDialog`` calling
 * ``resetPackLocale`` (reverts to English and clears the marker), so toggling a
 * pack on then off leaves the language exactly where it started.
 */

import { useEffect } from 'react';

import i18n, { loadLocaleResource, normalizePackLocale } from '@/app/i18n';

import { usePartnerPack } from './usePartnerPack';

/** localStorage marker: the slug of the pack whose locale we already forced. */
const PACK_LOCALE_MARKER = 'oce-pack-locale-active';

/**
 * Revert the UI language to English and clear the pack-locale marker.
 *
 * Called from the deactivate flow. Safe to call when no pack locale was ever
 * forced (it just sets English). localStorage failures are non-fatal.
 */
export async function resetPackLocale(): Promise<void> {
  try {
    window.localStorage.removeItem(PACK_LOCALE_MARKER);
    window.localStorage.setItem('i18nextLng', 'en');
  } catch {
    // localStorage unavailable (private browsing) — non-fatal.
  }
  await loadLocaleResource('en');
  await i18n.changeLanguage('en');
}

/**
 * Apply the active pack's language once per activation. Mount once, app-wide
 * (AppLayout). A no-op when no pack is active, when the pack's locale resolves
 * to English, or when this pack's locale was already forced this session.
 */
export function usePartnerPackLocale(): void {
  const { data } = usePartnerPack();

  useEffect(() => {
    if (!data?.active || !data.manifest) return;
    const slug = data.manifest.slug;
    const target = normalizePackLocale(data.manifest.default_locale);
    // Nothing to force when the pack speaks English.
    if (target === 'en') return;

    let alreadyForced = false;
    try {
      alreadyForced = window.localStorage.getItem(PACK_LOCALE_MARKER) === slug;
    } catch {
      alreadyForced = false;
    }
    // Force once per activation, so a later manual language pick sticks.
    if (alreadyForced) return;

    try {
      window.localStorage.setItem(PACK_LOCALE_MARKER, slug);
      window.localStorage.setItem('i18nextLng', target);
    } catch {
      // localStorage unavailable — the changeLanguage below still applies it
      // for this session.
    }
    void loadLocaleResource(target).then(() => i18n.changeLanguage(target));
  }, [data]);
}

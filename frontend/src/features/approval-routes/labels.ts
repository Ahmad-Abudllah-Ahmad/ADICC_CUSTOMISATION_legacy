// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Shared label helpers for the Approval Routes feature. Target kinds are
// raw snake_case on the wire (markup, change_order, purchase_order); the
// UI must show them localised and humanised ("Change order", "Purchase
// order") rather than verbatim.

import type { TFunction } from 'i18next';

/** Humanise a raw snake_case kind into Title-ish prose:
 *  ``change_order`` → ``Change order``. */
function prettify(kind: string): string {
  const spaced = kind.replace(/_/g, ' ').trim();
  if (!spaced) return kind;
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/** Localised, humanised label for a target kind. Looks up
 *  ``approvalRoutes.kind_<kind>`` and falls back to the prettified form. */
export function kindLabel(t: TFunction, kind: string): string {
  return t(`approvalRoutes.kind_${kind}`, { defaultValue: prettify(kind) });
}

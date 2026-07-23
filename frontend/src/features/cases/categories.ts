// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Cases - category metadata and the soft per-group colour palette.
//
// Each case belongs to one construction discipline (`CaseCategory`). This file
// is the single source of truth for the filter chips on the Cases hub AND for
// the very soft colour tint that visually groups cards and the runner header by
// discipline. Both `CasesPage` and `PlaybookRunner` import from here so the two
// views stay in step.
//
// The tint strings are FULL literal Tailwind classes on purpose: Tailwind's JIT
// only keeps classes it can see as complete tokens, so they must never be built
// by string concatenation. Tints are deliberately low-opacity - a hint of
// colour, not a paint job - and each carries a dark-mode text override.

import type { ComponentType } from 'react';
import {
  Calculator,
  PackageCheck,
  CalendarClock,
  Box,
  HardHat,
  BadgeCheck,
  FileSignature,
  ShieldCheck,
  type LucideProps,
} from 'lucide-react';
import type { CaseCategory } from './types';

/** The soft colour tint for one discipline, as ready-to-use class strings. */
export interface CategoryTint {
  /** Rounded icon tile: soft background, coloured glyph, faint ring. */
  tile: string;
  /** Active filter chip: soft background, coloured border and text. */
  chip: string;
  /** Colour of the thin left accent rail on a case card: a `border-l-*` colour
   *  class, combined at the call site with `border-l-[3px]` for the rail width. */
  accent: string;
  /** Very faint full-card wash in the same hue as the accent rail, layered under
   *  the card content so cards are easy to tell apart at a glance without the
   *  colour ever fighting the text. Kept lower opacity than the tile. Optional:
   *  only the discipline category tints (drawn behind case cards) set it; the
   *  company, role and stage picker-chip tints have no card wash and omit it. */
  softBg?: string;
  /** Plain coloured text for small eyebrow labels. */
  text: string;
}

export interface CategoryMeta {
  id: CaseCategory;
  labelKey: string;
  labelDefault: string;
  icon: ComponentType<LucideProps>;
  tint: CategoryTint;
}

/** Display order, labels, chip icon and soft tint for each discipline. Keep the
 *  ids aligned with the `CaseCategory` union in `types.ts`. */
export const CATEGORY_META: CategoryMeta[] = [
  {
    id: 'estimating',
    labelKey: 'cases.cat.estimating',
    labelDefault: 'Estimating & costing',
    icon: Calculator,
    tint: {
      tile: 'bg-emerald-500/10 text-emerald-600 ring-emerald-500/20 dark:text-emerald-400',
      chip: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
      accent: 'border-l-emerald-400/60',
      softBg: 'bg-emerald-400/5 dark:bg-emerald-400/10',
      text: 'text-emerald-600 dark:text-emerald-400',
    },
  },
  {
    id: 'tendering',
    labelKey: 'cases.cat.tendering',
    labelDefault: 'Tendering & procurement',
    icon: PackageCheck,
    tint: {
      tile: 'bg-violet-500/10 text-violet-600 ring-violet-500/20 dark:text-violet-400',
      chip: 'border-violet-500/40 bg-violet-500/10 text-violet-700 dark:text-violet-300',
      accent: 'border-l-violet-400/60',
      softBg: 'bg-violet-400/5 dark:bg-violet-400/10',
      text: 'text-violet-600 dark:text-violet-400',
    },
  },
  {
    id: 'planning',
    labelKey: 'cases.cat.planning',
    labelDefault: 'Planning & controls',
    icon: CalendarClock,
    tint: {
      tile: 'bg-sky-500/10 text-sky-600 ring-sky-500/20 dark:text-sky-400',
      chip: 'border-sky-500/40 bg-sky-500/10 text-sky-700 dark:text-sky-300',
      accent: 'border-l-sky-400/60',
      softBg: 'bg-sky-400/5 dark:bg-sky-400/10',
      text: 'text-sky-600 dark:text-sky-400',
    },
  },
  {
    id: 'bim',
    labelKey: 'cases.cat.bim',
    labelDefault: 'BIM & takeoff',
    icon: Box,
    tint: {
      tile: 'bg-indigo-500/10 text-indigo-600 ring-indigo-500/20 dark:text-indigo-400',
      chip: 'border-indigo-500/40 bg-indigo-500/10 text-indigo-700 dark:text-indigo-300',
      accent: 'border-l-indigo-400/60',
      softBg: 'bg-indigo-400/5 dark:bg-indigo-400/10',
      text: 'text-indigo-600 dark:text-indigo-400',
    },
  },
  {
    id: 'site',
    labelKey: 'cases.cat.site',
    labelDefault: 'Site & field',
    icon: HardHat,
    tint: {
      tile: 'bg-amber-500/10 text-amber-600 ring-amber-500/20 dark:text-amber-400',
      chip: 'border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300',
      accent: 'border-l-amber-400/60',
      softBg: 'bg-amber-400/5 dark:bg-amber-400/10',
      text: 'text-amber-600 dark:text-amber-400',
    },
  },
  {
    id: 'quality',
    labelKey: 'cases.cat.quality',
    labelDefault: 'Quality & safety',
    icon: BadgeCheck,
    tint: {
      tile: 'bg-teal-500/10 text-teal-600 ring-teal-500/20 dark:text-teal-400',
      chip: 'border-teal-500/40 bg-teal-500/10 text-teal-700 dark:text-teal-300',
      accent: 'border-l-teal-400/60',
      softBg: 'bg-teal-400/5 dark:bg-teal-400/10',
      text: 'text-teal-600 dark:text-teal-400',
    },
  },
  {
    id: 'commercial',
    labelKey: 'cases.cat.commercial',
    labelDefault: 'Commercial & contracts',
    icon: FileSignature,
    tint: {
      tile: 'bg-rose-500/10 text-rose-600 ring-rose-500/20 dark:text-rose-400',
      chip: 'border-rose-500/40 bg-rose-500/10 text-rose-700 dark:text-rose-300',
      accent: 'border-l-rose-400/60',
      softBg: 'bg-rose-400/5 dark:bg-rose-400/10',
      text: 'text-rose-600 dark:text-rose-400',
    },
  },
  {
    id: 'handover',
    labelKey: 'cases.cat.handover',
    labelDefault: 'Handover & lifecycle',
    icon: ShieldCheck,
    tint: {
      tile: 'bg-cyan-500/10 text-cyan-600 ring-cyan-500/20 dark:text-cyan-400',
      chip: 'border-cyan-500/40 bg-cyan-500/10 text-cyan-700 dark:text-cyan-300',
      accent: 'border-l-cyan-400/60',
      softBg: 'bg-cyan-400/5 dark:bg-cyan-400/10',
      text: 'text-cyan-600 dark:text-cyan-400',
    },
  },
];

/** Fast lookup of a category's metadata by id. */
export const CATEGORY_BY_ID: Record<CaseCategory, CategoryMeta> = Object.fromEntries(
  CATEGORY_META.map((c) => [c.id, c]),
) as Record<CaseCategory, CategoryMeta>;

/** Neutral tint used for the "All" chip and any unknown category, so the shared
 *  components always have a valid tint to render. */
export const NEUTRAL_TINT: CategoryTint = {
  tile: 'bg-oe-blue/10 text-oe-blue ring-oe-blue/20',
  chip: 'border-oe-blue/40 bg-oe-blue/10 text-oe-blue',
  accent: 'border-l-oe-blue/50',
  softBg: 'bg-oe-blue/5 dark:bg-oe-blue/10',
  text: 'text-oe-blue',
};

/** The tint for a category id, falling back to the neutral tint. */
export function tintFor(category: CaseCategory | undefined): CategoryTint {
  return category ? (CATEGORY_BY_ID[category]?.tint ?? NEUTRAL_TINT) : NEUTRAL_TINT;
}

// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
//
// Field-type metadata for the template builder + a light mirror of the backend
// validation engine (app/modules/forms/validation.py). The backend remains the
// source of truth - it re-validates on every write and every complete - but
// mirroring the rules here lets the builder show integrity problems live and
// the filler gate the Complete button without a round-trip.

import {
  Heading,
  Type,
  AlignLeft,
  Hash,
  CircleDot,
  ListChecks,
  CheckSquare,
  ShieldCheck,
  Star,
  Camera,
  PenLine,
  Calendar,
  type LucideIcon,
} from 'lucide-react';
import type { AnswerMap, AnswerValue, FieldType, FormFieldDef, TemplateCategory } from './api';

export interface FieldTypeMeta {
  type: FieldType;
  label: string;
  hint: string;
  icon: LucideIcon;
  /** Layout-only (no answer) - a section header. */
  layout?: boolean;
  /** Requires an options list. */
  hasOptions?: boolean;
  /** Has an optional measurement unit. */
  hasUnit?: boolean;
  /** Has a rating scale. */
  hasRating?: boolean;
}

/** Ordered palette - the order fields appear in the "add field" menu. */
export const FIELD_TYPES: FieldTypeMeta[] = [
  { type: 'section', label: 'Section header', hint: 'Group and title the fields below', icon: Heading, layout: true },
  { type: 'short_text', label: 'Short text', hint: 'A single line of text', icon: Type },
  { type: 'long_text', label: 'Paragraph', hint: 'Multi-line notes', icon: AlignLeft },
  { type: 'number', label: 'Number', hint: 'A measured value with an optional unit', icon: Hash, hasUnit: true },
  { type: 'single_choice', label: 'Single choice', hint: 'Pick one option', icon: CircleDot, hasOptions: true },
  { type: 'multi_choice', label: 'Multiple choice', hint: 'Pick any options', icon: ListChecks, hasOptions: true },
  { type: 'checkbox', label: 'Checkbox', hint: 'A single confirmation to tick', icon: CheckSquare },
  { type: 'pass_fail_na', label: 'Pass / Fail / NA', hint: 'The checklist workhorse', icon: ShieldCheck },
  { type: 'rating', label: 'Rating', hint: 'A star / numeric score', icon: Star, hasRating: true },
  { type: 'photo', label: 'Photo', hint: 'Attach photo evidence', icon: Camera },
  { type: 'signature', label: 'Signature', hint: 'Capture a signature', icon: PenLine },
  { type: 'date', label: 'Date', hint: 'A calendar date', icon: Calendar },
];

const META_BY_TYPE: Record<FieldType, FieldTypeMeta> = FIELD_TYPES.reduce(
  (acc, m) => {
    acc[m.type] = m;
    return acc;
  },
  {} as Record<FieldType, FieldTypeMeta>,
);

export function fieldMeta(type: FieldType): FieldTypeMeta {
  return META_BY_TYPE[type] ?? META_BY_TYPE.short_text;
}

export const CHOICE_TYPES: ReadonlySet<FieldType> = new Set<FieldType>(['single_choice', 'multi_choice']);
export const LAYOUT_TYPES: ReadonlySet<FieldType> = new Set<FieldType>(['section']);

export const RATING_MIN_SCALE = 2;
export const RATING_MAX_SCALE = 10;
export const DEFAULT_RATING_SCALE = 5;

export const CATEGORY_ORDER: TemplateCategory[] = [
  'safety',
  'quality',
  'handover',
  'inspection',
  'commissioning',
  'custom',
];

export const CATEGORY_LABELS: Record<TemplateCategory, string> = {
  safety: 'Safety',
  quality: 'Quality & acceptance',
  handover: 'Handover',
  inspection: 'Inspection',
  commissioning: 'Commissioning',
  custom: 'Custom',
};

/* -- Keys ------------------------------------------------------------------ */

export function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 60);
}

/**
 * Fill blank keys from labels and de-duplicate, mirroring
 * validation.normalize_fields so the client and server agree on keys before a
 * save. Never mutates the input.
 */
export function ensureFieldKeys(fields: FormFieldDef[]): FormFieldDef[] {
  const seen = new Set<string>();
  return fields.map((f, idx) => {
    let key = (f.key || '').trim() || slugify(f.label) || `field_${idx + 1}`;
    const base = key;
    let n = 2;
    while (seen.has(key)) {
      key = `${base}_${n}`;
      n += 1;
    }
    seen.add(key);
    return { ...f, key };
  });
}

/* -- Template integrity (mirror of validate_template_fields) --------------- */

export interface BuilderIssue {
  index: number;
  message: string;
}

export function validateTemplateFields(fields: FormFieldDef[]): BuilderIssue[] {
  const issues: BuilderIssue[] = [];
  if (fields.length === 0) {
    issues.push({ index: -1, message: 'Add at least one field.' });
    return issues;
  }
  let fillable = 0;
  fields.forEach((f, idx) => {
    if (!f.label.trim()) issues.push({ index: idx, message: 'Every field needs a label.' });
    if (!LAYOUT_TYPES.has(f.type)) fillable += 1;
    if (CHOICE_TYPES.has(f.type)) {
      const distinct = new Set((f.options ?? []).map((o) => o.trim()).filter(Boolean));
      if (distinct.size < 2) {
        issues.push({ index: idx, message: 'A choice field needs at least two options.' });
      }
    }
    if (f.type === 'rating') {
      const scale = f.max_rating ?? DEFAULT_RATING_SCALE;
      if (scale < RATING_MIN_SCALE || scale > RATING_MAX_SCALE) {
        issues.push({ index: idx, message: `Rating scale must be ${RATING_MIN_SCALE}-${RATING_MAX_SCALE}.` });
      }
    }
  });
  if (fillable === 0) {
    issues.push({ index: -1, message: 'Add at least one field to fill in, not only section headers.' });
  }
  return issues;
}

/* -- Submission completeness (mirror of _is_empty_answer) ------------------ */

export function isAnswerEmpty(type: FieldType, value: AnswerValue): boolean {
  if (value === null || value === undefined) return true;
  if (type === 'checkbox') return value !== true;
  if (type === 'multi_choice') {
    return !(Array.isArray(value) && value.filter((v) => String(v).trim()).length > 0);
  }
  if (type === 'photo') {
    if (Array.isArray(value)) return value.filter((v) => String(v).trim()).length === 0;
    return String(value).trim() === '';
  }
  if (type === 'signature') {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      const sig = value as { name?: string; data?: string };
      return !(String(sig.name ?? '').trim() || String(sig.data ?? '').trim());
    }
    return String(value).trim() === '';
  }
  if (typeof value === 'string') return value.trim() === '';
  return false;
}

/** Keys of required fields that are not yet answered (for progress + gating). */
export function missingRequiredKeys(fields: FormFieldDef[], answers: AnswerMap): string[] {
  const missing: string[] = [];
  for (const f of fields) {
    if (LAYOUT_TYPES.has(f.type) || !f.required) continue;
    if (isAnswerEmpty(f.type, answers[f.key] ?? null)) missing.push(f.key);
  }
  return missing;
}

/** Count of required fields (denominator for the completion meter). */
export function requiredCount(fields: FormFieldDef[]): number {
  return fields.filter((f) => !LAYOUT_TYPES.has(f.type) && f.required).length;
}

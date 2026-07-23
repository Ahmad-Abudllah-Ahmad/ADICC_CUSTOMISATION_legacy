// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Pure helpers for the basis-of-estimate panel: render the document to Markdown
// for the proposal export, build a safe download filename, and factory a blank
// manual line. Kept free of React and network so they unit-test without a
// browser. All user-facing labels are passed in (already translated) so nothing
// here hardcodes a display string.

import type { EstimateBasisDocument, QualificationCategory, QualificationItem } from './api';

/** Only the lines the estimator has left enabled. */
export function enabledItems(items: QualificationItem[]): QualificationItem[] {
  return items.filter((it) => it.enabled);
}

/** Translated section headings + boilerplate the Markdown render weaves in. */
export interface MarkdownLabels {
  inclusions: string;
  exclusions: string;
  assumptions: string;
  notes: string;
  none: string;
  status: string;
  generated: string;
}

/**
 * Render a basis-of-estimate document to Markdown for the proposal export.
 *
 * Mirrors the server-side render: title, a status/generated meta line, then the
 * three qualification sections with only the enabled lines, and any free-text
 * notes. Section headings arrive pre-translated so the export follows the
 * viewer's language.
 */
export function renderBasisMarkdown(doc: EstimateBasisDocument, labels: MarkdownLabels): string {
  const lines: string[] = [`# ${doc.title}`, ''];

  const meta = [`${labels.status}: ${doc.status}`];
  if (doc.generated_at) meta.push(`${labels.generated}: ${doc.generated_at}`);
  lines.push(`_${meta.join('  ·  ')}_`, '');

  const sections: Array<[string, QualificationItem[]]> = [
    [labels.inclusions, doc.inclusions],
    [labels.exclusions, doc.exclusions],
    [labels.assumptions, doc.assumptions],
  ];
  for (const [heading, items] of sections) {
    lines.push(`## ${heading}`);
    const on = enabledItems(items ?? []);
    if (on.length > 0) {
      for (const it of on) lines.push(`- ${it.text.trim()}`);
    } else {
      lines.push(`- ${labels.none}`);
    }
    lines.push('');
  }

  if (doc.notes && doc.notes.trim()) {
    lines.push(`## ${labels.notes}`, doc.notes.trim(), '');
  }

  return `${lines.join('\n').replace(/\s+$/, '')}\n`;
}

/**
 * Safe download filename for a document, mirroring the server export
 * (`basis_of_estimate_<title>.md`). Only filename-safe characters survive.
 */
export function basisFilename(title: string): string {
  const cleaned = (title || '')
    .trim()
    .replace(/[/\\]/g, '-')
    .replace(/\s+/g, '_')
    .replace(/[^A-Za-z0-9_-]/g, '')
    .slice(0, 80);
  return `basis_of_estimate_${cleaned || 'document'}.md`;
}

/**
 * A blank, user-added line for a section. The caller supplies the id (so the
 * factory stays deterministic and testable); the component uses a unique value.
 */
export function newManualItem(category: QualificationCategory, id: string): QualificationItem {
  return {
    id,
    category,
    text: '',
    trade_code: null,
    trade_label: null,
    basis: 'manual',
    source: 'manual',
    enabled: true,
  };
}

/** Generate a reasonably unique id for a new manual line at runtime. */
export function makeItemId(): string {
  const rand =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : Math.random().toString(36).slice(2);
  return `manual-${rand}`;
}

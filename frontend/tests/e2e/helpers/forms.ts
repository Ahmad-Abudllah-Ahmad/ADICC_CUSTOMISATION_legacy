/**
 * forms.ts — typed form filler for common patterns.
 *
 * Handles:
 *   - text inputs (by name|label|testid)
 *   - selects (native + react-select-ish custom)
 *   - date pickers (ISO yyyy-mm-dd → typed value)
 *   - checkboxes / radios
 *   - file uploads (single or multi)
 *   - multi-selects (token tags)
 *
 * Generic shape:
 *   await fillForm(page, {
 *     name: 'Wall paint',
 *     unit: { select: 'm²' },
 *     start_date: { date: '2026-06-01' },
 *     spec_pdf: { file: '/path/spec.pdf' },
 *     trades: { multiselect: ['painting', 'plastering'] },
 *     active: { checkbox: true },
 *   });
 */
import { type Page, type Locator } from '@playwright/test';

export type FieldValue =
  | string
  | number
  | boolean
  | { select: string }
  | { multiselect: string[] }
  | { date: string }
  | { file: string | string[] }
  | { checkbox: boolean }
  | { radio: string };

export interface FillFormOptions {
  /** Submit the form after filling? Default: false. */
  submit?: boolean;
  /** Custom submit button locator override. */
  submitButton?: Locator;
}

/** Find a form field by name|id|data-testid|label. Throws if none match. */
function fieldLocator(page: Page, name: string): Locator {
  const sel = [
    `[data-testid="field-${name}"]`,
    `[data-testid="${name}"]`,
    `[name="${name}"]`,
    `#${name}`,
  ].join(', ');
  return page.locator(sel).first();
}

async function fillText(page: Page, name: string, value: string): Promise<void> {
  const field = fieldLocator(page, name);
  // Some components are contenteditable / custom inputs; .fill works on both
  // <input>/<textarea>. For contenteditable, fallback to clicking + typing.
  const tag = await field.evaluate((el) => el.tagName).catch(() => '');
  if (tag === 'INPUT' || tag === 'TEXTAREA') {
    await field.fill(value);
  } else {
    await field.click();
    await page.keyboard.press('ControlOrMeta+A');
    await page.keyboard.type(value);
  }
}

async function selectOne(page: Page, name: string, value: string): Promise<void> {
  const field = fieldLocator(page, name);
  const tag = await field.evaluate((el) => el.tagName).catch(() => '');
  if (tag === 'SELECT') {
    await field.selectOption({ label: value }).catch(async () => {
      await field.selectOption(value);
    });
    return;
  }
  // Custom dropdown — open it, then click the matching option.
  await field.click();
  const option = page.locator(
    `[role="option"]:has-text("${value}"), [data-value="${value}"], li:has-text("${value}")`,
  ).first();
  await option.click();
}

async function selectMany(page: Page, name: string, values: string[]): Promise<void> {
  for (const v of values) {
    await selectOne(page, name, v);
  }
}

async function setDate(page: Page, name: string, iso: string): Promise<void> {
  const field = fieldLocator(page, name);
  const type = await field.getAttribute('type').catch(() => null);
  if (type === 'date' || type === 'datetime-local') {
    await field.fill(iso);
  } else {
    // Custom date picker — try typing into the underlying input.
    await field.click();
    await field.fill(iso);
    await page.keyboard.press('Escape');
  }
}

async function setCheckbox(page: Page, name: string, on: boolean): Promise<void> {
  const field = fieldLocator(page, name);
  if (on) await field.check();
  else await field.uncheck();
}

async function setRadio(page: Page, name: string, value: string): Promise<void> {
  const radio = page.locator(`input[type="radio"][name="${name}"][value="${value}"]`).first();
  await radio.check();
}

async function uploadFile(page: Page, name: string, paths: string | string[]): Promise<void> {
  const field = fieldLocator(page, name);
  await field.setInputFiles(paths);
}

export async function fillForm(
  page: Page,
  fields: Record<string, FieldValue>,
  opts: FillFormOptions = {},
): Promise<void> {
  for (const [name, value] of Object.entries(fields)) {
    if (value === null || value === undefined) continue;
    if (typeof value === 'string' || typeof value === 'number') {
      await fillText(page, name, String(value));
    } else if (typeof value === 'boolean') {
      await setCheckbox(page, name, value);
    } else if ('select' in value) {
      await selectOne(page, name, value.select);
    } else if ('multiselect' in value) {
      await selectMany(page, name, value.multiselect);
    } else if ('date' in value) {
      await setDate(page, name, value.date);
    } else if ('file' in value) {
      await uploadFile(page, name, value.file);
    } else if ('checkbox' in value) {
      await setCheckbox(page, name, value.checkbox);
    } else if ('radio' in value) {
      await setRadio(page, name, value.radio);
    }
  }
  if (opts.submit) {
    const btn = opts.submitButton ?? page.locator('button[type="submit"]').first();
    await btn.click();
  }
}

/**
 * Artifact helpers — every screenshot for the R6 property_dev suite
 * lands under ``.tests-artifacts/r6/property_dev/<scenario>/`` so the
 * runner can collect them without scraping the rest of the playwright
 * output dir.
 *
 * The shooter auto-numbers files inside a scenario directory so a
 * scenario reading like "01_login → 02_dashboard → 03_drawer" comes
 * out in lexical order regardless of when the caller fired.
 */
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import type { Page } from '@playwright/test';

const __dirname_esm = path.dirname(fileURLToPath(import.meta.url));
const ARTIFACT_ROOT = path.resolve(
  __dirname_esm,
  '..',
  '..',
  '..',
  '..',
  '.tests-artifacts',
  'r6',
  'property_dev',
);

export class Shooter {
  private counter = 1;
  private readonly outDir: string;
  readonly captured: string[] = [];

  constructor(scenario: string) {
    this.outDir = path.join(ARTIFACT_ROOT, scenario);
    fs.mkdirSync(this.outDir, { recursive: true });
  }

  /**
   * Capture a screenshot. ``label`` is appended to the auto-counter for
   * a human-readable filename (e.g. ``03_lead_created.png``).
   */
  async shoot(page: Page, label: string): Promise<string> {
    const safeLabel = label
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_+|_+$/g, '')
      .slice(0, 60);
    const n = String(this.counter).padStart(2, '0');
    this.counter += 1;
    const file = path.join(this.outDir, `${n}_${safeLabel || 'snap'}.png`);
    await page.screenshot({ path: file, fullPage: true });
    this.captured.push(file);
    return file;
  }

  /** Save a JSON blob (e.g. response body) alongside the screenshots. */
  saveJson(name: string, payload: unknown): string {
    const safe = name.toLowerCase().replace(/[^a-z0-9]+/g, '_').slice(0, 60);
    const file = path.join(this.outDir, `${safe}.json`);
    fs.writeFileSync(file, JSON.stringify(payload, null, 2), 'utf-8');
    this.captured.push(file);
    return file;
  }

  /** Save raw binary (e.g. decoded PDF) alongside the screenshots. */
  saveBinary(name: string, payload: Buffer): string {
    const safe = name.toLowerCase().replace(/[^a-z0-9]+/g, '_').slice(0, 60);
    const file = path.join(this.outDir, safe);
    fs.writeFileSync(file, payload);
    this.captured.push(file);
    return file;
  }

  get directory(): string {
    return this.outDir;
  }
}

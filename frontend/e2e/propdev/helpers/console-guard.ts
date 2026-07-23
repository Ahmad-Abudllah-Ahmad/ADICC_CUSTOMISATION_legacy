/**
 * Strict console / pageerror capture for the R6 property_dev suite.
 *
 * Why "strict"?
 *   - The task explicitly requires the zero-width Unicode regression
 *     (scenario #9) and the focus-trap stress (scenario #8) to fail on
 *     a SINGLE insertBefore / NotFoundError. The default playwright
 *     pattern of "scan logs at the end" allows races where a noisy
 *     unrelated console.warn buries a real DOM error.
 *
 * The guard exposes an ``attach(page)`` helper that subscribes to
 * console + pageerror events, collects everything, and returns an
 * ``assertNoStrictErrors()`` method the spec calls at the end.
 *
 * Tunables:
 *   - ``ignorePatterns`` skips common-but-noisy warnings that come
 *     from third-party libs (React-Query dev-tools, source-map missing
 *     in dev). Add new entries only when the regression evidence is
 *     reproducible and unrelated to the assertion under test.
 */
import type { ConsoleMessage, Page } from '@playwright/test';

export interface CapturedEntry {
  kind: 'console' | 'pageerror';
  type: string;
  text: string;
  url?: string;
  stack?: string;
  at: number;
}

const DEFAULT_IGNORE: RegExp[] = [
  // React-Query devtool noise in dev mode
  /\[ReactQuery\] /i,
  // Vite HMR pings
  /\[vite\] connect/i,
  /\[vite\] connecting/i,
  /\[HMR\] connected/i,
  // openestimate-toolbox preload warnings
  /preload was not used within a few seconds/i,
  // i18next fallback notifications (we test ar/he which legitimately
  // fall back for keys still pending translation)
  /i18next::translator: missingKey/i,
  // dev-mode prop-type warnings come from third-party libs we don't own
  /Warning: Each child in a list should have a unique "key" prop/i,
  // ResizeObserver loop noise — Chromium ships a benign 0-frame loop
  // notification that surfaces on every AG-Grid mount.
  /ResizeObserver loop /i,
];

/**
 * Patterns that — if seen even once — fail the scenario. These are the
 * regressions the task explicitly targets.
 */
const HARD_FAIL: RegExp[] = [
  /Failed to execute 'insertBefore'/i,
  /NotFoundError: The object can not be found here/i,
  /Cannot read properties of (null|undefined) \(reading 'insertBefore'\)/i,
  /Maximum update depth exceeded/i,
];

export class ConsoleGuard {
  readonly entries: CapturedEntry[] = [];
  readonly hardFailures: CapturedEntry[] = [];
  private detach: (() => void) | null = null;

  constructor(
    private readonly page: Page,
    private readonly options: { ignorePatterns?: RegExp[] } = {},
  ) {}

  attach(): void {
    const onConsole = (msg: ConsoleMessage) => {
      const text = msg.text();
      if (this.matches(text, [...DEFAULT_IGNORE, ...(this.options.ignorePatterns ?? [])])) {
        return;
      }
      const entry: CapturedEntry = {
        kind: 'console',
        type: msg.type(),
        text,
        url: msg.location().url,
        at: Date.now(),
      };
      this.entries.push(entry);
      if (this.matches(text, HARD_FAIL)) this.hardFailures.push(entry);
    };
    const onPageError = (err: Error) => {
      const entry: CapturedEntry = {
        kind: 'pageerror',
        type: 'error',
        text: err.message,
        stack: err.stack ?? undefined,
        at: Date.now(),
      };
      this.entries.push(entry);
      if (this.matches(err.message, HARD_FAIL)) this.hardFailures.push(entry);
    };
    this.page.on('console', onConsole);
    this.page.on('pageerror', onPageError);
    this.detach = () => {
      this.page.off('console', onConsole);
      this.page.off('pageerror', onPageError);
    };
  }

  release(): void {
    this.detach?.();
    this.detach = null;
  }

  /** Returns only the entries with type=error or pageerror. */
  errors(): CapturedEntry[] {
    return this.entries.filter(
      (e) => e.kind === 'pageerror' || e.type === 'error',
    );
  }

  /**
   * Throws when any HARD_FAIL pattern fired. Pass ``allowErrors=false``
   * to also fail on any console.error.
   */
  assertNoHardFailures(opts: { allowErrors?: boolean } = {}): void {
    if (this.hardFailures.length > 0) {
      const dump = this.hardFailures
        .map((e) => `  • [${e.kind}/${e.type}] ${e.text}`)
        .join('\n');
      throw new Error(
        `Console guard tripped ${this.hardFailures.length} hard-fail pattern(s):\n${dump}`,
      );
    }
    if (opts.allowErrors === false) {
      const errs = this.errors();
      if (errs.length > 0) {
        const dump = errs.map((e) => `  • [${e.kind}/${e.type}] ${e.text}`).join('\n');
        throw new Error(`Console guard: ${errs.length} error(s) captured:\n${dump}`);
      }
    }
  }

  private matches(text: string, patterns: RegExp[]): boolean {
    return patterns.some((re) => re.test(text));
  }
}

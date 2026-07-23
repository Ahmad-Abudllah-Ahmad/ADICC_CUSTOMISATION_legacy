// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
import { describe, it, expect, vi } from 'vitest';

import { DeferredTeardown } from '../deferredTeardown';

/**
 * DeferredTeardown is the primitive behind the BIM viewers' StrictMode
 * recovery (issue #347). These tests pin its contract with an injected,
 * manually-driven scheduler so the "remount cancels the deferred dispose and
 * the scene is reused" path is exercised without a real DOM or WebGL.
 */
describe('DeferredTeardown', () => {
  /** A scheduler we fire by hand, modelling "the next task ran". */
  function manual() {
    let queued: (() => void) | null = null;
    const scheduleFn = vi.fn((run: () => void) => {
      queued = run;
      return 1;
    });
    const cancelFn = vi.fn(() => {
      queued = null;
    });
    const td = new DeferredTeardown(scheduleFn, cancelFn);
    return {
      td,
      scheduleFn,
      cancelFn,
      fire: () => {
        const cb = queued;
        queued = null;
        cb?.();
      },
    };
  }

  it('runs the teardown when the timer fires (genuine unmount)', () => {
    const { td, fire } = manual();
    const dispose = vi.fn();
    td.schedule(dispose);
    expect(td.pending).toBe(true);
    expect(dispose).not.toHaveBeenCalled();
    fire();
    expect(dispose).toHaveBeenCalledTimes(1);
    expect(td.pending).toBe(false);
  });

  it('cancel() stops a pending teardown and reports it (remount reuse)', () => {
    const { td, fire } = manual();
    const dispose = vi.fn();
    td.schedule(dispose);
    expect(td.cancel()).toBe(true);
    expect(td.pending).toBe(false);
    fire(); // nothing is queued anymore
    expect(dispose).not.toHaveBeenCalled();
  });

  it('cancel() returns false when nothing is pending', () => {
    const { td } = manual();
    expect(td.cancel()).toBe(false);
  });

  it('models the StrictMode cycle: defer, cancel on remount, reuse, then real dispose', () => {
    const { td, fire } = manual();
    const dispose = vi.fn();
    // mount 1 cleanup defers the teardown of scene 1
    td.schedule(dispose);
    // StrictMode remount runs before the timer: cancel and reuse scene 1
    expect(td.cancel()).toBe(true);
    fire();
    expect(dispose).not.toHaveBeenCalled();
    // later, a genuine unmount defers teardown again - this time it fires
    td.schedule(dispose);
    fire();
    expect(dispose).toHaveBeenCalledTimes(1);
  });

  it('scheduling again cancels and replaces the previous pending teardown', () => {
    const { td, cancelFn, fire } = manual();
    const first = vi.fn();
    const second = vi.fn();
    td.schedule(first);
    td.schedule(second); // must cancel `first` before arming `second`
    expect(cancelFn).toHaveBeenCalledTimes(1);
    fire();
    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledTimes(1);
  });

  it('defaults to real timers when no scheduler is injected', async () => {
    const td = new DeferredTeardown();
    const dispose = vi.fn();
    td.schedule(dispose);
    expect(td.pending).toBe(true);
    await new Promise((resolve) => setTimeout(resolve, 5));
    expect(dispose).toHaveBeenCalledTimes(1);
    expect(td.pending).toBe(false);
  });
});

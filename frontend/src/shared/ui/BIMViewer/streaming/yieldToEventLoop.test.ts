// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
import { afterEach, describe, expect, it, vi } from 'vitest';

import { yieldToEventLoop } from './yieldToEventLoop';

/**
 * yieldToEventLoop picks the fastest available way to hand control back to the
 * browser between tile parses: scheduler.yield() when the engine has it, a
 * setTimeout macrotask otherwise. These tests pin that selection and the
 * never-reject contract, with the global scheduler stubbed either way so the
 * result does not depend on whether the test runtime happens to expose one.
 */
describe('yieldToEventLoop', () => {
  const g = globalThis as typeof globalThis & { scheduler?: { yield?: () => Promise<void> } };
  const original = Object.prototype.hasOwnProperty.call(g, 'scheduler') ? g.scheduler : undefined;
  const had = Object.prototype.hasOwnProperty.call(g, 'scheduler');

  afterEach(() => {
    if (had) g.scheduler = original;
    else delete g.scheduler;
    vi.restoreAllMocks();
  });

  it('uses scheduler.yield when the browser provides it', async () => {
    const y = vi.fn(() => Promise.resolve());
    g.scheduler = { yield: y };
    const spy = vi.spyOn(globalThis, 'setTimeout');
    await yieldToEventLoop();
    expect(y).toHaveBeenCalledTimes(1);
    expect(spy).not.toHaveBeenCalled();
  });

  it('falls back to a setTimeout macrotask when scheduler.yield is absent', async () => {
    delete g.scheduler;
    const spy = vi.spyOn(globalThis, 'setTimeout');
    await yieldToEventLoop();
    expect(spy).toHaveBeenCalled();
  });

  it('falls back when a scheduler exists without a yield method', async () => {
    g.scheduler = {};
    const spy = vi.spyOn(globalThis, 'setTimeout');
    await yieldToEventLoop();
    expect(spy).toHaveBeenCalled();
  });

  it('resolves (does not reject) when scheduler.yield rejects', async () => {
    g.scheduler = { yield: () => Promise.reject(new Error('task aborted')) };
    await expect(yieldToEventLoop()).resolves.toBeUndefined();
  });

  it('resolves so a streaming loop can await it in a tight pass', async () => {
    delete g.scheduler;
    await expect(yieldToEventLoop()).resolves.toBeUndefined();
  });
});

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  isOnline,
  subscribeConnectivity,
  emitConnectivityForTests,
} from './connectivity';

/** Set navigator.onLine for the duration of a test. */
function setOnLine(value: boolean): void {
  Object.defineProperty(navigator, 'onLine', {
    configurable: true,
    get: () => value,
  });
}

describe('connectivity - isOnline', () => {
  afterEach(() => {
    setOnLine(true);
  });

  it('reflects navigator.onLine when true', () => {
    setOnLine(true);
    expect(isOnline()).toBe(true);
  });

  it('reflects navigator.onLine when false', () => {
    setOnLine(false);
    expect(isOnline()).toBe(false);
  });
});

describe('connectivity - subscribe', () => {
  let unsub: (() => void) | null = null;

  beforeEach(() => {
    setOnLine(true);
  });

  afterEach(() => {
    unsub?.();
    unsub = null;
  });

  it('notifies a subscriber when going offline then online', () => {
    const seen: boolean[] = [];
    unsub = subscribeConnectivity((online) => seen.push(online));

    // Dispatch the real DOM events the store binds to.
    window.dispatchEvent(new Event('offline'));
    window.dispatchEvent(new Event('online'));

    expect(seen).toEqual([false, true]);
  });

  it('stops notifying after unsubscribe', () => {
    const cb = vi.fn();
    const off = subscribeConnectivity(cb);
    window.dispatchEvent(new Event('offline'));
    expect(cb).toHaveBeenCalledTimes(1);

    off();
    window.dispatchEvent(new Event('online'));
    expect(cb).toHaveBeenCalledTimes(1); // not called again
  });

  it('supports multiple independent subscribers', () => {
    const a = vi.fn();
    const b = vi.fn();
    const offA = subscribeConnectivity(a);
    const offB = subscribeConnectivity(b);

    emitConnectivityForTests(false);
    expect(a).toHaveBeenCalledWith(false);
    expect(b).toHaveBeenCalledWith(false);

    offA();
    emitConnectivityForTests(true);
    expect(a).toHaveBeenCalledTimes(1); // a removed
    expect(b).toHaveBeenLastCalledWith(true);
    offB();
  });

  it('a subscriber that unsubscribes during dispatch does not break others', () => {
    const order: string[] = [];
    let offSelf: (() => void) | null = null;
    const offFirst = subscribeConnectivity(() => {
      order.push('first');
      offSelf?.(); // remove self mid-dispatch
    });
    offSelf = offFirst;
    const offSecond = subscribeConnectivity(() => order.push('second'));

    emitConnectivityForTests(false);

    expect(order).toContain('first');
    expect(order).toContain('second');
    offSecond();
  });
});

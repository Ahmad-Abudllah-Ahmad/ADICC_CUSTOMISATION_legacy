/**
 * CameraTween unit tests (W6.6).
 *
 * Verifies the cubic ease curve, per-frame interpolation, and the
 * cancellation contract — once cancelled, onComplete must NOT fire so
 * callers can chain a new tween without races.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CameraTween, easeInOutCubic, type CameraState } from '../CameraTween';

describe('easeInOutCubic', () => {
  it('passes through the anchor points (0, 0.5, 1)', () => {
    expect(easeInOutCubic(0)).toBe(0);
    expect(easeInOutCubic(0.5)).toBeCloseTo(0.5, 5);
    expect(easeInOutCubic(1)).toBe(1);
  });

  it('is monotonically increasing across the unit interval', () => {
    let prev = -1;
    for (let i = 0; i <= 20; i++) {
      const v = easeInOutCubic(i / 20);
      expect(v).toBeGreaterThanOrEqual(prev);
      prev = v;
    }
  });

  it('clamps values outside [0, 1]', () => {
    expect(easeInOutCubic(-0.5)).toBe(0);
    expect(easeInOutCubic(1.5)).toBe(1);
  });
});

describe('CameraTween', () => {
  /**
   * Drive requestAnimationFrame manually so we don't depend on browser
   * scheduling. Each scheduled callback is queued with the `now` value
   * it should receive when we advance the virtual clock.
   */
  let rafQueue: Array<{ id: number; cb: FrameRequestCallback }>;
  let rafCounter: number;
  let virtualNow: number;
  let originalRaf: typeof globalThis.requestAnimationFrame;
  let originalCancel: typeof globalThis.cancelAnimationFrame;
  let originalPerfNow: () => number;

  beforeEach(() => {
    rafQueue = [];
    rafCounter = 1;
    virtualNow = 0;
    originalRaf = globalThis.requestAnimationFrame;
    originalCancel = globalThis.cancelAnimationFrame;
    originalPerfNow = performance.now.bind(performance);
    globalThis.requestAnimationFrame = ((cb: FrameRequestCallback) => {
      const id = rafCounter++;
      rafQueue.push({ id, cb });
      return id;
    }) as typeof globalThis.requestAnimationFrame;
    globalThis.cancelAnimationFrame = ((id: number) => {
      rafQueue = rafQueue.filter((q) => q.id !== id);
    }) as typeof globalThis.cancelAnimationFrame;
    vi.spyOn(performance, 'now').mockImplementation(() => virtualNow);
  });

  afterEach(() => {
    globalThis.requestAnimationFrame = originalRaf;
    globalThis.cancelAnimationFrame = originalCancel;
    vi.restoreAllMocks();
    // Restore actual perf.now (spy already restored above).
    void originalPerfNow;
  });

  function flushFrame(advanceMs: number) {
    virtualNow += advanceMs;
    const pending = rafQueue;
    rafQueue = [];
    for (const { cb } of pending) {
      cb(virtualNow);
    }
  }

  const from: CameraState = { position: [0, 0, 0], target: [0, 0, 0], up: [0, 1, 0] };
  const to: CameraState = { position: [10, 20, 30], target: [1, 2, 3], up: [0, 1, 0] };

  it('lerps position and target across the duration', () => {
    const tween = new CameraTween();
    const updates: CameraState[] = [];
    const onComplete = vi.fn();
    tween.start(from, to, 600, (s) => updates.push(s), onComplete);

    // Frame 0 — initial scheduled callback. t = 0.
    flushFrame(0);
    expect(updates.length).toBeGreaterThanOrEqual(1);
    expect(updates[0]!.position[0]).toBeCloseTo(0, 5);

    // Halfway through — t ≈ 0.5 → easeInOutCubic(0.5) === 0.5
    flushFrame(300);
    const mid = updates[updates.length - 1]!;
    expect(mid.position[0]).toBeCloseTo(5, 5);
    expect(mid.position[1]).toBeCloseTo(10, 5);
    expect(mid.position[2]).toBeCloseTo(15, 5);

    expect(onComplete).not.toHaveBeenCalled();

    // Finish — onComplete should fire once and the final state must
    // equal the target exactly (the helper snaps to avoid drift).
    flushFrame(300);
    expect(onComplete).toHaveBeenCalledTimes(1);
    const last = updates[updates.length - 1]!;
    expect(last.position).toEqual([10, 20, 30]);
    expect(last.target).toEqual([1, 2, 3]);
  });

  it('cancel() stops further updates and never fires onComplete', () => {
    const tween = new CameraTween();
    const onComplete = vi.fn();
    const updates: CameraState[] = [];
    const cancel = tween.start(from, to, 600, (s) => updates.push(s), onComplete);

    flushFrame(0); // first frame
    flushFrame(200);
    const countBefore = updates.length;
    cancel();
    // Any pending rAF tick must observe the cancel flag and exit.
    flushFrame(200);
    flushFrame(200);
    expect(updates.length).toBe(countBefore);
    expect(onComplete).not.toHaveBeenCalled();
  });

  it('completes onComplete approximately after durationMs elapsed', () => {
    const tween = new CameraTween();
    const onComplete = vi.fn();
    tween.start(from, to, 600, () => {}, onComplete);
    flushFrame(0);
    flushFrame(599);
    expect(onComplete).not.toHaveBeenCalled();
    flushFrame(2);
    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it('does not call onUpdate past 100% even with overshoot frames', () => {
    const tween = new CameraTween();
    const updates: CameraState[] = [];
    tween.start(from, to, 100, (s) => updates.push(s));
    flushFrame(0);
    flushFrame(500); // Way past the end
    // The very last update must be exactly the destination.
    expect(updates[updates.length - 1]!.position).toEqual([10, 20, 30]);
    // No further frames are scheduled after completion.
    flushFrame(100);
    expect(updates[updates.length - 1]!.position).toEqual([10, 20, 30]);
  });
});

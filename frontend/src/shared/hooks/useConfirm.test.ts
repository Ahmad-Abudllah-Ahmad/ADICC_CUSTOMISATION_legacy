// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for useConfirm() — promise-based confirmation hook used by 16+
// callers across the app. Covers:
//   * confirm({...}) returns a Promise<boolean>.
//   * Resolves true on onConfirm().
//   * Resolves false on onCancel().
//   * variant defaults to 'danger' and respects 'warning' override.
//   * Sequential confirms do not interfere with each other (each gets
//     its own resolution).
//   * Parallel confirms (programmer-error) — the second one wins the
//     resolver slot; the first promise stays pending forever. We pin
//     the current behaviour explicitly so a future fix is intentional.
//   * Unmounting the host component while a confirm is open leaves the
//     promise unresolved (current behaviour) — flagged so future work
//     that adds auto-resolve-false-on-unmount keeps this expectation
//     in mind.
//   * setLoading flips the loading flag without affecting the open
//     dialog or the pending promise.

import { describe, it, expect } from 'vitest';
import { renderHook, act, cleanup } from '@testing-library/react';

import { useConfirm } from './useConfirm';

describe('useConfirm', () => {
  it('returns initial state with open=false and variant defaulted to danger', () => {
    const { result } = renderHook(() => useConfirm());
    expect(result.current.open).toBe(false);
    expect(result.current.variant).toBe('danger');
    expect(result.current.loading).toBe(false);
    expect(typeof result.current.confirm).toBe('function');
  });

  it('opens the dialog and exposes title + message when confirm() is called', () => {
    const { result } = renderHook(() => useConfirm());
    act(() => {
      void result.current.confirm({
        title: 'Delete row?',
        message: 'This cannot be undone.',
      });
    });
    expect(result.current.open).toBe(true);
    expect(result.current.title).toBe('Delete row?');
    expect(result.current.message).toBe('This cannot be undone.');
  });

  it('confirm() returns a Promise that resolves to true on onConfirm()', async () => {
    const { result } = renderHook(() => useConfirm());
    let promise!: Promise<boolean>;
    act(() => {
      promise = result.current.confirm({ title: 'X', message: 'Y' });
    });
    act(() => {
      result.current.onConfirm();
    });
    await expect(promise).resolves.toBe(true);
    expect(result.current.open).toBe(false);
  });

  it('confirm() resolves to false on onCancel()', async () => {
    const { result } = renderHook(() => useConfirm());
    let promise!: Promise<boolean>;
    act(() => {
      promise = result.current.confirm({ title: 'X', message: 'Y' });
    });
    act(() => {
      result.current.onCancel();
    });
    await expect(promise).resolves.toBe(false);
    expect(result.current.open).toBe(false);
  });

  it('respects an explicit variant: "warning"', () => {
    const { result } = renderHook(() => useConfirm());
    act(() => {
      void result.current.confirm({
        title: 'Risky',
        message: 'Are you sure?',
        variant: 'warning',
      });
    });
    expect(result.current.variant).toBe('warning');
  });

  it('passes through custom confirmLabel and cancelLabel', () => {
    const { result } = renderHook(() => useConfirm());
    act(() => {
      void result.current.confirm({
        title: 'X',
        message: 'Y',
        confirmLabel: 'Burn it',
        cancelLabel: 'Keep it',
      });
    });
    expect(result.current.confirmLabel).toBe('Burn it');
    expect(result.current.cancelLabel).toBe('Keep it');
  });

  it('two sequential confirms each resolve independently', async () => {
    const { result } = renderHook(() => useConfirm());

    let first!: Promise<boolean>;
    act(() => {
      first = result.current.confirm({ title: 'A', message: '1' });
    });
    act(() => {
      result.current.onConfirm();
    });
    await expect(first).resolves.toBe(true);

    let second!: Promise<boolean>;
    act(() => {
      second = result.current.confirm({ title: 'B', message: '2' });
    });
    expect(result.current.title).toBe('B');
    act(() => {
      result.current.onCancel();
    });
    await expect(second).resolves.toBe(false);
  });

  it('setLoading flips the loading flag without closing the dialog', () => {
    const { result } = renderHook(() => useConfirm());
    act(() => {
      void result.current.confirm({ title: 'X', message: 'Y' });
    });
    expect(result.current.loading).toBe(false);
    act(() => {
      result.current.setLoading(true);
    });
    expect(result.current.loading).toBe(true);
    // Dialog remains open while loading is true.
    expect(result.current.open).toBe(true);
    act(() => {
      result.current.setLoading(false);
    });
    expect(result.current.loading).toBe(false);
    expect(result.current.open).toBe(true);
  });

  it('parallel confirms: the second call replaces the resolver - the first stays pending', async () => {
    // Programmer-error case: today the hook stores ONE resolver in
    // a ref, so a second confirm() overwrites it. The first promise
    // therefore never settles. We assert that explicitly so a future
    // queueing/rejection fix is a deliberate behaviour change.
    const { result } = renderHook(() => useConfirm());

    let first!: Promise<boolean>;
    let second!: Promise<boolean>;
    act(() => {
      first = result.current.confirm({ title: 'A', message: '1' });
      second = result.current.confirm({ title: 'B', message: '2' });
    });

    // Resolving once now only settles `second`.
    act(() => {
      result.current.onConfirm();
    });
    await expect(second).resolves.toBe(true);

    // `first` is still pending. Race it against an immediate timeout
    // to assert non-resolution without hanging the test forever.
    const sentinel = Symbol('pending');
    const raced = await Promise.race([
      first.then((v) => v as unknown as symbol),
      new Promise<symbol>((r) => setTimeout(() => r(sentinel), 30)),
    ]);
    expect(raced).toBe(sentinel);
  });

  it('unmounting while a confirm is open does not crash, but leaves the promise pending', async () => {
    const { result, unmount } = renderHook(() => useConfirm());
    let promise!: Promise<boolean>;
    act(() => {
      promise = result.current.confirm({ title: 'X', message: 'Y' });
    });
    expect(() => unmount()).not.toThrow();

    // Today the promise is not auto-resolved on unmount. Assert
    // non-resolution within a short window so a future
    // "resolve false on unmount" change is intentional.
    const sentinel = Symbol('pending');
    const raced = await Promise.race([
      promise.then((v) => v as unknown as symbol),
      new Promise<symbol>((r) => setTimeout(() => r(sentinel), 30)),
    ]);
    expect(raced).toBe(sentinel);
  });

  it('cleanup() between renderHook calls leaves no shared state', async () => {
    const first = renderHook(() => useConfirm());
    act(() => {
      void first.result.current.confirm({ title: 'A', message: '1' });
    });
    expect(first.result.current.open).toBe(true);
    cleanup();
    // A brand new hook instance starts clean.
    const second = renderHook(() => useConfirm());
    expect(second.result.current.open).toBe(false);
    expect(second.result.current.title).toBe('');
  });
});

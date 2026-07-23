// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for useTabKeyboardNav — the small helper that returns an
// onKeyDown handler for ad-hoc tab strips that aren't using <TabBar>.

import { describe, it, expect, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import type { KeyboardEvent } from 'react';

import { useTabKeyboardNav } from './useTabKeyboardNav';

type Id = 'one' | 'two' | 'three';

function ev(key: string): KeyboardEvent<HTMLElement> {
  // Minimal stub satisfying the surface the hook uses.
  return {
    key,
    preventDefault: vi.fn(),
    stopPropagation: vi.fn(),
  } as unknown as KeyboardEvent<HTMLElement>;
}

describe('useTabKeyboardNav', () => {
  it('horizontal: ArrowRight moves forward, ArrowLeft moves backward', () => {
    const onChange = vi.fn();
    const ids: readonly Id[] = ['one', 'two', 'three'];
    const { result } = renderHook(() =>
      useTabKeyboardNav<Id>({ ids, activeId: 'one', onChange, orientation: 'horizontal' }),
    );
    result.current(ev('ArrowRight'));
    expect(onChange).toHaveBeenLastCalledWith('two');
    result.current(ev('ArrowLeft'));
    expect(onChange).toHaveBeenLastCalledWith('three');
  });

  it('vertical: ArrowDown moves forward, ArrowUp moves backward', () => {
    const onChange = vi.fn();
    const ids: readonly Id[] = ['one', 'two', 'three'];
    const { result } = renderHook(() =>
      useTabKeyboardNav<Id>({ ids, activeId: 'two', onChange, orientation: 'vertical' }),
    );
    result.current(ev('ArrowDown'));
    expect(onChange).toHaveBeenLastCalledWith('three');
    result.current(ev('ArrowUp'));
    expect(onChange).toHaveBeenLastCalledWith('one');
  });

  it('Home jumps to first, End jumps to last', () => {
    const onChange = vi.fn();
    const ids: readonly Id[] = ['one', 'two', 'three'];
    const { result } = renderHook(() =>
      useTabKeyboardNav<Id>({ ids, activeId: 'two', onChange, orientation: 'horizontal' }),
    );
    result.current(ev('Home'));
    expect(onChange).toHaveBeenLastCalledWith('one');
    result.current(ev('End'));
    expect(onChange).toHaveBeenLastCalledWith('three');
  });

  it('ignores keys that are not navigation keys', () => {
    const onChange = vi.fn();
    const ids: readonly Id[] = ['one', 'two', 'three'];
    const { result } = renderHook(() =>
      useTabKeyboardNav<Id>({ ids, activeId: 'one', onChange, orientation: 'horizontal' }),
    );
    result.current(ev('Enter'));
    result.current(ev('a'));
    expect(onChange).not.toHaveBeenCalled();
  });

  it('skips disabled tabs in the rotation', () => {
    const onChange = vi.fn();
    const ids: readonly Id[] = ['one', 'two', 'three'];
    const { result } = renderHook(() =>
      useTabKeyboardNav<Id>({
        ids,
        activeId: 'one',
        onChange,
        orientation: 'horizontal',
        disabledIds: ['two'],
      }),
    );
    result.current(ev('ArrowRight'));
    expect(onChange).toHaveBeenLastCalledWith('three');
  });
});

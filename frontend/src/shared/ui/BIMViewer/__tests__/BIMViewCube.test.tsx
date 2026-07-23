/**
 * BIMViewCube tests — verifies face buttons are present and each one
 * calls SceneManager.setViewPreset() with the correct preset name (W6.6).
 *
 * WHY: We can't exercise the WebGL raycast in jsdom — three.js has no
 * GL context here. Instead we render the component, click the
 * accessible `sr-only` fallback buttons that mirror the cube faces,
 * and assert the public contract (`setViewPreset` dispatch).
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

// Mock three.js WebGLRenderer + CanvasTexture so the component mounts
// in jsdom without crashing. We keep the real Scene / Camera / Box /
// Material classes — they're plain JS objects that don't need GL.
vi.mock('three', async () => {
  const actual = await vi.importActual<typeof import('three')>('three');
  class FakeWebGLRenderer {
    domElement: HTMLCanvasElement;
    constructor(opts: { canvas?: HTMLCanvasElement } = {}) {
      this.domElement =
        opts.canvas ?? (document.createElement('canvas') as HTMLCanvasElement);
    }
    setPixelRatio() {}
    setSize() {}
    setClearColor() {}
    render() {}
    dispose() {}
  }
  class FakeCanvasTexture {
    needsUpdate = true;
    constructor(_canvas?: HTMLCanvasElement) {
      void _canvas;
    }
    dispose() {}
  }
  return {
    ...actual,
    WebGLRenderer: FakeWebGLRenderer,
    CanvasTexture: FakeCanvasTexture,
  };
});

import { BIMViewCube } from '../BIMViewCube';
import type { SceneManager } from '../SceneManager';

function makeMockSceneManager(): {
  sm: SceneManager;
  setViewPreset: ReturnType<typeof vi.fn>;
  onCameraChange: ReturnType<typeof vi.fn>;
} {
  const setViewPreset = vi.fn().mockResolvedValue(undefined);
  const onCameraChange = vi.fn().mockReturnValue(() => {});
  const sm = {
    camera: { matrixWorld: { decompose: () => {} } },
    controls: { target: { copy: () => {} } },
    setViewPreset,
    onCameraChange,
  } as unknown as SceneManager;
  return { sm, setViewPreset, onCameraChange };
}

describe('BIMViewCube', () => {
  afterEach(() => {
    cleanup();
  });

  it('renders the root widget with the expected test id', () => {
    const { sm } = makeMockSceneManager();
    render(<BIMViewCube sceneManager={sm} />);
    expect(screen.getByTestId('bim-view-cube')).toBeInTheDocument();
  });

  it('renders an accessible fallback button per face', () => {
    const { sm } = makeMockSceneManager();
    render(<BIMViewCube sceneManager={sm} />);
    for (const preset of ['top', 'bottom', 'front', 'back', 'left', 'right'] as const) {
      expect(screen.getByTestId(`bim-view-cube-face-${preset}`)).toBeInTheDocument();
    }
  });

  it('calls setViewPreset with the matching preset when a face button is clicked', () => {
    const { sm, setViewPreset } = makeMockSceneManager();
    render(<BIMViewCube sceneManager={sm} />);
    for (const preset of ['top', 'bottom', 'front', 'back', 'left', 'right'] as const) {
      screen.getByTestId(`bim-view-cube-face-${preset}`).click();
    }
    expect(setViewPreset).toHaveBeenCalledTimes(6);
    expect(setViewPreset.mock.calls.map((c) => c[0])).toEqual([
      'top',
      'bottom',
      'front',
      'back',
      'left',
      'right',
    ]);
  });

  it('subscribes to camera-change events on the active scene manager', () => {
    const { sm, onCameraChange } = makeMockSceneManager();
    render(<BIMViewCube sceneManager={sm} />);
    expect(onCameraChange).toHaveBeenCalled();
  });

  it('mounts safely when sceneManager is null', () => {
    expect(() =>
      render(<BIMViewCube sceneManager={null} />),
    ).not.toThrow();
    expect(screen.getByTestId('bim-view-cube')).toBeInTheDocument();
  });
});

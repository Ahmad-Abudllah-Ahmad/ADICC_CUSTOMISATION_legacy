// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Tests for SelectionManager hover throttling (perf wave).
 *
 * The hover raycast is the dominant idle-interaction cost on a large model:
 * a high-Hz mouse fires many `mousemove` events per rendered frame and each
 * used to raycast the ENTIRE scene recursively. These tests pin the new
 * contract:
 *   - a burst of move events coalesces into a single raycast on the next
 *     animation frame (one hover resolution, not one per event);
 *   - no hover raycast runs while a pointer button is held (camera drag);
 *   - starting a drag clears an active hover exactly once;
 *   - a disposed / suspended tool never resolves a queued hover.
 *
 * We use real three geometry + a real Raycaster (pure math, no WebGL) and a
 * hand-rolled requestAnimationFrame so the frame boundary is deterministic.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as THREE from 'three';

import { SelectionManager } from '../SelectionManager';
import type { SceneManager } from '../SceneManager';
import type { BIMElementData, ElementManager } from '../ElementManager';

/** Captured rAF callbacks so a test can advance frames by hand. */
let rafCallbacks: FrameRequestCallback[] = [];

function flushFrame(): void {
  const cbs = rafCallbacks;
  rafCallbacks = [];
  for (const cb of cbs) cb(performance.now());
}

function makeCanvas(): HTMLCanvasElement {
  const canvas = document.createElement('canvas');
  // jsdom returns an all-zero rect; getMouseCoords divides by width/height,
  // so give it a real 100x100 box centred at the origin.
  canvas.getBoundingClientRect = () =>
    ({
      left: 0,
      top: 0,
      right: 100,
      bottom: 100,
      width: 100,
      height: 100,
      x: 0,
      y: 0,
      toJSON() {},
    }) as DOMRect;
  return canvas;
}

/** A box at the origin, big enough that the centre-screen ray always hits. */
function makeHitMesh(elementId: string): THREE.Mesh {
  const mesh = new THREE.Mesh(
    new THREE.BoxGeometry(4, 4, 4),
    new THREE.MeshStandardMaterial({ color: 0x808080 }),
  );
  mesh.userData = { elementId };
  return mesh;
}

interface Harness {
  selection: SelectionManager;
  canvas: HTMLCanvasElement;
  mesh: THREE.Mesh;
  onHover: ReturnType<typeof vi.fn>;
  originalMaterial: THREE.Material;
}

function setup(elementId = 'el-1'): Harness {
  const canvas = makeCanvas();
  const scene = new THREE.Scene();
  const mesh = makeHitMesh(elementId);
  const originalMaterial = mesh.material as THREE.Material;
  scene.add(mesh);

  const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
  camera.position.set(0, 0, 10);
  camera.lookAt(0, 0, 0);
  camera.updateMatrixWorld(true);
  scene.updateMatrixWorld(true);

  const sceneManager = {
    renderer: { domElement: canvas },
    camera,
    scene,
    requestRender: vi.fn(),
  } as unknown as SceneManager;

  const elementManager = {
    getMesh: (id: string) => (id === elementId ? mesh : undefined),
    getElementData: (id: string): BIMElementData | undefined =>
      id === elementId
        ? { id, name: 'El', element_type: 'Walls', discipline: 'architectural' }
        : undefined,
    getAllMeshes: () => [mesh],
  } as unknown as ElementManager;

  const onHover = vi.fn();
  const selection = new SelectionManager(sceneManager, elementManager, {
    onElementHover: onHover,
  });

  return { selection, canvas, mesh, onHover, originalMaterial };
}

function move(canvas: HTMLCanvasElement, buttons = 0): void {
  canvas.dispatchEvent(
    new MouseEvent('mousemove', { clientX: 50, clientY: 50, buttons, bubbles: true }),
  );
}

beforeEach(() => {
  rafCallbacks = [];
  vi.stubGlobal(
    'requestAnimationFrame',
    vi.fn((cb: FrameRequestCallback) => {
      rafCallbacks.push(cb);
      return rafCallbacks.length;
    }),
  );
  vi.stubGlobal('cancelAnimationFrame', vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('SelectionManager hover throttle', () => {
  it('coalesces a burst of mousemove events into one raycast per frame', () => {
    const { selection, canvas, onHover } = setup();

    // Three move events in the same frame -> one scheduled frame, no hover yet.
    move(canvas);
    move(canvas);
    move(canvas);
    expect(requestAnimationFrame).toHaveBeenCalledTimes(1);
    expect(onHover).not.toHaveBeenCalled();

    // Advancing one frame resolves the hover exactly once.
    flushFrame();
    expect(onHover).toHaveBeenCalledTimes(1);
    expect(onHover).toHaveBeenLastCalledWith('el-1');

    selection.dispose();
  });

  it('applies the hover material to the element under the cursor', () => {
    const { selection, canvas, mesh, originalMaterial } = setup();
    move(canvas);
    flushFrame();
    // The mesh material was swapped for the shared hover material.
    expect(mesh.material).not.toBe(originalMaterial);
    selection.dispose();
  });

  it('does not raycast or hover while a pointer button is held (camera drag)', () => {
    const { selection, canvas, onHover } = setup();
    move(canvas, 1); // left button down => orbiting
    expect(requestAnimationFrame).not.toHaveBeenCalled();
    expect(onHover).not.toHaveBeenCalled();
    selection.dispose();
  });

  it('clears an active hover once when a drag starts, restoring the material', () => {
    const { selection, canvas, mesh, onHover, originalMaterial } = setup();

    // Establish a hover.
    move(canvas);
    flushFrame();
    expect(onHover).toHaveBeenLastCalledWith('el-1');
    onHover.mockClear();

    // Start dragging: hover cleared once, material restored, no new frame.
    move(canvas, 1);
    expect(onHover).toHaveBeenCalledTimes(1);
    expect(onHover).toHaveBeenLastCalledWith(null);
    expect(mesh.material).toBe(originalMaterial);

    // A second drag move does not re-fire the null hover.
    move(canvas, 1);
    expect(onHover).toHaveBeenCalledTimes(1);

    selection.dispose();
  });

  it('does not resolve a queued hover after dispose', () => {
    const { selection, canvas, onHover } = setup();
    move(canvas); // schedules a frame
    selection.dispose(); // cancels the pending hover
    flushFrame(); // the stale callback must be a no-op
    expect(onHover).not.toHaveBeenCalled();
  });

  it('does not resolve a queued hover after the tool is suspended', () => {
    const { selection, canvas, onHover } = setup();
    move(canvas);
    selection.setSuspended(true);
    flushFrame();
    expect(onHover).not.toHaveBeenCalled();
    selection.dispose();
  });
});

import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as THREE from 'three';
import { ClipManager } from '../ClipManager';
import type { SceneManager } from '../SceneManager';

/** Minimal SceneManager stand-in with a real scene + a fake renderer so we
 *  can assert clippingPlanes assignment without booting WebGL. */
function makeFakes() {
  const scene = new THREE.Scene();
  // One real mesh to carry the clip planes.
  const mat = new THREE.MeshStandardMaterial();
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(2, 2, 2), mat);
  mesh.position.set(0, 0, 0);
  mesh.geometry.computeBoundingBox();
  scene.add(mesh);

  const renderer = { localClippingEnabled: false } as THREE.WebGLRenderer;
  const sceneMgr = {
    scene,
    renderer,
    requestRender: vi.fn(),
  } as unknown as SceneManager;
  return { scene, mesh, mat, sceneMgr };
}

describe('ClipManager', () => {
  let fakes: ReturnType<typeof makeFakes>;
  let mgr: ClipManager;

  beforeEach(() => {
    fakes = makeFakes();
    mgr = new ClipManager(fakes.sceneMgr);
  });

  it('enables renderer local clipping on construction', () => {
    expect(fakes.sceneMgr.renderer.localClippingEnabled).toBe(true);
  });

  it('starts with no clip mode and no planes assigned', () => {
    expect(mgr.mode).toBe('none');
    expect(fakes.mat.clippingPlanes).toBeNull();
  });

  it('assigns six box planes in box mode', () => {
    mgr.setMode('box');
    expect(mgr.mode).toBe('box');
    expect(fakes.mat.clippingPlanes).not.toBeNull();
    expect(fakes.mat.clippingPlanes!.length).toBe(6);
  });

  it('assigns a single plane in plane mode', () => {
    mgr.setMode('plane');
    expect(fakes.mat.clippingPlanes).not.toBeNull();
    expect(fakes.mat.clippingPlanes!.length).toBe(1);
  });

  it('clears planes when mode returns to none', () => {
    mgr.setMode('box');
    mgr.setMode('none');
    expect(fakes.mat.clippingPlanes).toBeNull();
  });

  it('reset() restores defaults and disables clipping', () => {
    mgr.setMode('box');
    mgr.setBoxExtent({ minX: 0.3, maxX: 0.7 });
    mgr.reset();
    expect(mgr.mode).toBe('none');
    expect(mgr.getBoxExtent()).toEqual({
      minX: 0,
      maxX: 1,
      minY: 0,
      maxY: 1,
      minZ: 0,
      maxZ: 1,
    });
    expect(fakes.mat.clippingPlanes).toBeNull();
  });

  it('clamps box faces so min never crosses max', () => {
    // Push min past max — clamp should keep a positive gap.
    mgr.setBoxExtent({ minX: 0.9, maxX: 0.2 });
    const e = mgr.getBoxExtent();
    expect(e.minX).toBeLessThanOrEqual(e.maxX);
  });

  it('clamps box extent values into [0, 1]', () => {
    mgr.setBoxExtent({ minY: -0.5, maxY: 2 });
    const e = mgr.getBoxExtent();
    expect(e.minY).toBeGreaterThanOrEqual(0);
    expect(e.maxY).toBeLessThanOrEqual(1);
  });

  it('updates the single plane normal when the axis changes', () => {
    mgr.setMode('plane');
    mgr.setPlaneState({ axis: 'x' });
    const plane = fakes.mat.clippingPlanes![0]!;
    // X-axis plane → normal aligned with X.
    expect(Math.abs(plane.normal.x)).toBeCloseTo(1, 6);
    expect(plane.normal.y).toBeCloseTo(0, 6);
  });

  it('flips the plane normal when flipped is toggled', () => {
    mgr.setMode('plane');
    mgr.setPlaneState({ axis: 'y', flipped: false });
    const before = fakes.mat.clippingPlanes![0]!.normal.clone();
    mgr.setPlaneState({ flipped: true });
    const after = fakes.mat.clippingPlanes![0]!.normal;
    expect(after.y).toBeCloseTo(-before.y, 6);
  });

  it('dispose() detaches planes from every material', () => {
    mgr.setMode('box');
    mgr.dispose();
    expect(fakes.mat.clippingPlanes).toBeNull();
  });
});

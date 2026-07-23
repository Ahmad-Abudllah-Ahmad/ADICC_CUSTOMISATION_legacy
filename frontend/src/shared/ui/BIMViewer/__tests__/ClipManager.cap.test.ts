/**
 * ClipManager — section cap hatching tests.
 *
 * Cover the cap geometry/orientation maths, the public setCap* API
 * validation, and lifecycle (enable → disable → re-enable disposes and
 * recreates the cap mesh). We do NOT exercise the shader itself — that
 * lives on the GPU and is verified by the Playwright screenshot script.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as THREE from 'three';
import { ClipManager } from '../ClipManager';
import type { SceneManager } from '../SceneManager';

function makeFakes() {
  const scene = new THREE.Scene();
  const mat = new THREE.MeshStandardMaterial();
  // Place a 4×4×4 box centred on the origin so the model bounding box is
  // (-2,-2,-2) → (2,2,2). Cap geometry maths use that box.
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(4, 4, 4), mat);
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

/** Locate the cap mesh in the scene by its tagged userData flag. */
function findCap(scene: THREE.Scene): THREE.Mesh | null {
  let found: THREE.Mesh | null = null;
  scene.traverse((obj) => {
    if (obj.userData && obj.userData.isClipCap && obj instanceof THREE.Mesh) {
      found = obj;
    }
  });
  return found;
}

describe('ClipManager - section cap hatching', () => {
  let fakes: ReturnType<typeof makeFakes>;
  let mgr: ClipManager;

  beforeEach(() => {
    fakes = makeFakes();
    mgr = new ClipManager(fakes.sceneMgr);
  });

  it('starts with the cap enabled by default but no cap mesh until a clip plane is active', () => {
    expect(mgr.capEnabled).toBe(true);
    expect(findCap(fakes.scene)).toBeNull();
  });

  it('creates a cap mesh sized to the model bounding box when a clip plane is activated', () => {
    mgr.setMode('plane');
    mgr.setPlaneState({ axis: 'y', offset: 0.5, flipped: false });
    const cap = findCap(fakes.scene);
    expect(cap).not.toBeNull();
    // Cap should be roughly aligned with Y=0 (model centre on Y axis).
    expect(cap!.position.y).toBeCloseTo(0, 6);
    // Quad scale should exceed the model diagonal so the hatch covers the
    // visible cross-section. Box (4×4×4) → diagonal ≈ 6.93, scale ≥ ~7.
    expect(cap!.scale.x).toBeGreaterThan(6);
    expect(cap!.scale.y).toBeGreaterThan(6);
  });

  it('orients the cap so its +Z normal matches the plane normal', () => {
    mgr.setMode('plane');
    mgr.setPlaneState({ axis: 'y', offset: 0.5, flipped: false });
    const cap = findCap(fakes.scene)!;
    const capNormal = new THREE.Vector3(0, 0, 1).applyQuaternion(cap.quaternion);
    // Plane axis y → cap normal should be along +Y (within float tolerance).
    expect(Math.abs(capNormal.y)).toBeCloseTo(1, 5);
    expect(Math.abs(capNormal.x)).toBeLessThan(1e-5);
    expect(Math.abs(capNormal.z)).toBeLessThan(1e-5);
  });

  it('rebuilds the cap when the plane axis changes', () => {
    mgr.setMode('plane');
    mgr.setPlaneState({ axis: 'y' });
    const first = findCap(fakes.scene)!;
    const firstY = new THREE.Vector3(0, 0, 1).applyQuaternion(first.quaternion).y;
    mgr.setPlaneState({ axis: 'x' });
    const second = findCap(fakes.scene)!;
    const secondNormal = new THREE.Vector3(0, 0, 1).applyQuaternion(second.quaternion);
    // After switching to X axis the cap normal should now point along X.
    expect(Math.abs(secondNormal.x)).toBeCloseTo(1, 5);
    // And NOT match the previous Y-aligned normal.
    expect(Math.abs(firstY - secondNormal.y)).toBeGreaterThan(0.5);
  });

  it('disposes the cap when the cap is disabled', () => {
    mgr.setMode('plane');
    expect(findCap(fakes.scene)).not.toBeNull();
    mgr.setCapEnabled(false);
    expect(findCap(fakes.scene)).toBeNull();
  });

  it('recreates the cap when re-enabled while clipping is active', () => {
    mgr.setMode('plane');
    mgr.setCapEnabled(false);
    expect(findCap(fakes.scene)).toBeNull();
    mgr.setCapEnabled(true);
    expect(findCap(fakes.scene)).not.toBeNull();
  });

  it('disposes the cap when clipping returns to none', () => {
    mgr.setMode('plane');
    expect(findCap(fakes.scene)).not.toBeNull();
    mgr.setMode('none');
    expect(findCap(fakes.scene)).toBeNull();
  });

  it('does not render a cap in box mode (helper alone is the cue)', () => {
    mgr.setMode('box');
    expect(findCap(fakes.scene)).toBeNull();
  });

  it('clamps cap style alpha into [0, 1]', () => {
    mgr.setCapStyle({ alpha: 2.0 });
    expect(mgr.getCapStyle().alpha).toBe(1);
    mgr.setCapStyle({ alpha: -0.5 });
    expect(mgr.getCapStyle().alpha).toBe(0);
  });

  it('clamps cap style density above zero', () => {
    mgr.setCapStyle({ density: 0 });
    expect(mgr.getCapStyle().density).toBeGreaterThan(0);
    mgr.setCapStyle({ density: -10 });
    expect(mgr.getCapStyle().density).toBeGreaterThan(0);
  });

  it('wraps cap style angleDeg modulo 360 (including negative values)', () => {
    mgr.setCapStyle({ angleDeg: 405 });
    expect(mgr.getCapStyle().angleDeg).toBeCloseTo(45, 6);
    mgr.setCapStyle({ angleDeg: -90 });
    expect(mgr.getCapStyle().angleDeg).toBeCloseTo(270, 6);
  });

  it('setCapColor updates the active cap material uniform live', () => {
    mgr.setMode('plane');
    mgr.setCapColor(0xff00ff);
    const cap = findCap(fakes.scene)!;
    const mat = cap.material as THREE.ShaderMaterial;
    const color = mat.uniforms['uColor']?.value as THREE.Color;
    expect(color.r).toBeCloseTo(1, 5);
    expect(color.g).toBeCloseTo(0, 5);
    expect(color.b).toBeCloseTo(1, 5);
  });

  it('setCapStyle updates active cap shader uniforms', () => {
    mgr.setMode('plane');
    mgr.setCapStyle({ density: 16, angleDeg: 30, alpha: 0.25 });
    const cap = findCap(fakes.scene)!;
    const mat = cap.material as THREE.ShaderMaterial;
    expect(mat.uniforms['uDensity']?.value).toBe(16);
    expect(mat.uniforms['uAlpha']?.value).toBe(0.25);
    expect(mat.uniforms['uAngleRad']?.value).toBeCloseTo((30 * Math.PI) / 180, 6);
  });

  it('dispose() removes the cap mesh from the scene', () => {
    mgr.setMode('plane');
    expect(findCap(fakes.scene)).not.toBeNull();
    mgr.dispose();
    expect(findCap(fakes.scene)).toBeNull();
  });

  it('cap material is excluded from material.clippingPlanes assignment', () => {
    mgr.setMode('plane');
    const cap = findCap(fakes.scene)!;
    const mat = cap.material as THREE.ShaderMaterial;
    expect(mat.clippingPlanes).toBeNull();
  });
});

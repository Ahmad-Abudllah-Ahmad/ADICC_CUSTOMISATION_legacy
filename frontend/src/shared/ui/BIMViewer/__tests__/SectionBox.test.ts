/**
 * SectionBox tests — verify the AABB-driven clipping helper without
 * booting WebGL. Strategy: mock `TransformControls` (it pokes at the
 * DOM in its constructor and is irrelevant for the plane-math
 * assertions), use a real `THREE.Scene` + `Mesh` + `MeshStandardMaterial`,
 * and use a stub `WebGLRenderer` that only exposes `localClippingEnabled`
 * and `domElement`.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as THREE from 'three';

// Mock the TransformControls module — its constructor reads
// `document.body.style.touchAction` which jsdom does NOT support cleanly
// across versions, and we don't exercise the gizmo geometry here.
vi.mock('three/examples/jsm/controls/TransformControls.js', () => {
  class FakeTransformControls {
    object: THREE.Object3D | null = null;
    mode = 'translate';
    enabled = false;
    private helper = new THREE.Object3D();
    private listeners: Record<string, ((e: unknown) => void)[]> = {};
    constructor(public camera: THREE.Camera, public domElement: HTMLElement) {
      this.helper.userData.isFakeTransformHelper = true;
    }
    setMode(m: string): void {
      this.mode = m;
    }
    attach(o: THREE.Object3D): void {
      this.object = o;
    }
    detach(): void {
      this.object = null;
    }
    getHelper(): THREE.Object3D {
      return this.helper;
    }
    addEventListener(type: string, fn: (e: unknown) => void): void {
      (this.listeners[type] ??= []).push(fn);
    }
    removeEventListener(): void {
      // no-op
    }
    dispatchEvent(e: { type: string }): void {
      const list = this.listeners[e.type];
      if (list) for (const fn of list) fn(e);
    }
    dispose(): void {
      this.listeners = {};
    }
  }
  return { TransformControls: FakeTransformControls };
});

import { SectionBox } from '../SectionBox';

function makeFakes() {
  const scene = new THREE.Scene();
  const mat = new THREE.MeshStandardMaterial();
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(2, 2, 2), mat);
  scene.add(mesh);

  // Second material to verify multi-material snapshot + restore.
  const mat2 = new THREE.MeshStandardMaterial();
  const mesh2 = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), mat2);
  mesh2.position.set(5, 0, 0);
  scene.add(mesh2);

  const renderer = {
    localClippingEnabled: false,
    domElement: document.createElement('canvas'),
  } as unknown as THREE.WebGLRenderer;
  const camera = new THREE.PerspectiveCamera(45, 1, 0.01, 1000);
  return { scene, mesh, mesh2, mat, mat2, renderer, camera };
}

describe('SectionBox', () => {
  let fakes: ReturnType<typeof makeFakes>;
  let sb: SectionBox;

  beforeEach(() => {
    fakes = makeFakes();
    sb = new SectionBox({
      scene: fakes.scene,
      camera: fakes.camera,
      renderer: fakes.renderer,
    });
  });

  it('enable() flips renderer.localClippingEnabled when previously false', () => {
    expect(fakes.renderer.localClippingEnabled).toBe(false);
    sb.enable();
    expect(fakes.renderer.localClippingEnabled).toBe(true);
    expect(sb.isEnabled()).toBe(true);
  });

  it('disable() restores the previous localClippingEnabled flag', () => {
    // Case 1: was off → ends off.
    sb.enable();
    sb.disable();
    expect(fakes.renderer.localClippingEnabled).toBe(false);
    expect(sb.isEnabled()).toBe(false);
  });

  it('disable() does not stomp localClippingEnabled if it was already on', () => {
    fakes.renderer.localClippingEnabled = true;
    sb.enable();
    sb.disable();
    expect(fakes.renderer.localClippingEnabled).toBe(true);
  });

  it('setBoundsToBox produces 6 inward-facing planes matching the AABB', () => {
    sb.enable();
    const box = new THREE.Box3(
      new THREE.Vector3(-1, -2, -3),
      new THREE.Vector3(1, 2, 3),
    );
    sb.setBoundsToBox(box);

    const planes = sb.getClippingPlanes();
    expect(planes).toHaveLength(6);

    // Each plane should classify the box CENTRE as INSIDE (distance ≥ 0).
    const centre = new THREE.Vector3(0, 0, 0);
    for (const p of planes) {
      expect(p.distanceToPoint(centre)).toBeGreaterThanOrEqual(0);
    }
    // A point clearly outside on +X should be outside on at least one
    // plane (signed distance < 0).
    const outside = new THREE.Vector3(10, 0, 0);
    const anyOutside = planes.some((p) => p.distanceToPoint(outside) < 0);
    expect(anyOutside).toBe(true);
  });

  it('setBoundsToSelection computes the union AABB of selected objects', () => {
    sb.enable();
    sb.setBoundsToSelection([fakes.mesh, fakes.mesh2]);
    const bounds = sb.getBounds();
    // mesh1 occupies [-1, 1] cube; mesh2 is a 1×1×1 at x=5 so [4.5, 5.5].
    expect(bounds.min.x).toBeCloseTo(-1, 3);
    expect(bounds.max.x).toBeCloseTo(5.5, 3);
  });

  it('getClippingPlanes() always returns 6 planes', () => {
    expect(sb.getClippingPlanes()).toHaveLength(6);
    sb.enable();
    expect(sb.getClippingPlanes()).toHaveLength(6);
    sb.setBoundsToBox(
      new THREE.Box3(new THREE.Vector3(0, 0, 0), new THREE.Vector3(1, 1, 1)),
    );
    expect(sb.getClippingPlanes()).toHaveLength(6);
  });

  it('applies clippingPlanes to every mesh material when enabled with bounds', () => {
    sb.enable(
      new THREE.Box3(new THREE.Vector3(-1, -1, -1), new THREE.Vector3(1, 1, 1)),
    );
    expect(fakes.mat.clippingPlanes).not.toBeNull();
    expect(fakes.mat.clippingPlanes!).toHaveLength(6);
    expect(fakes.mat2.clippingPlanes).not.toBeNull();
  });

  it('disable() restores the previous clippingPlanes on every material', () => {
    // Pre-existing plane on one material — must survive enable + disable.
    const existing = [new THREE.Plane(new THREE.Vector3(0, 1, 0), 0)];
    fakes.mat.clippingPlanes = existing;
    sb.enable(
      new THREE.Box3(new THREE.Vector3(-1, -1, -1), new THREE.Vector3(1, 1, 1)),
    );
    expect(fakes.mat.clippingPlanes).not.toBe(existing); // overwritten
    sb.disable();
    expect(fakes.mat.clippingPlanes).toBe(existing);
    expect(fakes.mat2.clippingPlanes).toBeNull();
  });

  it('dispose() removes the wireframe overlay + restores renderer state', () => {
    sb.enable(
      new THREE.Box3(new THREE.Vector3(-1, -1, -1), new THREE.Vector3(1, 1, 1)),
    );
    // Wireframe should be present in the scene as a LineSegments.
    const wires = fakes.scene.children.filter(
      (c) => c instanceof THREE.LineSegments,
    );
    expect(wires.length).toBeGreaterThanOrEqual(1);
    sb.dispose();
    // Renderer flag restored (it was false on construction).
    expect(fakes.renderer.localClippingEnabled).toBe(false);
    // Wireframe removed from the scene.
    const afterWires = fakes.scene.children.filter(
      (c) => c instanceof THREE.LineSegments,
    );
    expect(afterWires.length).toBe(0);
  });

  it('__testSnapTo quantises Ctrl-drag offsets to integer millimetres', () => {
    // 0.12345 m → 123.45 mm → rounded to 123 mm → 0.123 m.
    const snapped = sb.__testSnapTo({ x: 0.12345, y: 0.4999, z: -0.0007 });
    expect(snapped.x).toBeCloseTo(0.123, 6);
    expect(snapped.y).toBeCloseTo(0.5, 6);
    expect(snapped.z).toBeCloseTo(-0.001, 6);
  });

  it('idempotent enable(): calling twice does not re-snapshot or double-apply', () => {
    const existing = [new THREE.Plane(new THREE.Vector3(0, 1, 0), 0)];
    fakes.mat.clippingPlanes = existing;
    sb.enable(
      new THREE.Box3(new THREE.Vector3(-1, -1, -1), new THREE.Vector3(1, 1, 1)),
    );
    // After first enable, the snapshot's previousPlanes captured `existing`.
    // A second enable() must NOT capture the SectionBox planes as "previous".
    sb.enable();
    sb.disable();
    expect(fakes.mat.clippingPlanes).toBe(existing);
  });

  it('setBoundsToBox rejects an empty box and leaves prior bounds intact', () => {
    sb.enable();
    const good = new THREE.Box3(
      new THREE.Vector3(-1, -1, -1),
      new THREE.Vector3(1, 1, 1),
    );
    expect(sb.setBoundsToBox(good)).toBe(true);
    // An empty box (max < min) must be rejected without clobbering bounds.
    const empty = new THREE.Box3(
      new THREE.Vector3(1, 1, 1),
      new THREE.Vector3(-1, -1, -1),
    );
    expect(sb.setBoundsToBox(empty)).toBe(false);
    const bounds = sb.getBounds();
    expect(bounds.min.x).toBeCloseTo(-1, 6);
    expect(bounds.max.x).toBeCloseTo(1, 6);
  });

  it('setBoundsToBox rejects a degenerate (zero-size) box that would clip everything', () => {
    sb.enable();
    // A collapsed AABB (min === max) is NOT empty in three.js, but fitting
    // the six inward planes to it hides the whole model. Must be rejected.
    const point = new THREE.Box3(
      new THREE.Vector3(5, 5, 5),
      new THREE.Vector3(5, 5, 5),
    );
    expect(sb.setBoundsToBox(point)).toBe(false);
    expect(SectionBox.isUsableBox(point)).toBe(false);
    // A box larger than 1mm on at least one axis is accepted.
    const thin = new THREE.Box3(
      new THREE.Vector3(0, 0, 0),
      new THREE.Vector3(2, 0, 0),
    );
    expect(SectionBox.isUsableBox(thin)).toBe(true);
  });

  it('setBoundsToSelection returns false for an empty selection', () => {
    sb.enable();
    expect(sb.setBoundsToSelection([])).toBe(false);
    expect(sb.setBoundsToSelection([fakes.mesh])).toBe(true);
  });

  it('enableManualDrag(true) wires up the TransformControls gizmo', () => {
    sb.enable(
      new THREE.Box3(new THREE.Vector3(-1, -1, -1), new THREE.Vector3(1, 1, 1)),
    );
    sb.enableManualDrag(true);
    expect(sb.isManualDragEnabled()).toBe(true);
    // Disable round-trip clears the flag.
    sb.enableManualDrag(false);
    expect(sb.isManualDragEnabled()).toBe(false);
  });
});

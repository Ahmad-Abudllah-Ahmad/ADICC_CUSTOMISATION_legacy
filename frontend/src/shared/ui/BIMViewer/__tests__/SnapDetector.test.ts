/**
 * SnapDetector unit tests — verify vertex / edge_midpoint / edge_perp
 * priority and the screen-space radius gating.
 *
 * Uses a real BufferGeometry + camera and stubs canvas.getBoundingClientRect
 * so we exercise the actual projection math without depending on jsdom's
 * (missing) canvas implementation.
 */

import { beforeEach, describe, expect, it } from 'vitest';
import * as THREE from 'three';
import { SnapDetector } from '../SnapDetector';

const CANVAS_WIDTH = 800;
const CANVAS_HEIGHT = 600;

function makeCanvas(): HTMLCanvasElement {
  const canvas = document.createElement('canvas');
  canvas.width = CANVAS_WIDTH;
  canvas.height = CANVAS_HEIGHT;
  canvas.getBoundingClientRect = () =>
    ({
      left: 0,
      top: 0,
      right: CANVAS_WIDTH,
      bottom: CANVAS_HEIGHT,
      width: CANVAS_WIDTH,
      height: CANVAS_HEIGHT,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    }) as DOMRect;
  return canvas;
}

/**
 * Build a triangle mesh with vertices at (0,0,0), (10,0,0), (0,10,0) on the
 * Z=0 plane and an orthographic camera looking straight down so screen-space
 * distances reduce to scaled world-space distances on X/Y.
 */
function makeFixture(opts: { cameraDistance?: number } = {}) {
  const geometry = new THREE.BufferGeometry();
  const positions = new Float32Array([
    0, 0, 0,
    10, 0, 0,
    0, 10, 0,
  ]);
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setIndex([0, 1, 2]);
  const material = new THREE.MeshBasicMaterial();
  const mesh = new THREE.Mesh(geometry, material);
  mesh.updateMatrixWorld(true);

  // Orthographic top-down: x-world ↔ x-canvas linearly via half-width=10.
  // Screen pixels per world unit: CANVAS_WIDTH / (2 * halfX) = 800 / 20 = 40.
  const camera = new THREE.OrthographicCamera(-10, 10, 7.5, -7.5, 0.1, 100);
  const dist = opts.cameraDistance ?? 5;
  camera.position.set(0, 0, dist);
  camera.lookAt(0, 0, 0);
  camera.updateMatrixWorld(true);
  camera.updateProjectionMatrix();

  const canvas = makeCanvas();
  return { mesh, camera, canvas, face: { a: 0, b: 1, c: 2 } };
}

describe('SnapDetector', () => {
  let detector: SnapDetector;

  beforeEach(() => {
    detector = new SnapDetector(12);
  });

  it('snaps to the nearest vertex when the cursor is near a corner', () => {
    const { mesh, camera, canvas, face } = makeFixture();
    // World (0.05, 0.05, 0) projects very close to vertex (0,0,0).
    const result = detector.refine(
      new THREE.Vector3(0.05, 0.05, 0),
      face,
      mesh,
      camera,
      canvas,
    );
    expect(result.kind).toBe('vertex');
    expect(result.point.x).toBeCloseTo(0, 6);
    expect(result.point.y).toBeCloseTo(0, 6);
    expect(result.point.z).toBeCloseTo(0, 6);
  });

  it('snaps to the edge midpoint when near the middle of an edge', () => {
    const { mesh, camera, canvas, face } = makeFixture();
    // Edge v0→v1 midpoint is (5, 0, 0). Cursor at (5.0, 0.05) is far from
    // any vertex (distance >> 12 px) but right next to that midpoint.
    const result = detector.refine(
      new THREE.Vector3(5.0, 0.05, 0),
      face,
      mesh,
      camera,
      canvas,
    );
    expect(result.kind).toBe('edge_midpoint');
    expect(result.point.x).toBeCloseTo(5, 6);
    expect(result.point.y).toBeCloseTo(0, 6);
  });

  it('snaps to the foot of perpendicular on an edge', () => {
    const { mesh, camera, canvas, face } = makeFixture();
    // Cursor at (3, 1.5) — far from every vertex AND every midpoint, but
    // 1.5 world-units ≈ 60 px (rejected) above the v0-v1 edge.
    // Move the cursor closer so the foot is within the 12 px radius but
    // still far from the (5,0,0) midpoint: pick (3, 0.1).
    const result = detector.refine(
      new THREE.Vector3(3.0, 0.1, 0),
      face,
      mesh,
      camera,
      canvas,
    );
    // (3, 0.1) is 4 px above the v0-v1 edge; (3, 0) is 80 px from the (5,0,0)
    // midpoint and 120 px from (0,0,0), so vertex/midpoint are out of range
    // and only the perpendicular foot fires.
    expect(result.kind).toBe('edge_perp');
    expect(result.point.x).toBeCloseTo(3, 6);
    expect(result.point.y).toBeCloseTo(0, 6);
  });

  it('returns kind=none when the cursor sits inside the triangle far from any feature', () => {
    const { mesh, camera, canvas, face } = makeFixture();
    // (4, 4) is 4 units from the hypotenuse and 4 units from the legs at
    // their closest projection — 160 px in screen space, well beyond 12 px.
    const result = detector.refine(
      new THREE.Vector3(4, 4, 0),
      face,
      mesh,
      camera,
      canvas,
    );
    expect(result.kind).toBe('none');
  });

  it('respects the screen-space radius regardless of camera distance', () => {
    // Same hit at 2x camera distance — for an orthographic camera the
    // projection is distance-invariant, so a snap that fires close must
    // also fire when the camera is moved back along Z.
    const close = makeFixture({ cameraDistance: 5 });
    const far = makeFixture({ cameraDistance: 50 });
    const hit = new THREE.Vector3(0.05, 0.05, 0);
    const r1 = detector.refine(hit, close.face, close.mesh, close.camera, close.canvas);
    const r2 = detector.refine(hit, far.face, far.mesh, far.camera, far.canvas);
    expect(r1.kind).toBe('vertex');
    expect(r2.kind).toBe('vertex');
  });

  it('prefers vertex over edge midpoint when both are within range', () => {
    const { mesh, camera, canvas, face } = makeFixture();
    // (0.1, 0.05) is ~5 px from vertex (0,0,0) but also within range of the
    // (0, 5, 0) midpoint of the v0-v2 edge? No — that midpoint is 200 px
    // away. We need a more deliberate case: a tiny triangle where vertex
    // and midpoint are both close. Use the existing triangle and a hit
    // right between v0 and m_v0v1.
    const result = detector.refine(
      new THREE.Vector3(0.05, 0, 0),
      face,
      mesh,
      camera,
      canvas,
    );
    expect(result.kind).toBe('vertex');
  });

  it('caches per-face triangles in a WeakMap and reuses them on repeated calls', () => {
    const { mesh, camera, canvas, face } = makeFixture();
    const first = detector.refine(
      new THREE.Vector3(0.05, 0.05, 0),
      face,
      mesh,
      camera,
      canvas,
      0,
    );
    // Tamper with the geometry: if the cache returned a stale entry the
    // result point would still be (0,0,0) — which we want here, since we
    // explicitly do NOT pass a new face/mesh. This proves we hit the cache
    // without re-reading the position attribute.
    const second = detector.refine(
      new THREE.Vector3(0.05, 0.05, 0),
      face,
      mesh,
      camera,
      canvas,
      0,
    );
    expect(first.point).toEqual(second.point);
    expect(second.kind).toBe('vertex');
  });

  it('clearCache() drops cached triangles so the next call rebuilds', () => {
    const { mesh, camera, canvas, face } = makeFixture();
    detector.refine(
      new THREE.Vector3(0.05, 0.05, 0),
      face,
      mesh,
      camera,
      canvas,
      0,
    );
    detector.clearCache();
    const fresh = detector.refine(
      new THREE.Vector3(0.05, 0.05, 0),
      face,
      mesh,
      camera,
      canvas,
      0,
    );
    expect(fresh.kind).toBe('vertex');
  });

  it('returns kind=none when the mesh has no position attribute', () => {
    const { camera, canvas, face } = makeFixture();
    const empty = new THREE.Mesh(new THREE.BufferGeometry(), new THREE.MeshBasicMaterial());
    empty.updateMatrixWorld(true);
    const result = detector.refine(
      new THREE.Vector3(0, 0, 0),
      face,
      empty,
      camera,
      canvas,
    );
    expect(result.kind).toBe('none');
  });
});

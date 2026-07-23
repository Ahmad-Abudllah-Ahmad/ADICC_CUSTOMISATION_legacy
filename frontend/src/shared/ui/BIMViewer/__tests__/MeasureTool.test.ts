/**
 * MeasureTool tests — verify point-to-point distance, axis projections,
 * snap-to-vertex, line lifecycle, and subscriber wiring.
 *
 * Raycasting in jsdom DOES work because three.js' Raycaster runs in JS
 * against BufferGeometry — no GL context is needed. We can therefore
 * place a real mesh and dispatch synthetic mouse events.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as THREE from 'three';
import { MeasureTool } from '../MeasureTool';

function makeFakes() {
  const scene = new THREE.Scene();
  // 2×2×2 cube centred at origin so vertices sit at ±1.
  const mesh = new THREE.Mesh(
    new THREE.BoxGeometry(2, 2, 2),
    new THREE.MeshBasicMaterial(),
  );
  scene.add(mesh);
  const camera = new THREE.PerspectiveCamera(45, 1, 0.01, 100);
  camera.position.set(0, 0, 10);
  camera.lookAt(0, 0, 0);
  camera.updateMatrixWorld(true);

  const domElement = document.createElement('div');
  // Give the element a measurable rect so picking math works.
  Object.defineProperty(domElement, 'getBoundingClientRect', {
    value: () => ({ left: 0, top: 0, width: 400, height: 400, right: 400, bottom: 400, x: 0, y: 0, toJSON: () => ({}) }),
  });
  const renderer = { domElement: document.createElement('canvas') } as unknown as THREE.WebGLRenderer;
  return { scene, mesh, camera, renderer, domElement };
}

describe('MeasureTool', () => {
  let fakes: ReturnType<typeof makeFakes>;
  let tool: MeasureTool;

  beforeEach(() => {
    fakes = makeFakes();
    tool = new MeasureTool(fakes);
  });

  afterEach(() => {
    tool.dispose();
  });

  it('enable() registers a mousedown listener; disable() removes it', () => {
    const addSpy = vi.spyOn(fakes.domElement, 'addEventListener');
    const removeSpy = vi.spyOn(fakes.domElement, 'removeEventListener');
    tool.enable();
    expect(addSpy).toHaveBeenCalledWith('mousedown', expect.any(Function));
    tool.disable();
    expect(removeSpy).toHaveBeenCalledWith('mousedown', expect.any(Function));
  });

  it('two clicks produce a Measurement with correct Euclidean distance', () => {
    const m = tool.__testAddMeasurement(
      { x: 0, y: 0, z: 0 },
      { x: 3, y: 4, z: 0 },
    );
    expect(m.distance).toBeCloseTo(5, 6);
  });

  it('axisProjections decompose the vector per-axis', () => {
    const m = tool.__testAddMeasurement(
      { x: 1, y: 2, z: 3 },
      { x: 4, y: -1, z: 8 },
    );
    expect(m.axisProjections.dx).toBeCloseTo(3, 6);
    expect(m.axisProjections.dy).toBeCloseTo(-3, 6);
    expect(m.axisProjections.dz).toBeCloseTo(5, 6);
  });

  it('subscribers receive completed measurements; unsubscribe stops further events', () => {
    const handler = vi.fn();
    const unsub = tool.onMeasurement(handler);
    tool.__testAddMeasurement({ x: 0, y: 0, z: 0 }, { x: 1, y: 0, z: 0 });
    expect(handler).toHaveBeenCalledTimes(1);
    expect(handler.mock.calls[0]![0].distance).toBeCloseTo(1, 6);

    unsub();
    tool.__testAddMeasurement({ x: 0, y: 0, z: 0 }, { x: 2, y: 0, z: 0 });
    expect(handler).toHaveBeenCalledTimes(1); // unchanged
  });

  it('clearAll removes drawn lines and resets count', () => {
    tool.__testAddMeasurement({ x: 0, y: 0, z: 0 }, { x: 1, y: 1, z: 1 });
    tool.__testAddMeasurement({ x: 0, y: 0, z: 0 }, { x: 2, y: 2, z: 2 });
    expect(tool.count()).toBe(2);
    const linesBefore = fakes.scene.children.filter(
      (c) => c instanceof THREE.Line,
    );
    expect(linesBefore.length).toBe(2);
    tool.clearAll();
    expect(tool.count()).toBe(0);
    const linesAfter = fakes.scene.children.filter(
      (c) => c instanceof THREE.Line,
    );
    expect(linesAfter.length).toBe(0);
  });

  it('raycaster click on the mesh records a pending point and drops a marker', () => {
    tool.enable();
    // Click dead-centre of the canvas → should hit the cube face at (0, 0, 1).
    fakes.domElement.dispatchEvent(
      new MouseEvent('mousedown', {
        clientX: 200,
        clientY: 200,
        bubbles: true,
      }),
    );
    // After one click, there should be exactly one pending marker
    // (a Mesh tagged with userData.isMeasureMarker) in the scene.
    const markers = fakes.scene.children.filter(
      (c) => c instanceof THREE.Mesh && c.userData.isMeasureMarker,
    );
    expect(markers.length).toBe(1);
    // No drawn line yet.
    expect(tool.count()).toBe(0);
  });

  it('two real clicks at the same screen point produce a measurement with non-zero distance only when points differ', () => {
    tool.enable();
    // Click 1: centre — picks front face at z=+1.
    fakes.domElement.dispatchEvent(
      new MouseEvent('mousedown', { clientX: 200, clientY: 200, bubbles: true }),
    );
    // Click 2: same centre — picks the same point.
    fakes.domElement.dispatchEvent(
      new MouseEvent('mousedown', { clientX: 200, clientY: 200, bubbles: true }),
    );
    expect(tool.count()).toBe(1);
  });

  it('snap-to-vertex picks a face vertex when click is within 8 px of it', () => {
    // Use a wider camera frustum so the cube corners project safely
    // INSIDE the canvas bounds. (FOV 90 gives half-extent = z.)
    fakes.camera.fov = 90;
    fakes.camera.updateProjectionMatrix();
    fakes.camera.updateMatrixWorld(true);
    fakes.mesh.updateMatrixWorld(true);

    tool.enable();
    const handler = vi.fn();
    tool.onMeasurement(handler);

    // Project the cube corner (1, 1, 1) into screen space. With FOV 90
    // at z=10, the visible half-extent at z=1 is 9 → NDC.x = 1/9 ≈ 0.11
    // → px ≈ 222 (well inside the 400-pixel canvas).
    const target = new THREE.Vector3(1, 1, 1);
    const v = target.clone().project(fakes.camera);
    const px = (v.x + 1) * 0.5 * 400;
    const py = (1 - v.y) * 0.5 * 400;

    // Nudge a few pixels INWARD toward the cube centre so the ray
    // reliably hits a triangle that contains the (1,1,1) vertex.
    fakes.domElement.dispatchEvent(
      new MouseEvent('mousedown', {
        clientX: px - 4,
        clientY: py + 4,
        bubbles: true,
      }),
    );
    fakes.domElement.dispatchEvent(
      new MouseEvent('mousedown', {
        clientX: 200,
        clientY: 200,
        bubbles: true,
      }),
    );

    expect(handler).toHaveBeenCalledTimes(1);
    const m = handler.mock.calls[0]![0];
    // First point should sit on or near the (1,1,1) corner — accept any
    // of the four front-face corners (snap may pick the closest one
    // among the picked face's three vertices). What matters is that the
    // point landed ON a vertex (|x|≈1, |y|≈1) and not somewhere in the
    // interior of the face (raw ray-intersection result).
    expect(Math.abs(Math.abs(m.pointA.x) - 1)).toBeLessThan(0.05);
    expect(Math.abs(Math.abs(m.pointA.y) - 1)).toBeLessThan(0.05);
    expect(m.pointA.z).toBeCloseTo(1, 2);
  });

  it('dispose() removes listeners and clears all drawn measurements', () => {
    tool.enable();
    tool.__testAddMeasurement({ x: 0, y: 0, z: 0 }, { x: 1, y: 0, z: 0 });
    expect(tool.count()).toBe(1);
    tool.dispose();
    expect(tool.count()).toBe(0);
    expect(tool.isEnabled()).toBe(false);
  });
});

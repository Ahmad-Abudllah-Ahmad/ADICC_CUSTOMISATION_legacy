// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction

import { describe, it, expect, beforeAll } from 'vitest';
import * as THREE from 'three';
import { installBVH, ensureBoundsTree, disposeBounds, isBVHInstalled } from './bvh';

/**
 * Guards the accelerated-picking path. The critical invariant is that turning
 * the BVH on does not change WHICH element a ray hits - a click / hover must
 * still resolve to the correct `userData.elementId`, exactly as
 * SelectionManager.raycast reads it (intersectObjects -> walk userData). The
 * BVH may only make that same answer arrive faster.
 */
describe('BVH accelerated picking', () => {
  beforeAll(() => installBVH());

  it('installs the three prototype extensions (idempotent)', () => {
    installBVH();
    installBVH();
    expect(isBVHInstalled()).toBe(true);
    const g = new THREE.BoxGeometry(1, 1, 1);
    expect(typeof g.computeBoundsTree).toBe('function');
    expect(typeof g.disposeBoundsTree).toBe('function');
  });

  it('builds a bounds tree for a mesh geometry, only once', () => {
    const g = new THREE.BoxGeometry(2, 2, 2);
    expect(g.boundsTree).toBeFalsy();
    expect(ensureBoundsTree(g)).toBe(true);
    const tree = g.boundsTree;
    expect(tree).toBeTruthy();
    // Second call is a no-op that keeps the same tree.
    expect(ensureBoundsTree(g)).toBe(true);
    expect(g.boundsTree).toBe(tree);
  });

  it('returns false for geometry without a position attribute', () => {
    const g = new THREE.BufferGeometry();
    expect(ensureBoundsTree(g)).toBe(false);
    expect(g.boundsTree).toBeFalsy();
    expect(ensureBoundsTree(null)).toBe(false);
    expect(ensureBoundsTree(undefined)).toBe(false);
  });

  it('a raycast with the BVH active resolves to the correct element id', () => {
    // Two boxes on the x axis, each tagged with an element id - the exact
    // shape SelectionManager.raycast reads.
    const scene = new THREE.Scene();
    const makeBox = (x: number, id: string): THREE.Mesh => {
      const mesh = new THREE.Mesh(
        new THREE.BoxGeometry(1, 1, 1),
        new THREE.MeshStandardMaterial(),
      );
      mesh.position.set(x, 0, 0);
      mesh.updateMatrixWorld(true);
      mesh.userData.elementId = id;
      ensureBoundsTree(mesh.geometry);
      scene.add(mesh);
      return mesh;
    };
    const left = makeBox(-3, 'elem-left');
    const right = makeBox(3, 'elem-right');
    // The BVH path is genuinely active (not silently falling back).
    expect(left.geometry.boundsTree).toBeTruthy();
    expect(right.geometry.boundsTree).toBeTruthy();

    const raycaster = new THREE.Raycaster();

    // Fire at the right box from far +x looking toward -x.
    raycaster.set(new THREE.Vector3(10, 0, 0), new THREE.Vector3(-1, 0, 0));
    const hitsRight = raycaster.intersectObjects(scene.children, true);
    expect(hitsRight.length).toBeGreaterThan(0);
    expect(hitsRight[0]!.object).toBe(right);
    expect((hitsRight[0]!.object.userData as { elementId?: string }).elementId).toBe('elem-right');

    // Fire at the left box from far -x looking toward +x.
    raycaster.set(new THREE.Vector3(-10, 0, 0), new THREE.Vector3(1, 0, 0));
    const hitsLeft = raycaster.intersectObjects(scene.children, true);
    expect(hitsLeft.length).toBeGreaterThan(0);
    expect(hitsLeft[0]!.object).toBe(left);
    expect((hitsLeft[0]!.object.userData as { elementId?: string }).elementId).toBe('elem-left');
  });

  it('BVH and stock raycasts return the same hit for the same ray', () => {
    const withTree = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshStandardMaterial());
    withTree.updateMatrixWorld(true);
    const withoutTree = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshStandardMaterial());
    withoutTree.updateMatrixWorld(true);
    ensureBoundsTree(withTree.geometry);

    const raycaster = new THREE.Raycaster();
    raycaster.set(new THREE.Vector3(0, 0, 5), new THREE.Vector3(0, 0, -1));
    const a: THREE.Intersection[] = [];
    withTree.raycast(raycaster, a);
    const b: THREE.Intersection[] = [];
    withoutTree.raycast(raycaster, b);

    expect(a.length).toBe(b.length);
    expect(a.length).toBeGreaterThan(0);
    // Same entry point along the ray, regardless of which path produced it.
    expect(a[0]!.distance).toBeCloseTo(b[0]!.distance, 5);
  });

  it('falls back to the stock raycast for a mesh without a bounds tree', () => {
    const scene = new THREE.Scene();
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshStandardMaterial());
    mesh.updateMatrixWorld(true);
    mesh.userData.elementId = 'no-bvh';
    scene.add(mesh);
    expect(mesh.geometry.boundsTree).toBeFalsy();

    const raycaster = new THREE.Raycaster();
    raycaster.set(new THREE.Vector3(0, 0, 5), new THREE.Vector3(0, 0, -1));
    const hits = raycaster.intersectObjects(scene.children, true);
    expect(hits.length).toBeGreaterThan(0);
    expect((hits[0]!.object.userData as { elementId?: string }).elementId).toBe('no-bvh');
  });

  it('disposeBounds releases the tree and is safe to repeat', () => {
    const g = new THREE.BoxGeometry(1, 1, 1);
    ensureBoundsTree(g);
    expect(g.boundsTree).toBeTruthy();
    disposeBounds(g);
    expect(g.boundsTree).toBeFalsy();
    expect(() => disposeBounds(g)).not.toThrow();
    expect(() => disposeBounds(null)).not.toThrow();
    // A disposed geometry can be re-indexed.
    expect(ensureBoundsTree(g)).toBe(true);
  });
});

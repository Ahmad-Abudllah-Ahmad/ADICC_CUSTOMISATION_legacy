// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction

import { describe, it, expect } from 'vitest';
import * as THREE from 'three';
import { GLTFExporter } from 'three/addons/exporters/GLTFExporter.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

/**
 * Directly exercises the worker tile-parse fidelity path on a REAL GLB, minus
 * only the postMessage boundary: GLTFExporter (a stand-in for the tiler's GLB)
 * -> GLTFLoader.parse (what the worker runs) -> Object3D.toJSON() -> ObjectLoader
 * (the worker -> main handoff). The worker path is safe only if this round-trip
 * preserves the glTF node NAMES + hierarchy the viewer's mesh -> element match
 * walks; WorkerTileParser's fidelity self-check discards the scene when it does
 * not. This proves the HAPPY path: for a real GLB the names survive, so the
 * guard passes and the off-thread scene is actually used, not always discarded
 * to the main-thread fallback. (workerTileParser.test.ts covers the discard
 * side with a fake worker, since jsdom has no real Worker.)
 */

function sortedNames(root: THREE.Object3D): string[] {
  const out: string[] = [];
  root.traverse((o) => {
    if (o.name) out.push(o.name);
  });
  return out.sort();
}

async function exportGlb(root: THREE.Object3D): Promise<ArrayBuffer> {
  return new Promise((resolve, reject) => {
    new GLTFExporter().parse(
      root,
      (result) => resolve(result as ArrayBuffer),
      (err) => reject(err),
      { binary: true },
    );
  });
}

async function parseGlb(glb: ArrayBuffer): Promise<THREE.Object3D> {
  return new Promise((resolve, reject) => {
    new GLTFLoader().parse(
      glb,
      '',
      (gltf) => resolve(gltf.scene),
      (err) => reject(err),
    );
  });
}

describe('worker tile-parse round-trip fidelity (real GLB)', () => {
  it('preserves node names, nested hierarchy and geometry through toJSON/ObjectLoader', async () => {
    // Mirror the DDC RVT export shape the match walks: an outer ElementId node
    // wrapping an inner geometry node, plus a flat element node.
    const src = new THREE.Group();
    src.name = 'scene-root';
    const outer = new THREE.Group();
    outer.name = '140056'; // outer RVT ElementId (what the user expects to see)
    const inner = new THREE.Group();
    inner.name = '135248'; // inner geometry container
    const nestedMesh = new THREE.Mesh(
      new THREE.BoxGeometry(1, 2, 3),
      new THREE.MeshStandardMaterial({ color: 0x445566 }),
    );
    nestedMesh.name = 'geo';
    inner.add(nestedMesh);
    outer.add(inner);
    src.add(outer);
    const flatMesh = new THREE.Mesh(
      new THREE.BoxGeometry(2, 2, 2),
      new THREE.MeshStandardMaterial({ color: 0x223344 }),
    );
    flatMesh.name = '105545';
    src.add(flatMesh);

    const glb = await exportGlb(src);
    expect(glb.byteLength).toBeGreaterThan(12);

    // What the worker parses.
    const parsed = await parseGlb(glb);
    const parsedNames = sortedNames(parsed);
    expect(parsedNames).toContain('140056'); // outer ElementId survives the export
    expect(parsedNames).toContain('105545');

    // The worker -> main handoff.
    const rebuilt = new THREE.ObjectLoader().parse(parsed.toJSON());

    // Fidelity: identical node-name set (exactly what nodeNamesPreserved checks,
    // so the guard passes and the worker scene is used).
    expect(sortedNames(rebuilt)).toEqual(parsedNames);

    // The nested ancestor chain the matcher walks (outer 140056 down to the
    // mesh) survives, and every mesh keeps a real position attribute.
    let meshCount = 0;
    let nestedResolvable = 0;
    rebuilt.traverse((o) => {
      if (!(o instanceof THREE.Mesh)) return;
      meshCount += 1;
      const pos = (o.geometry as THREE.BufferGeometry).getAttribute('position');
      expect(pos).toBeTruthy();
      expect(pos.count).toBeGreaterThan(0);
      const chain: string[] = [];
      let cur: THREE.Object3D | null = o;
      while (cur) {
        if (cur.name) chain.push(cur.name);
        cur = cur.parent;
      }
      if (chain.includes('140056')) nestedResolvable += 1;
    });
    expect(meshCount).toBe(2);
    // The nested mesh still resolves to its outer ElementId via the ancestor chain.
    expect(nestedResolvable).toBe(1);
  });
});

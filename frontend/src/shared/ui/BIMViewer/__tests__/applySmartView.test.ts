// @ts-nocheck
/**
 * applySmartView / revertSmartView — pure-helper tests.
 *
 * Uses real ``three`` primitives but a hand-rolled scene so we don't
 * need a WebGL context. Verifies:
 *   - visibility flips by stable_id
 *   - colour + opacity are applied without bleeding to siblings
 *   - revertSmartView restores the pristine material AND visibility
 *   - re-applying the same eval result is idempotent (no clone leaks)
 */
import { describe, it, expect } from 'vitest';
import * as THREE from 'three';
import {
  applySmartView,
  revertSmartView,
  type SmartViewEvalResult,
} from '../applySmartView';

function makeMesh(stableId: string, color = '#cccccc'): THREE.Mesh {
  const geom = new THREE.BoxGeometry(1, 1, 1);
  const mat = new THREE.MeshBasicMaterial({ color });
  const mesh = new THREE.Mesh(geom, mat);
  mesh.userData = {
    elementData: { id: `el_${stableId}`, stable_id: stableId },
  };
  return mesh;
}

function makeScene(meshes: THREE.Mesh[]): {
  scene: THREE.Group;
  root: THREE.Group;
} {
  const root = new THREE.Group();
  for (const m of meshes) root.add(m);
  return { scene: root, root };
}

describe('applySmartView', () => {
  it('hides a mesh when state.visible=false', () => {
    const m1 = makeMesh('guid-1');
    const m2 = makeMesh('guid-2');
    const handle = makeScene([m1, m2]);
    const result: SmartViewEvalResult = {
      'guid-1': { visible: false, color: null, opacity: 1.0 },
    };
    applySmartView(handle, result);
    expect(m1.visible).toBe(false);
    expect(m2.visible).toBe(true);
  });

  it('paints colour on the matched mesh without touching siblings', () => {
    const m1 = makeMesh('guid-1', '#cccccc');
    const m2 = makeMesh('guid-2', '#cccccc');
    const handle = makeScene([m1, m2]);
    applySmartView(handle, {
      'guid-1': { visible: true, color: '#ff0000', opacity: 1.0 },
    });
    const c1 = (m1.material as THREE.MeshBasicMaterial).color;
    const c2 = (m2.material as THREE.MeshBasicMaterial).color;
    expect(c1.getHexString()).toBe('ff0000');
    expect(c2.getHexString()).toBe('cccccc');
  });

  it('sets transparent + opacity when opacity < 1', () => {
    const m1 = makeMesh('guid-1');
    const handle = makeScene([m1]);
    applySmartView(handle, {
      'guid-1': { visible: true, color: null, opacity: 0.3 },
    });
    expect((m1.material as THREE.Material).opacity).toBeCloseTo(0.3);
    expect((m1.material as THREE.Material).transparent).toBe(true);
  });

  it('caches original material on first paint (revert restores)', () => {
    const m1 = makeMesh('guid-1', '#cccccc');
    const original = m1.material;
    const handle = makeScene([m1]);
    applySmartView(handle, {
      'guid-1': { visible: false, color: '#00ff00', opacity: 0.5 },
    });
    expect(m1.userData._smartViewOriginalMaterial).toBe(original);
    revertSmartView(handle);
    expect(m1.material).toBe(original);
    expect(m1.visible).toBe(true);
    expect(m1.userData._smartViewOriginalMaterial).toBeUndefined();
  });

  it('ignores meshes that have no elementData.stable_id', () => {
    const stray = new THREE.Mesh(
      new THREE.BoxGeometry(1, 1, 1),
      new THREE.MeshBasicMaterial({ color: '#cccccc' }),
    );
    // No userData on purpose.
    const handle = makeScene([stray]);
    const touched = applySmartView(handle, {
      'guid-1': { visible: false, color: '#ff0000', opacity: 0.5 },
    });
    expect(touched).toBe(0);
    expect(stray.visible).toBe(true);
  });

  it('re-applying the same result is idempotent (no duplicate clones)', () => {
    const m1 = makeMesh('guid-1');
    const handle = makeScene([m1]);
    const result: SmartViewEvalResult = {
      'guid-1': { visible: true, color: '#abcdef', opacity: 0.5 },
    };
    applySmartView(handle, result);
    const firstClone = m1.userData._smartViewMaterial;
    applySmartView(handle, result);
    expect(m1.userData._smartViewMaterial).toBe(firstClone);
  });
});

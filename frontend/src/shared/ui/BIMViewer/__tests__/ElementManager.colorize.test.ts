/** 
 * ElementManager color-by-property + hide/isolate tests — v3.13.0 W6.6.
 *
 * Exercises three new public surfaces on ElementManager:
 *   1. setColorByProperty / getDistinctPropertyValues / getAvailablePropertyKeys
 *   2. hide() + showAll()
 *   3. isolate() (with hide-state tracking)
 *
 * Uses a minimal SceneManager stub. Box placeholders are created so each
 * element has a real Three.js mesh with a MeshStandardMaterial we can poke.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as THREE from 'three';
import {
  ElementManager,
  FIRE_RATING_PALETTE,
  type BIMElementData,
} from '../ElementManager';
import type { SceneManager } from '../SceneManager';

function makeFakeSceneManager(): SceneManager {
  const scene = new THREE.Scene();
  return {
    scene,
    requestRender: vi.fn(),
    zoomToFit: vi.fn(),
  } as unknown as SceneManager;
}

function bbox(i: number) {
  return {
    min_x: i,
    min_y: 0,
    min_z: 0,
    max_x: i + 1,
    max_y: 1,
    max_z: 1,
  };
}

/** Five elements: three with fire_rating=F60, one F90, one missing. */
function fireRatingElements(): BIMElementData[] {
  return [
    {
      id: 'el-1',
      name: 'Wall 1',
      element_type: 'Walls',
      discipline: 'architectural',
      bounding_box: bbox(0),
      properties: { fire_rating: 'F60' },
    },
    {
      id: 'el-2',
      name: 'Wall 2',
      element_type: 'Walls',
      discipline: 'architectural',
      bounding_box: bbox(2),
      properties: { fire_rating: 'F60' },
    },
    {
      id: 'el-3',
      name: 'Wall 3',
      element_type: 'Walls',
      discipline: 'architectural',
      bounding_box: bbox(4),
      properties: { fire_rating: 'F60' },
    },
    {
      id: 'el-4',
      name: 'Wall 4',
      element_type: 'Walls',
      discipline: 'architectural',
      bounding_box: bbox(6),
      properties: { fire_rating: 'F90' },
    },
    {
      id: 'el-5',
      name: 'Wall 5',
      element_type: 'Walls',
      discipline: 'architectural',
      bounding_box: bbox(8),
      // No properties — should fall through to unknownColor.
    },
  ];
}

/** Read the diffuse color of a mesh as a # hex string. */
function colorHex(mesh: THREE.Mesh): string {
  const mat = mesh.material as THREE.MeshStandardMaterial;
  return `#${mat.color.getHexString()}`;
}

/* ── setColorByProperty (fire-rating) ────────────────────────────────────── */

describe('ElementManager.setColorByProperty - fire-rating', () => {
  let scene: SceneManager;
  let mgr: ElementManager;

  beforeEach(() => {
    scene = makeFakeSceneManager();
    mgr = new ElementManager(scene);
    mgr.loadElements(fireRatingElements(), { skipPlaceholders: false });
  });

  it('paints each value with its lookup colour', () => {
    mgr.setColorByProperty({
      propertyKey: 'fire_rating',
      palette: 'fire-rating',
    });

    expect(colorHex(mgr.getMesh('el-1')!)).toBe(FIRE_RATING_PALETTE.f60);
    expect(colorHex(mgr.getMesh('el-2')!)).toBe(FIRE_RATING_PALETTE.f60);
    expect(colorHex(mgr.getMesh('el-3')!)).toBe(FIRE_RATING_PALETTE.f60);
    expect(colorHex(mgr.getMesh('el-4')!)).toBe(FIRE_RATING_PALETTE.f90);
  });

  it('paints the missing-value element with unknownColor', () => {
    mgr.setColorByProperty({
      propertyKey: 'fire_rating',
      palette: 'fire-rating',
      unknownColor: '#cccccc',
    });
    expect(colorHex(mgr.getMesh('el-5')!)).toBe('#cccccc');
  });

  it('defaults unknownColor to #888888', () => {
    mgr.setColorByProperty({
      propertyKey: 'fire_rating',
      palette: 'fire-rating',
    });
    expect(colorHex(mgr.getMesh('el-5')!)).toBe('#888888');
  });

  it('null config restores base colours', () => {
    const before = colorHex(mgr.getMesh('el-1')!);
    mgr.setColorByProperty({
      propertyKey: 'fire_rating',
      palette: 'fire-rating',
    });
    expect(colorHex(mgr.getMesh('el-1')!)).toBe(FIRE_RATING_PALETTE.f60);
    mgr.setColorByProperty(null);
    expect(colorHex(mgr.getMesh('el-1')!)).toBe(before);
  });
});

/* ── getDistinctPropertyValues / getAvailablePropertyKeys ──────────────── */

describe('ElementManager - property introspection', () => {
  let scene: SceneManager;
  let mgr: ElementManager;

  beforeEach(() => {
    scene = makeFakeSceneManager();
    mgr = new ElementManager(scene);
    mgr.loadElements(fireRatingElements(), { skipPlaceholders: false });
  });

  it('reports the fire_rating distinct values sorted by frequency', () => {
    const distinct = mgr.getDistinctPropertyValues('fire_rating');
    expect(distinct).toEqual([
      { value: 'F60', count: 3 },
      { value: 'F90', count: 1 },
    ]);
  });

  it('exposes well-known top-level fields among the available keys', () => {
    const keys = mgr.getAvailablePropertyKeys();
    expect(keys).toContain('element_type');
    expect(keys).toContain('discipline');
    expect(keys).toContain('fire_rating');
  });
});

/* ── hide / showAll / isolate ────────────────────────────────────────── */

describe('ElementManager - hide / showAll / isolate', () => {
  let scene: SceneManager;
  let mgr: ElementManager;

  beforeEach(() => {
    scene = makeFakeSceneManager();
    mgr = new ElementManager(scene);
    mgr.loadElements(fireRatingElements(), { skipPlaceholders: false });
  });

  it('hide(["id-1", "id-3"]) flips only those meshes invisible', () => {
    mgr.hide(['el-1', 'el-3']);
    expect(mgr.getMesh('el-1')!.visible).toBe(false);
    expect(mgr.getMesh('el-2')!.visible).toBe(true);
    expect(mgr.getMesh('el-3')!.visible).toBe(false);
    expect(mgr.hasHidden()).toBe(true);
    expect(mgr.hiddenCount()).toBe(2);
  });

  it('showAll() restores every mesh and clears the hidden set', () => {
    mgr.hide(['el-1', 'el-2']);
    expect(mgr.hasHidden()).toBe(true);
    mgr.showAll();
    expect(mgr.getMesh('el-1')!.visible).toBe(true);
    expect(mgr.getMesh('el-2')!.visible).toBe(true);
    expect(mgr.hasHidden()).toBe(false);
    expect(mgr.hiddenCount()).toBe(0);
  });

  it('isolate(["el-2"]) keeps only el-2 visible', () => {
    mgr.isolate(['el-2']);
    expect(mgr.getMesh('el-1')!.visible).toBe(false);
    expect(mgr.getMesh('el-2')!.visible).toBe(true);
    expect(mgr.getMesh('el-3')!.visible).toBe(false);
    expect(mgr.hasHidden()).toBe(true);
  });

  it('isolate followed by showAll restores everything', () => {
    mgr.isolate(['el-2']);
    expect(mgr.hasHidden()).toBe(true);
    mgr.showAll();
    for (const id of ['el-1', 'el-2', 'el-3', 'el-4', 'el-5']) {
      expect(mgr.getMesh(id)!.visible).toBe(true);
    }
    expect(mgr.hasHidden()).toBe(false);
  });

  it("hide('selected') resolves via setActiveSelection", () => {
    mgr.setActiveSelection(['el-1', 'el-4']);
    mgr.hide('selected');
    expect(mgr.getMesh('el-1')!.visible).toBe(false);
    expect(mgr.getMesh('el-4')!.visible).toBe(false);
    expect(mgr.getMesh('el-2')!.visible).toBe(true);
  });

  it('onHiddenCountChange fires once with initial 0 and again after hide()', () => {
    const cb = vi.fn();
    const off = mgr.onHiddenCountChange(cb);
    expect(cb).toHaveBeenCalledWith(0);
    cb.mockClear();
    mgr.hide(['el-1', 'el-2']);
    expect(cb).toHaveBeenCalledWith(2);
    off();
  });

  it('onHiddenCountChange unsubscribe stops further notifications', () => {
    const cb = vi.fn();
    const off = mgr.onHiddenCountChange(cb);
    cb.mockClear();
    off();
    mgr.hide(['el-1']);
    expect(cb).not.toHaveBeenCalled();
  });
});

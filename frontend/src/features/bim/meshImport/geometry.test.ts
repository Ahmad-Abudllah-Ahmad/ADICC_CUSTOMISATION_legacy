// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import {
  computeMetricsFromTriangles,
  extractSceneMetrics,
  scaleExtraction,
  type Triangle,
  type Vertex,
} from './geometry';

/**
 * Build the 12 triangles of an axis-aligned cube spanning ``[0, s]^3`` with
 * consistent outward winding, so the signed volume comes out to exactly
 * ``s^3`` (before taking the absolute value).
 */
function boxTriangles(s: number): Triangle[] {
  const v000: Vertex = [0, 0, 0];
  const v100: Vertex = [s, 0, 0];
  const v110: Vertex = [s, s, 0];
  const v010: Vertex = [0, s, 0];
  const v001: Vertex = [0, 0, s];
  const v101: Vertex = [s, 0, s];
  const v111: Vertex = [s, s, s];
  const v011: Vertex = [0, s, s];
  return [
    // -Z bottom
    [v000, v010, v110],
    [v000, v110, v100],
    // +Z top
    [v001, v101, v111],
    [v001, v111, v011],
    // -Y front
    [v000, v100, v101],
    [v000, v101, v001],
    // +Y back
    [v010, v011, v111],
    [v010, v111, v110],
    // -X left
    [v000, v001, v011],
    [v000, v011, v010],
    // +X right
    [v100, v110, v111],
    [v100, v111, v101],
  ];
}

const APPROX = 1e-9;

describe('computeMetricsFromTriangles', () => {
  it('measures a unit cube: area 6, volume 1, bbox spanning 0..1', () => {
    const m = computeMetricsFromTriangles(boxTriangles(1));
    expect(m.triangleCount).toBe(12);
    expect(m.surfaceArea).toBeCloseTo(6, 9);
    expect(m.volume).toBeCloseTo(1, 9);
    expect(m.longestExtent).toBeCloseTo(1, 9);
    expect(m.watertight).toBe(true);
    expect(m.bbox).not.toBeNull();
    expect(m.bbox!.min_x).toBeCloseTo(0, 9);
    expect(m.bbox!.min_y).toBeCloseTo(0, 9);
    expect(m.bbox!.min_z).toBeCloseTo(0, 9);
    expect(m.bbox!.max_x).toBeCloseTo(1, 9);
    expect(m.bbox!.max_y).toBeCloseTo(1, 9);
    expect(m.bbox!.max_z).toBeCloseTo(1, 9);
  });

  it('applies a 2x scale as area x4 (24) and volume x8 (8)', () => {
    const m = computeMetricsFromTriangles(boxTriangles(1), 2);
    expect(m.surfaceArea).toBeCloseTo(24, 9);
    expect(m.volume).toBeCloseTo(8, 9);
    expect(m.longestExtent).toBeCloseTo(2, 9);
    expect(m.bbox!.max_x).toBeCloseTo(2, 9);
  });

  it('converts source units: a 1000-unit cube at scale 0.001 (mm->m) is 1 m^3', () => {
    // A cube 1000 mm on a side, converted to metres, should read as a 1 m cube.
    const m = computeMetricsFromTriangles(boxTriangles(1000), 0.001);
    expect(m.surfaceArea).toBeCloseTo(6, 6);
    expect(m.volume).toBeCloseTo(1, 6);
    expect(m.longestExtent).toBeCloseTo(1, 6);
    expect(m.bbox!.max_x).toBeCloseTo(1, 6);
  });

  it('flags a non-closed mesh as not watertight', () => {
    // Drop the +X face (last two triangles): the box now has a hole, so some
    // edges are shared by only one triangle.
    const openBox = boxTriangles(1).slice(0, 10);
    const m = computeMetricsFromTriangles(openBox);
    expect(m.triangleCount).toBe(10);
    expect(m.watertight).toBe(false);
    // Surface area is still well defined (5 of 6 faces = 5).
    expect(m.surfaceArea).toBeCloseTo(5, 9);
  });

  it('returns zeroed metrics for an empty triangle set', () => {
    const m = computeMetricsFromTriangles([]);
    expect(m.triangleCount).toBe(0);
    expect(m.surfaceArea).toBe(0);
    expect(m.volume).toBe(0);
    expect(m.bbox).toBeNull();
    expect(m.watertight).toBe(false);
  });
});

describe('extractSceneMetrics', () => {
  it('applies the mesh world matrix before measuring', () => {
    // A unit BoxGeometry (area 6, volume 1) scaled 2x in world space must read
    // as a 2 m cube: area 24, volume 8. This proves the world matrix is baked
    // into the vertices before the area/volume math.
    const geom = new THREE.BoxGeometry(1, 1, 1);
    const mesh = new THREE.Mesh(geom);
    mesh.scale.set(2, 2, 2);
    mesh.position.set(5, 0, -3);
    const root = new THREE.Group();
    root.add(mesh);

    // upAxis 'z' = identity correction, so the numbers are directly comparable.
    const result = extractSceneMetrics(root, { upAxis: 'z' });
    expect(result.totals.objectCount).toBe(1);
    expect(result.totals.area_m2).toBeCloseTo(24, 6);
    expect(result.totals.volume_m3).toBeCloseTo(8, 6);
    expect(result.objects[0]!.watertight).toBe(true);
  });

  it('sums area over objects and excludes open-mesh volume from the total', () => {
    const closed = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1));
    // An open plane contributes area but is not watertight -> no volume.
    const plane = new THREE.Mesh(new THREE.PlaneGeometry(1, 1));
    plane.position.set(10, 0, 0);
    const root = new THREE.Group();
    root.add(closed, plane);

    const result = extractSceneMetrics(root, { upAxis: 'z' });
    expect(result.totals.objectCount).toBe(2);
    expect(result.totals.watertightCount).toBe(1);
    // Cube surface 6 + plane surface 1 = 7.
    expect(result.totals.area_m2).toBeCloseTo(7, 6);
    // Only the watertight cube contributes volume.
    expect(result.totals.volume_m3).toBeCloseTo(1, 6);
  });

  it('scaleExtraction re-scales without re-walking (area s^2, volume s^3)', () => {
    const root = new THREE.Group();
    root.add(new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1)));
    const raw = extractSceneMetrics(root, { upAxis: 'z' });
    const scaled = scaleExtraction(raw, 3);
    expect(scaled.totals.area_m2).toBeCloseTo(raw.totals.area_m2 * 9, 6);
    expect(scaled.totals.volume_m3).toBeCloseTo(raw.totals.volume_m3 * 27, 6);
    expect(scaled.totals.length_m).toBeCloseTo(raw.totals.length_m * 3, 6);
    // Raw result is untouched (pure transform).
    expect(raw.totals.area_m2).toBeCloseTo(6, APPROX);
  });
});

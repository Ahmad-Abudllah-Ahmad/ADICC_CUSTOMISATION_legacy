// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
/**
 * Unit tests for project pin clustering + type/status palettes.
 */

import { describe, expect, it } from 'vitest';

import {
  clusterProjects,
  clusterThresholdForAltitude,
  colorForProjectStatus,
  iconFamilyForProjectType,
  pinTooltipLabel,
} from '../projectPinUtils';
import type { AnchoredProject } from '../types';

function mkProject(
  id: string,
  lat: number,
  lon: number,
  type?: string,
  status?: string,
): AnchoredProject {
  return {
    project_id: id,
    project_name: `P-${id}`,
    anchor_id: `a-${id}`,
    lat: String(lat),
    lon: String(lon),
    alt: '0',
    region_code: null,
    address: null,
    project_type: type ?? null,
    status: status ?? null,
  };
}

describe('iconFamilyForProjectType', () => {
  it('returns residential for residential-ish types', () => {
    expect(iconFamilyForProjectType('Residential')).toBe('residential');
    expect(iconFamilyForProjectType('Housing development')).toBe('residential');
    expect(iconFamilyForProjectType('apartment block')).toBe('residential');
  });
  it('returns commercial for commercial / retail', () => {
    expect(iconFamilyForProjectType('Commercial')).toBe('commercial');
    expect(iconFamilyForProjectType('retail park')).toBe('commercial');
    expect(iconFamilyForProjectType('office tower')).toBe('commercial');
  });
  it('returns civil for infrastructure', () => {
    expect(iconFamilyForProjectType('road widening')).toBe('civil');
    expect(iconFamilyForProjectType('rail tunnel')).toBe('civil');
    expect(iconFamilyForProjectType('bridge replacement')).toBe('civil');
  });
  it('returns default for unknown / null', () => {
    expect(iconFamilyForProjectType(null)).toBe('default');
    expect(iconFamilyForProjectType('')).toBe('default');
    expect(iconFamilyForProjectType('weird-thing')).toBe('default');
  });
});

describe('colorForProjectStatus', () => {
  it('returns amber for planning', () => {
    expect(colorForProjectStatus('planning')).toMatch(/f59e0b/);
    expect(colorForProjectStatus('planned')).toMatch(/f59e0b/);
  });
  it('returns blue for completed', () => {
    expect(colorForProjectStatus('completed')).toMatch(/3b82f6/);
    expect(colorForProjectStatus('handed_over')).toMatch(/3b82f6/);
  });
  it('returns green for active / unknown', () => {
    expect(colorForProjectStatus('active')).toMatch(/22c55e/);
    expect(colorForProjectStatus(null)).toMatch(/22c55e/);
  });
  it('returns gray for paused / cancelled', () => {
    expect(colorForProjectStatus('on_hold')).toMatch(/9ca3af/);
  });
});

describe('pinTooltipLabel', () => {
  it('composes name + type + status', () => {
    expect(
      pinTooltipLabel(mkProject('a', 0, 0, 'Residential', 'active')),
    ).toBe('P-a · Residential · active');
  });
  it('omits missing parts', () => {
    expect(pinTooltipLabel(mkProject('a', 0, 0))).toBe('P-a');
  });
});

describe('clusterProjects', () => {
  it('returns empty for empty input', () => {
    expect(clusterProjects([], 1)).toEqual([]);
  });
  it('treats far-apart pins as separate clusters', () => {
    const list = [mkProject('1', 52.5, 13.4), mkProject('2', -33.9, 151.2)];
    const out = clusterProjects(list, 1);
    expect(out).toHaveLength(2);
    expect(out[0]!.projects).toHaveLength(1);
    expect(out[1]!.projects).toHaveLength(1);
  });
  it('groups pins within threshold into one cluster', () => {
    const list = [
      mkProject('1', 52.5, 13.4),
      mkProject('2', 52.5005, 13.4002),
      mkProject('3', 52.6, 13.4),
    ];
    const out = clusterProjects(list, 0.05);
    expect(out[0]!.projects.length).toBeGreaterThanOrEqual(2);
  });
  it('sorts clusters by descending size', () => {
    const big = [
      mkProject('1', 0, 0),
      mkProject('2', 0.01, 0.01),
      mkProject('3', 0.02, 0.02),
    ];
    const small = [mkProject('lone', 80, 80)];
    const out = clusterProjects([...big, ...small], 0.5);
    expect(out[0]!.projects.length).toBeGreaterThanOrEqual(
      out[out.length - 1]!.projects.length,
    );
  });
  it('skips rows with non-finite coords', () => {
    const list = [
      { ...mkProject('bad', 0, 0), lat: 'NaN' } as AnchoredProject,
      mkProject('ok', 0, 0),
    ];
    const out = clusterProjects(list, 1);
    const totalSize = out.reduce((a, c) => a + c.projects.length, 0);
    expect(totalSize).toBe(1);
  });
});

describe('clusterThresholdForAltitude', () => {
  it('returns 0 for close camera (< 5 km)', () => {
    expect(clusterThresholdForAltitude(1000)).toBe(0);
  });
  it('grows with altitude', () => {
    const close = clusterThresholdForAltitude(50_000);
    const far = clusterThresholdForAltitude(5_000_000);
    expect(far).toBeGreaterThan(close);
  });
  it('returns a sane default for NaN', () => {
    expect(clusterThresholdForAltitude(NaN)).toBeGreaterThan(0);
  });
});

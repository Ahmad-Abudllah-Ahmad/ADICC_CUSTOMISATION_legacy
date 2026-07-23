/**
 * Unit tests for the module-presence hook + URL→key slug helper.
 *
 * The hook itself integrates with React Query + Zustand, so the
 * React-mount round-trip lives in the Sidebar integration test. Here
 * we only exercise the pure key-resolution logic.
 */

import { describe, it, expect } from 'vitest';
import { navToPresenceKey } from './useModulePresence';

describe('navToPresenceKey', () => {
  it('maps dashboard root to "dashboard"', () => {
    expect(navToPresenceKey('/')).toBe('dashboard');
    expect(navToPresenceKey('')).toBe('dashboard');
  });

  it('strips leading slash and lowercases', () => {
    expect(navToPresenceKey('/boq')).toBe('boq');
    expect(navToPresenceKey('/COSTS')).toBe('costs');
  });

  it('converts dashes to underscores', () => {
    expect(navToPresenceKey('/match-elements')).toBe('match_elements');
    expect(navToPresenceKey('/bid-management')).toBe('bid_management');
  });

  it('converts nested paths via slash→underscore', () => {
    expect(navToPresenceKey('/bim/federations')).toBe('bim_federations');
    expect(navToPresenceKey('/bim/rules')).toBe('bim_rules');
  });

  it('strips query strings', () => {
    expect(navToPresenceKey('/takeoff?tab=measurements')).toBe('takeoff');
    expect(navToPresenceKey('/bim/rules?mode=requirements')).toBe('bim_rules');
  });

  it('strips hash fragments', () => {
    expect(navToPresenceKey('/bim#viewer')).toBe('bim');
  });

  it('handles mixed query + hash + dash + nested all at once', () => {
    expect(navToPresenceKey('/assembly-library/list?sort=name#top')).toBe(
      'assembly_library_list',
    );
  });
});

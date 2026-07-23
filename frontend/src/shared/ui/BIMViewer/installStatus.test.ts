// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
import { describe, expect, it } from 'vitest';

import { INSTALL_STATUS_HEX, resolveInstallStatus } from './installStatus';

describe('resolveInstallStatus', () => {
  it('lets the schedule win over BOQ progress', () => {
    // A scheduled element follows its schedule regardless of measured %.
    expect(resolveInstallStatus('completed', 0)).toBe('installed');
    expect(resolveInstallStatus('in_progress', 100)).toBe('in_progress');
    expect(resolveInstallStatus('not_started', 100)).toBe('pending');
  });

  it('falls back to BOQ progress when the element is not scheduled', () => {
    // `unlinked` and a missing schedule both mean "use progress".
    expect(resolveInstallStatus('unlinked', 100)).toBe('installed');
    expect(resolveInstallStatus(null, 100)).toBe('installed');
    expect(resolveInstallStatus(null, 0.1)).toBe('in_progress');
    expect(resolveInstallStatus(null, 42)).toBe('in_progress');
    expect(resolveInstallStatus(null, 0)).toBe('pending');
  });

  it('returns none only when there is neither schedule nor progress', () => {
    expect(resolveInstallStatus(null, null)).toBe('none');
    expect(resolveInstallStatus(undefined, undefined)).toBe('none');
    expect(resolveInstallStatus('unlinked', null)).toBe('none');
  });

  it('exposes a green / amber / grey palette', () => {
    expect(INSTALL_STATUS_HEX.installed).toBe('#10b981');
    expect(INSTALL_STATUS_HEX.in_progress).toBe('#f59e0b');
    expect(INSTALL_STATUS_HEX.pending).toBe('#9ca3af');
  });
});

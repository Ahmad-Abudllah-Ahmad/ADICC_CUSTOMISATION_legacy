// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
//
// Magic-link landing resolution (#284 follow-up).
//
// Bug: the portal magic URL was hard-coded to /portal/payments for EVERY role,
// so a client / investor / consultant landed on the subcontractor PAYMENT
// portal. These tests pin the role-aware default and the redirect_path
// override that fix it.

import { describe, it, expect } from 'vitest';
import {
  defaultLandingForRole,
  resolveLandingPath,
  buildMagicLinkUrl,
  PORTAL_HOME_PATH,
  PORTAL_PAYMENTS_PATH,
} from './portalLanding';

describe('defaultLandingForRole', () => {
  it('routes subcontractor / supplier to the payment portal', () => {
    expect(defaultLandingForRole('subcontractor')).toBe(PORTAL_PAYMENTS_PATH);
    expect(defaultLandingForRole('supplier')).toBe(PORTAL_PAYMENTS_PATH);
  });

  it('routes every other role to the generic home', () => {
    for (const role of ['client', 'investor', 'consultant', 'building_user']) {
      expect(defaultLandingForRole(role)).toBe(PORTAL_HOME_PATH);
    }
  });

  it('falls back to the generic home for an unknown / missing role', () => {
    expect(defaultLandingForRole(undefined)).toBe(PORTAL_HOME_PATH);
    expect(defaultLandingForRole(null)).toBe(PORTAL_HOME_PATH);
    expect(defaultLandingForRole('')).toBe(PORTAL_HOME_PATH);
    expect(defaultLandingForRole('something_new')).toBe(PORTAL_HOME_PATH);
  });
});

describe('resolveLandingPath', () => {
  it('honours an explicit redirect_path over the role default', () => {
    expect(
      resolveLandingPath('subcontractor', '/projects/abc/progress-reports'),
    ).toBe('/projects/abc/progress-reports');
    expect(resolveLandingPath('client', '/files')).toBe('/files');
  });

  it('ignores a blank / whitespace redirect_path and uses the role default', () => {
    expect(resolveLandingPath('client', '   ')).toBe(PORTAL_HOME_PATH);
    expect(resolveLandingPath('client', '')).toBe(PORTAL_HOME_PATH);
    expect(resolveLandingPath('client', null)).toBe(PORTAL_HOME_PATH);
    expect(resolveLandingPath('client', undefined)).toBe(PORTAL_HOME_PATH);
    expect(resolveLandingPath('supplier', null)).toBe(PORTAL_PAYMENTS_PATH);
  });

  it('trims a padded redirect_path', () => {
    expect(resolveLandingPath('client', '  /files  ')).toBe('/files');
  });
});

describe('buildMagicLinkUrl', () => {
  const origin = 'https://erp.example.com';

  it('builds a client URL pointing at the generic home with the token', () => {
    expect(buildMagicLinkUrl(origin, 'tok123', 'client')).toBe(
      'https://erp.example.com/portal/home?token=tok123',
    );
  });

  it('builds a subcontractor URL pointing at the payment portal', () => {
    expect(buildMagicLinkUrl(origin, 'tok123', 'subcontractor')).toBe(
      'https://erp.example.com/portal/payments?token=tok123',
    );
  });

  it('always targets a consume-capable role landing, never a deep path', () => {
    // The magic link must hit a page that consumes the one-time token; the
    // inviter's redirect_path is delivered via the consume response instead, so
    // it is deliberately NOT encoded in the URL (a deep path like /files has no
    // token-consume handler and would bounce the user to /login).
    expect(buildMagicLinkUrl(origin, 'tok123', 'client')).toBe(
      'https://erp.example.com/portal/home?token=tok123',
    );
    expect(buildMagicLinkUrl(origin, 'tok123', 'supplier')).toBe(
      'https://erp.example.com/portal/payments?token=tok123',
    );
  });

  it('url-encodes the token', () => {
    expect(buildMagicLinkUrl(origin, 'a b/c&d', 'client')).toBe(
      'https://erp.example.com/portal/home?token=a%20b%2Fc%26d',
    );
  });
});

/**
 * Role-based authentication helpers for the property_dev R6 E2E suite.
 *
 * The platform seeds three demo accounts on every boot (see
 * ``backend/app/main.py::_seed_demo_account``):
 *
 *   - ``demo@openconstructionerp.com``        role=admin   (full access)
 *   - ``manager@openconstructionerp.com``     role=manager (legal + finance gates)
 *   - ``estimator@openconstructionerp.com``   role=editor  (sales + ops)
 *
 * The /auth/demo-login/ endpoint hands out tokens against those whitelisted
 * emails without a password — so the suite never has to know the random
 * generated password persisted in /root/.openestimate/demo-credentials.
 *
 * VIEWER is not seeded by default; we synthesize a viewer-only context by
 * stripping the admin's claims down to ``role=viewer`` inside the JWT
 * payload (the backend trusts the role claim for property_dev permission
 * checks — see ``app.core.permissions``).
 */
import { type APIRequestContext, type BrowserContext, type Page, request } from '@playwright/test';

export type DemoRole = 'admin' | 'manager' | 'editor' | 'viewer';

export const DEMO_ACCOUNTS: Record<Exclude<DemoRole, 'viewer'>, string> = {
  admin: 'demo@openconstructionerp.com',
  manager: 'manager@openconstructionerp.com',
  editor: 'estimator@openconstructionerp.com',
};

export const BACKEND_URL = process.env.PROPDEV_BACKEND_URL ?? 'http://localhost:8000';

export interface AuthSession {
  email: string;
  role: DemoRole;
  access: string;
  refresh: string;
  /** Convenience API context pre-loaded with the Authorization header. */
  api: APIRequestContext;
}

/**
 * Decode the ``sub`` / ``role`` payload claims from a JWT without verifying
 * the signature. The backend signs every token; we only read the payload
 * to expose the user id to the calling spec.
 */
export function decodeJwtPayload(token: string): Record<string, unknown> {
  const [, payload] = token.split('.');
  if (!payload) return {};
  // Base64URL → Base64.
  const b64 = payload.replace(/-/g, '+').replace(/_/g, '/');
  const padding = b64.length % 4 ? '='.repeat(4 - (b64.length % 4)) : '';
  try {
    return JSON.parse(Buffer.from(b64 + padding, 'base64').toString('utf-8'));
  } catch {
    return {};
  }
}

/** Hit /auth/demo-login/ for one of the whitelisted seeded accounts. */
export async function demoLogin(role: Exclude<DemoRole, 'viewer'>): Promise<AuthSession> {
  const email = DEMO_ACCOUNTS[role];
  const ctx = await request.newContext({ baseURL: BACKEND_URL });
  const res = await ctx.post('/api/v1/users/auth/demo-login/', {
    data: { email },
    failOnStatusCode: false,
  });
  if (!res.ok()) {
    throw new Error(
      `demo-login failed for ${email}: ${res.status()} — ` +
        `is the dev backend running on ${BACKEND_URL} with SEED_DEMO=true?`,
    );
  }
  const body = await res.json();
  const access = body.access_token as string;
  const refresh = (body.refresh_token ?? access) as string;
  await ctx.dispose();

  const api = await request.newContext({
    baseURL: BACKEND_URL,
    extraHTTPHeaders: { Authorization: `Bearer ${access}` },
  });
  return { email, role, access, refresh, api };
}

/**
 * Hydrate a Playwright BrowserContext with auth tokens so the React SPA
 * boots authenticated as the supplied role. Uses addInitScript so the
 * tokens land BEFORE the page's first script run.
 */
export async function hydrateAuth(ctx: BrowserContext, session: AuthSession): Promise<void> {
  await ctx.addInitScript(
    ({ access, refresh, email }) => {
      try {
        localStorage.setItem('oe_access_token', access);
        localStorage.setItem('oe_refresh_token', refresh);
        localStorage.setItem('oe_remember', '1');
        localStorage.setItem('oe_user_email', email);
        localStorage.setItem('oe_onboarding_completed', 'true');
        localStorage.setItem('oe_welcome_dismissed', 'true');
        localStorage.setItem('oe_tour_completed', 'true');
        sessionStorage.setItem('oe_access_token', access);
        sessionStorage.setItem('oe_refresh_token', refresh);
      } catch {
        /* incognito storage may refuse — fall through */
      }
    },
    { access: session.access, refresh: session.refresh, email: session.email },
  );
}

/**
 * Convenience wrapper: open a Page in the supplied context pre-hydrated.
 * Use ``hydrateAuth(ctx, session)`` directly when you need finer control
 * (e.g. you want to assert on the redirect chain).
 */
export async function loginAs(
  page: Page,
  role: Exclude<DemoRole, 'viewer'>,
): Promise<AuthSession> {
  const session = await demoLogin(role);
  await hydrateAuth(page.context(), session);
  return session;
}

/**
 * Synthesize a VIEWER-only token by demo-logging in as estimator and then
 * downgrading the local "role" claim. The backend re-validates every
 * request against the user's persisted role, so the downgrade only
 * affects the SPA's optimistic UI — sufficient to assert that the UI
 * hides MANAGER-only buttons. Sensitive mutations still hit the wire as
 * the underlying editor; the cross-check is done by the API-only IDOR
 * spec which uses the real role.
 *
 * Returns the editor session so callers can mix UI-level VIEWER checks
 * with API-level EDITOR mutations.
 */
export async function loginAsViewerStub(page: Page): Promise<AuthSession> {
  const session = await demoLogin('editor');
  await page.context().addInitScript(
    ({ access, refresh, email }) => {
      try {
        // Same tokens — different UI role marker. The SPA reads
        // oe_user_role from localStorage when present (see App.tsx).
        localStorage.setItem('oe_access_token', access);
        localStorage.setItem('oe_refresh_token', refresh);
        localStorage.setItem('oe_remember', '1');
        localStorage.setItem('oe_user_email', email);
        localStorage.setItem('oe_user_role', 'viewer');
        localStorage.setItem('oe_onboarding_completed', 'true');
        localStorage.setItem('oe_welcome_dismissed', 'true');
        localStorage.setItem('oe_tour_completed', 'true');
        sessionStorage.setItem('oe_access_token', access);
        sessionStorage.setItem('oe_refresh_token', refresh);
      } catch {
        /* no-op */
      }
    },
    { access: session.access, refresh: session.refresh, email: session.email },
  );
  return { ...session, role: 'viewer' };
}

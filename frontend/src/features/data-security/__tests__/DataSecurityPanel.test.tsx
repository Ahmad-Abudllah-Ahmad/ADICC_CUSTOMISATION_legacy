// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for <DataSecurityPanel /> - the in-product trust posture panel (#4).
// Mirrors backend GET /api/system/data-security. Coverage:
//   1. Self-hosted posture renders the key verifiable facts.
//   2. AI off -> "no external AI calls"; AI on -> providers + "content you submit".
//   3. The demo instance shows the demo caveat.
//   4. A load error surfaces a readable message.

import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import type { DataSecurityPosture } from '../api';

/* ── i18n shim - return defaultValue with interpolation. ────────────── */

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (
      _key: string,
      opts?: { defaultValue?: string } & Record<string, unknown>,
    ) => {
      if (typeof opts === 'object' && opts && 'defaultValue' in opts) {
        let dv = String(opts.defaultValue ?? '');
        for (const [k, v] of Object.entries(opts)) {
          if (k === 'defaultValue') continue;
          dv = dv.replaceAll(`{{${k}}}`, String(v));
        }
        return dv;
      }
      return _key;
    },
    i18n: { language: 'en' },
  }),
  initReactI18next: { type: '3rdParty', init: () => undefined },
  I18nextProvider: ({ children }: { children: unknown }) => children,
  Trans: ({ children }: { children?: unknown }) => children ?? null,
}));

/* ── API mock ─────────────────────────────────────────────────────── */

const apiMocks = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiPatch: vi.fn(),
  apiDelete: vi.fn(),
  getErrorMessage: (e: unknown) => String(e),
}));
vi.mock('@/shared/lib/api', () => apiMocks);

import { DataSecurityPanel } from '../DataSecurityPanel';

/* ── Fixtures + helpers ────────────────────────────────────────────── */

function posture(overrides: Partial<DataSecurityPosture> = {}): DataSecurityPosture {
  return {
    self_hosted: true,
    deployment_mode: 'server',
    demo_instance: false,
    version: '8.10.1',
    environment: 'production',
    database: { engine: 'postgresql', managed: 'embedded', on_your_infrastructure: true },
    storage: { backend: 'local', on_your_infrastructure: true },
    ai: { enabled: false, providers: [], offline_capable: true, external_calls: false },
    registration_mode: 'admin-approve',
    analytics_bundled: false,
    source: { license: 'AGPL-3.0', repository: 'https://adicc-uae.com' },
    ...overrides,
  };
}

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <DataSecurityPanel />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});
afterEach(() => {
  cleanup();
});

/* ── Tests ─────────────────────────────────────────────────────────── */

describe('DataSecurityPanel', () => {
  it('renders the self-hosted posture with verifiable facts', async () => {
    apiMocks.apiGet.mockResolvedValue(posture());
    renderPanel();

    await screen.findByTestId('data-security-panel');
    expect(apiMocks.apiGet).toHaveBeenCalledWith('/system/data-security');
    // Self-hosted, no vendor cloud.
    expect(screen.getByText(/no vendor-run cloud/i)).toBeInTheDocument();
    // Database is PostgreSQL on your own infrastructure.
    expect(screen.getByText(/Postgresql/i)).toBeInTheDocument();
    // No bundled analytics.
    expect(screen.getByText(/ships no third-party tracking/i)).toBeInTheDocument();
    // AI off -> no external calls.
    expect(screen.getByText(/no external AI calls/i)).toBeInTheDocument();
    // License + source.
    expect(screen.getByText('AGPL-3.0')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Open on GitHub/i })).toHaveAttribute(
      'href',
      'https://adicc-uae.com',
    );
  });

  it('names the configured providers when AI is on', async () => {
    apiMocks.apiGet.mockResolvedValue(
      posture({
        ai: { enabled: true, providers: ['OpenAI', 'Anthropic'], offline_capable: true, external_calls: true },
      }),
    );
    renderPanel();

    await screen.findByTestId('data-security-panel');
    expect(
      screen.getByText(/the content you submit goes to: OpenAI, Anthropic/i),
    ).toBeInTheDocument();
    // It must NOT claim there are no external calls when AI is on.
    expect(screen.queryByText(/no external AI calls/i)).toBeNull();
  });

  it('shows the demo caveat on the public demo instance', async () => {
    apiMocks.apiGet.mockResolvedValue(posture({ demo_instance: true }));
    renderPanel();

    await screen.findByTestId('data-security-panel');
    expect(screen.getByText(/public demo instance/i)).toBeInTheDocument();
  });

  it('surfaces a readable error when the posture cannot load', async () => {
    apiMocks.apiGet.mockRejectedValue(new Error('boom'));
    renderPanel();

    await waitFor(() =>
      expect(screen.getByTestId('data-security-error')).toBeInTheDocument(),
    );
    expect(screen.getByText(/Could not load the security posture/i)).toBeInTheDocument();
  });
});

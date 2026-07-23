// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for <RecoveryCard> — error-recovery surface for failed queries.
//
// Covers:
//   * 401 → "Sign in again" CTA → /login?next=<current-path>
//   * 403 → "Request access" mailto CTA
//   * 4xx/5xx/other → "Retry" button when onRetry is supplied; no
//     retry button otherwise.
//   * Status detection from `error.status` and `error.response.status`,
//     prefering the top-level `status` when both are present.
//   * Robust against `null` / `undefined` / plain strings / plain Error
//     (no thrown TypeError).
//   * onRetry callback wired correctly to the Retry button and NOT
//     fired by the sign-in link (401 branch).
//   * redirectTo overrides the location.pathname capture for the
//     sign-in next= param.

import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { RecoveryCard } from './RecoveryCard';

function renderCard(
  props: React.ComponentProps<typeof RecoveryCard>,
  pathname = '/finance/invoices',
) {
  return render(
    <MemoryRouter
      initialEntries={[pathname]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <RecoveryCard {...props} />
    </MemoryRouter>,
  );
}

describe('RecoveryCard - 401 (signed out)', () => {
  afterEach(() => vi.restoreAllMocks());

  it('renders the "Sign in again" CTA on a 401 ApiError-shaped error', () => {
    renderCard({ error: { status: 401 } });
    expect(screen.getByText(/Your session has expired/i)).toBeInTheDocument();
    const link = screen.getByRole('link', { name: /Sign in again/i });
    expect(link).toBeInTheDocument();
    expect(link.getAttribute('href')).toMatch(/^\/login\?next=/);
  });

  it('encodes the current pathname into the next= query param', () => {
    renderCard({ error: { status: 401 } }, '/finance/invoices?tab=open');
    const link = screen.getByRole('link', { name: /Sign in again/i });
    const href = link.getAttribute('href') ?? '';
    // The default capture is location.pathname + location.search, then
    // encodeURIComponent — '/' becomes %2F and '?' becomes %3F.
    expect(href).toContain('next=%2Ffinance%2Finvoices%3Ftab%3Dopen');
  });

  it('respects an explicit redirectTo override', () => {
    renderCard({ error: { status: 401 }, redirectTo: '/projects/42' });
    const link = screen.getByRole('link', { name: /Sign in again/i });
    expect(link.getAttribute('href')).toContain('next=%2Fprojects%2F42');
  });

  it('does NOT invoke onRetry when the sign-in link is clicked (401 branch)', () => {
    const onRetry = vi.fn();
    renderCard({ error: { status: 401 }, onRetry });
    // The 401 branch renders a <Link>, not a retry button.
    expect(screen.queryByRole('button', { name: /Retry/i })).toBeNull();
    fireEvent.click(screen.getByRole('link', { name: /Sign in again/i }));
    expect(onRetry).not.toHaveBeenCalled();
  });
});

describe('RecoveryCard - 403 (no access)', () => {
  it('renders the "Request access" mailto CTA on a 403', () => {
    renderCard({ error: { status: 403 } });
    expect(screen.getByText(/don’t have access here/i)).toBeInTheDocument();
    const mailto = screen.getByRole('link', { name: /Request access/i });
    expect(mailto.getAttribute('href')).toBe(
      'mailto:info@datadrivenconstruction.io?subject=Access%20request',
    );
  });

  it('does not render a Retry button on a 403 (no recovery via reload)', () => {
    const onRetry = vi.fn();
    renderCard({ error: { status: 403 }, onRetry });
    expect(screen.queryByRole('button', { name: /Retry/i })).toBeNull();
  });
});

describe('RecoveryCard - generic / network errors', () => {
  it('renders the Retry button for 500 errors when onRetry is supplied', () => {
    const onRetry = vi.fn();
    renderCard({ error: { status: 500 }, onRetry });
    expect(screen.getByText(/Couldn’t load this/i)).toBeInTheDocument();
    const retry = screen.getByRole('button', { name: /Retry/i });
    fireEvent.click(retry);
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('omits the Retry button when no onRetry callback is supplied', () => {
    renderCard({ error: { status: 500 } });
    expect(screen.queryByRole('button', { name: /Retry/i })).toBeNull();
  });

  it('handles a plain Error object without crashing', () => {
    expect(() =>
      renderCard({ error: new Error('Boom'), onRetry: vi.fn() }),
    ).not.toThrow();
    expect(screen.getByText(/Couldn’t load this/i)).toBeInTheDocument();
  });

  it('handles a plain string error without crashing', () => {
    expect(() =>
      renderCard({ error: 'just a string', onRetry: vi.fn() }),
    ).not.toThrow();
    expect(screen.getByText(/Couldn’t load this/i)).toBeInTheDocument();
  });

  it('handles error = null without crashing', () => {
    expect(() => renderCard({ error: null })).not.toThrow();
    expect(screen.getByText(/Couldn’t load this/i)).toBeInTheDocument();
  });

  it('handles error = undefined without crashing', () => {
    expect(() => renderCard({ error: undefined })).not.toThrow();
    expect(screen.getByText(/Couldn’t load this/i)).toBeInTheDocument();
  });
});

describe('RecoveryCard - status extraction precedence', () => {
  it('reads status from the top-level `status` field (axios-style)', () => {
    renderCard({ error: { status: 401 } });
    expect(screen.getByText(/Your session has expired/i)).toBeInTheDocument();
  });

  it('reads status from `error.response.status` (raw axios error)', () => {
    renderCard({ error: { response: { status: 403 } } });
    expect(screen.getByText(/don’t have access here/i)).toBeInTheDocument();
  });

  it('prefers a top-level status over response.status when both are set', () => {
    // The component checks `e.status` first, so the top-level 401 wins
    // over the nested 403 — exercises the precedence branch in
    // extractStatus().
    renderCard({ error: { status: 401, response: { status: 403 } } });
    expect(screen.getByText(/Your session has expired/i)).toBeInTheDocument();
    expect(screen.queryByText(/don’t have access here/i)).toBeNull();
  });

  it('treats non-numeric status as missing (falls through to generic branch)', () => {
    renderCard({ error: { status: '401' as unknown as number }, onRetry: vi.fn() });
    // Generic branch — not the 401 sign-out screen.
    expect(screen.getByText(/Couldn’t load this/i)).toBeInTheDocument();
    expect(screen.queryByText(/Your session has expired/i)).toBeNull();
  });
});

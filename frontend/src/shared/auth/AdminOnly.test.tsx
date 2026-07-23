// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for <AdminOnly> — route gate hiding dev-only surfaces from
// non-admin users. Confirms:
//   * Renders children when userRole === 'admin'.
//   * Redirects to /404 (default) when userRole !== 'admin'.
//   * Honours an explicit redirectTo override.
//   * Does NOT throw when userRole is null (auth still loading) —
//     simply treats null as "not admin" and redirects.

import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

import { AdminOnly } from './AdminOnly';
import { useAuthStore } from '@/stores/useAuthStore';

function renderWithRoutes(
  redirectTo?: string,
  initialEntries: string[] = ['/dev/styles'],
) {
  return render(
    <MemoryRouter
      initialEntries={initialEntries}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Routes>
        <Route
          path="/dev/styles"
          element={
            <AdminOnly redirectTo={redirectTo}>
              <div data-testid="dev-content">Dev-only content</div>
            </AdminOnly>
          }
        />
        <Route path="/404" element={<div data-testid="not-found">404 here</div>} />
        <Route
          path="/forbidden"
          element={<div data-testid="forbidden">Custom redirect</div>}
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe('AdminOnly', () => {
  beforeEach(() => {
    act(() => {
      useAuthStore.setState({
        accessToken: null,
        isAuthenticated: false,
        userEmail: null,
        userRole: null,
      });
    });
  });

  it('renders children for users with userRole === "admin"', () => {
    act(() => {
      useAuthStore.setState({ userRole: 'admin', isAuthenticated: true });
    });
    renderWithRoutes();
    expect(screen.getByTestId('dev-content')).toBeInTheDocument();
    expect(screen.queryByTestId('not-found')).toBeNull();
  });

  it('redirects to /404 by default for non-admin users', () => {
    act(() => {
      useAuthStore.setState({ userRole: 'estimator', isAuthenticated: true });
    });
    renderWithRoutes();
    expect(screen.queryByTestId('dev-content')).toBeNull();
    expect(screen.getByTestId('not-found')).toBeInTheDocument();
  });

  it('redirects to the provided redirectTo path when supplied', () => {
    act(() => {
      useAuthStore.setState({ userRole: 'estimator', isAuthenticated: true });
    });
    renderWithRoutes('/forbidden');
    expect(screen.getByTestId('forbidden')).toBeInTheDocument();
    expect(screen.queryByTestId('dev-content')).toBeNull();
  });

  it('treats userRole === null (loading / signed out) as not-admin and redirects', () => {
    // Auth store starts with userRole=null in beforeEach.
    renderWithRoutes();
    expect(screen.queryByTestId('dev-content')).toBeNull();
    expect(screen.getByTestId('not-found')).toBeInTheDocument();
  });

  it('treats unknown role strings as not-admin (no partial match)', () => {
    act(() => {
      useAuthStore.setState({ userRole: 'superadmin', isAuthenticated: true });
    });
    renderWithRoutes();
    // 'superadmin' !== 'admin' under the strict-equality check, even
    // though the substring matches — exclusion is the safer default.
    expect(screen.queryByTestId('dev-content')).toBeNull();
    expect(screen.getByTestId('not-found')).toBeInTheDocument();
  });
});

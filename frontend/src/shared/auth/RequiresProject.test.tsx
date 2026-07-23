// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for <RequiresProject> — project-gating wrapper used by ~30 module
// pages. Confirms:
//   * Children render when a project is selected via the global store.
//   * Empty state renders with default copy + "Open Projects" CTA when no
//     project is selected, AND when the projectId resolves to an empty
//     string (treated as "no project").
//   * `emptyHint` / `emptyTitle` props override default copy.
//   * Wrapper re-renders when the store's `activeProjectId` flips on/off.
//   * The default `useParams()` mock from setup returns `{}`, so the
//     resolution chain falls back to `activeProjectId` from the store.
//
// react-router-dom and react-i18next are stubbed globally in
// frontend/src/test/setup.ts. We rely on the project context store
// directly so we don't have to spin up a MemoryRouter with a
// :projectId param.

import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';

import { RequiresProject } from './RequiresProject';
import { useProjectContextStore } from '@/stores/useProjectContextStore';

function renderGate(props: { emptyHint?: string; emptyTitle?: string } = {}) {
  return render(
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <RequiresProject {...props}>
        <div data-testid="protected-content">Protected content</div>
      </RequiresProject>
    </BrowserRouter>,
  );
}

describe('RequiresProject', () => {
  beforeEach(() => {
    // Reset the project context to "no project selected" before each
    // test. The store persists to localStorage which is mocked but
    // shared across tests in the same module, so we clear it explicitly.
    act(() => {
      useProjectContextStore.setState({
        activeProjectId: null,
        activeProjectName: '',
        activeBOQId: null,
      });
    });
    localStorage.clear();
  });

  it('renders children when activeProjectId is set in the store', () => {
    act(() => {
      useProjectContextStore.setState({
        activeProjectId: 'proj-123',
        activeProjectName: 'Sample project',
      });
    });
    renderGate();
    expect(screen.getByTestId('protected-content')).toBeInTheDocument();
    expect(screen.queryByText(/No project selected/i)).toBeNull();
  });

  it('renders the EmptyState with default title + description when no project is set', () => {
    renderGate();
    expect(screen.queryByTestId('protected-content')).toBeNull();
    expect(screen.getByText(/No project selected/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Pick a project from the header to continue/i),
    ).toBeInTheDocument();
  });

  it('renders the "Open Projects" CTA pointing at /projects', () => {
    renderGate();
    const link = screen.getByRole('link', { name: /Open Projects/i });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute('href', '/projects');
  });

  it('respects a custom emptyHint description', () => {
    renderGate({ emptyHint: 'Pick a project before raising an RFI.' });
    expect(
      screen.getByText('Pick a project before raising an RFI.'),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/Pick a project from the header to continue/i),
    ).toBeNull();
  });

  it('respects a custom emptyTitle override', () => {
    renderGate({ emptyTitle: 'Project required for RFIs' });
    expect(screen.getByText('Project required for RFIs')).toBeInTheDocument();
    expect(screen.queryByText(/No project selected/i)).toBeNull();
  });

  it('treats empty string activeProjectId as "no project" and shows the gate', () => {
    act(() => {
      useProjectContextStore.setState({ activeProjectId: '', activeProjectName: '' });
    });
    renderGate();
    expect(screen.queryByTestId('protected-content')).toBeNull();
    expect(screen.getByText(/No project selected/i)).toBeInTheDocument();
  });

  it('re-renders to show children when activeProjectId flips from null to a value', () => {
    renderGate();
    // Initially: no project → gate visible.
    expect(screen.getByText(/No project selected/i)).toBeInTheDocument();
    expect(screen.queryByTestId('protected-content')).toBeNull();

    // Flip the store; the wrapper subscribes to it and should re-render.
    act(() => {
      useProjectContextStore.setState({
        activeProjectId: 'proj-999',
        activeProjectName: 'Now selected',
      });
    });

    expect(screen.getByTestId('protected-content')).toBeInTheDocument();
    expect(screen.queryByText(/No project selected/i)).toBeNull();
  });

  it('re-renders to show the gate when activeProjectId is cleared', () => {
    act(() => {
      useProjectContextStore.setState({
        activeProjectId: 'proj-abc',
        activeProjectName: 'Will be cleared',
      });
    });
    renderGate();
    expect(screen.getByTestId('protected-content')).toBeInTheDocument();

    act(() => {
      useProjectContextStore.setState({ activeProjectId: null, activeProjectName: '' });
    });

    expect(screen.queryByTestId('protected-content')).toBeNull();
    expect(screen.getByText(/No project selected/i)).toBeInTheDocument();
  });
});

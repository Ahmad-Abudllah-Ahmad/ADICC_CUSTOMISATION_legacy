// @ts-nocheck
/**
 * Unit tests for the FolderPermissionsModal component.
 *
 * Covers the three scenarios from the spec:
 *   1. zero grants → empty state "All members can access this folder"
 *   2. two grants → both rows render with role badges
 *   3. clicking "Grant access" opens the picker → picker fills the
 *      select with project members, "Grant access" button calls the API.
 *
 * Mocks the api module directly (instead of using MSW) because the
 * shared MSW node setup is brittle in this worktree — the project's
 * existing share-link.test.tsx hits the same issue. Direct module
 * mocks make the test deterministic without depending on the
 * intercept layer.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, waitFor, fireEvent, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

import { FolderPermissionsModal } from './components/FolderPermissionsModal';
import type { FolderPermissionRow } from './types';
import * as api from './api';
import { apiGet } from '@/shared/lib/api';

const PROJECT_ID = 'proj-001';

const ALICE: FolderPermissionRow = {
  id: 'grant-001',
  project_id: PROJECT_ID,
  user_id: 'user-alice',
  scope_kind: 'document',
  scope_path: null,
  role: 'viewer',
  granted_by: 'user-owner',
  granted_at: '2026-05-12T00:00:00Z',
  revoked: false,
  created_at: '2026-05-12T00:00:00Z',
  updated_at: '2026-05-12T00:00:00Z',
  user_email: 'alice@example.com',
  user_full_name: 'Alice Engineer',
};

const BOB: FolderPermissionRow = {
  id: 'grant-002',
  project_id: PROJECT_ID,
  user_id: 'user-bob',
  scope_kind: 'document',
  scope_path: null,
  role: 'editor',
  granted_by: 'user-owner',
  granted_at: '2026-05-12T01:00:00Z',
  revoked: false,
  created_at: '2026-05-12T01:00:00Z',
  updated_at: '2026-05-12T01:00:00Z',
  user_email: 'bob@example.com',
  user_full_name: 'Bob Manager',
};

const MOCK_MEMBERS = [
  {
    user_id: 'user-owner',
    email: 'owner@example.com',
    full_name: 'Project Owner',
    is_owner: true,
  },
  {
    user_id: 'user-alice',
    email: 'alice@example.com',
    full_name: 'Alice Engineer',
    is_owner: false,
  },
  {
    user_id: 'user-bob',
    email: 'bob@example.com',
    full_name: 'Bob Manager',
    is_owner: false,
  },
  {
    user_id: 'user-carol',
    email: 'carol@example.com',
    full_name: 'Carol Estimator',
    is_owner: false,
  },
];

// Mock the file-manager api module so the modal's listFolderPermissions /
// grantFolderPermission / revokeFolderPermission calls resolve from
// in-test state without hitting MSW.
vi.mock('./api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api')>();
  return {
    ...actual,
    listFolderPermissions: vi.fn(),
    grantFolderPermission: vi.fn(),
    revokeFolderPermission: vi.fn(),
  };
});

// Mock the shared apiGet so the members fetch resolves from in-test state.
vi.mock('@/shared/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/shared/lib/api')>();
  return {
    ...actual,
    apiGet: vi.fn(),
  };
});

beforeEach(() => {
  (api.listFolderPermissions as ReturnType<typeof vi.fn>).mockResolvedValue([]);
  (api.grantFolderPermission as ReturnType<typeof vi.fn>).mockImplementation(
    async (_projectId, payload) => ({
      ...ALICE,
      id: 'grant-new',
      user_id: payload.user_id,
      role: payload.role,
    }),
  );
  (api.revokeFolderPermission as ReturnType<typeof vi.fn>).mockResolvedValue(
    undefined,
  );
  (apiGet as ReturnType<typeof vi.fn>).mockResolvedValue(MOCK_MEMBERS);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderModal(open = true) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <FolderPermissionsModal
        open={open}
        projectId={PROJECT_ID}
        scopeKind="document"
        scopePath={null}
        folderLabel="Documents"
        onClose={() => {}}
      />
    </QueryClientProvider>,
  );
}

describe('FolderPermissionsModal', () => {
  it('renders nothing when closed', () => {
    const { container } = renderModal(false);
    expect(container.innerHTML).toBe('');
  });

  it('shows the "all members" empty state when no grants exist', async () => {
    (api.listFolderPermissions as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    renderModal();
    await waitFor(() => {
      expect(
        screen.getByTestId('folder-permissions-empty'),
      ).toBeInTheDocument();
    });
    expect(
      screen.getByText(/all project members can access/i),
    ).toBeInTheDocument();
  });

  it('renders rows for each existing grant with the role badge', async () => {
    (api.listFolderPermissions as ReturnType<typeof vi.fn>).mockResolvedValue([
      ALICE,
      BOB,
    ]);
    renderModal();
    await waitFor(() => {
      expect(
        screen.getByTestId(`folder-permission-row-${ALICE.id}`),
      ).toBeInTheDocument();
    });
    expect(
      screen.getByTestId(`folder-permission-row-${BOB.id}`),
    ).toBeInTheDocument();
    expect(screen.getByText('Alice Engineer')).toBeInTheDocument();
    expect(screen.getByText('Bob Manager')).toBeInTheDocument();
    // Role badges are rendered as the role string (lowercase) inside
    // an uppercase-tracked span.
    const badges = screen.getAllByText(/viewer|editor/i);
    expect(badges.length).toBeGreaterThanOrEqual(2);
  });

  it('opens the picker, lists project members minus already-granted, and grants on click', async () => {
    (api.listFolderPermissions as ReturnType<typeof vi.fn>).mockResolvedValue([
      ALICE,
    ]);
    renderModal();

    await waitFor(() => {
      expect(
        screen.getByTestId('folder-permissions-user-picker'),
      ).toBeInTheDocument();
    });

    const picker = screen.getByTestId(
      'folder-permissions-user-picker',
    ) as HTMLSelectElement;
    // Wait for members + grants to load.
    await waitFor(() => {
      const opts = Array.from(picker.options).map((o) => o.value);
      expect(opts).toContain('user-bob');
      expect(opts).toContain('user-carol');
      // Alice excluded because she already has a grant.
      expect(opts).not.toContain('user-alice');
      // Owner excluded.
      expect(opts).not.toContain('user-owner');
    });

    fireEvent.change(picker, { target: { value: 'user-bob' } });
    const grantButton = screen.getByTestId('folder-permissions-grant-button');
    fireEvent.click(grantButton);

    await waitFor(() => {
      expect(api.grantFolderPermission).toHaveBeenCalledWith(
        PROJECT_ID,
        expect.objectContaining({
          user_id: 'user-bob',
          scope_kind: 'document',
          role: 'viewer',
        }),
      );
    });
  });
});

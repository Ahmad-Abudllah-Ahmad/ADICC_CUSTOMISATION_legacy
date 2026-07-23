// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/** Tests for the NamingViolationBanner component. */

import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { NamingViolationBanner } from '../NamingViolationBanner';
import type { NamingViolationListResponse } from '../types';

vi.mock('../api', async () => {
  const actual =
    await vi.importActual<typeof import('../api')>('../api');
  return {
    ...actual,
    listViolations: vi.fn(),
    acknowledgeViolation: vi.fn(),
  };
});

import { acknowledgeViolation, listViolations } from '../api';

function renderWithClient(ui: React.ReactNode): void {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

afterEach(() => {
  vi.resetAllMocks();
});

describe('NamingViolationBanner', () => {
  it('renders nothing when the file has no open violation', async () => {
    vi.mocked(listViolations).mockResolvedValue({
      items: [],
      total: 0,
      limit: 500,
      offset: 0,
    } satisfies NamingViolationListResponse);

    renderWithClient(
      <NamingViolationBanner
        projectId="p-1"
        fileKind="document"
        fileId="f-1"
      />,
    );

    await waitFor(() => {
      expect(listViolations).toHaveBeenCalled();
    });
    // No banner rendered.
    expect(
      screen.queryByTestId('naming-violation-banner'),
    ).not.toBeInTheDocument();
  });

  it('renders the violation codes for a matching file', async () => {
    vi.mocked(listViolations).mockResolvedValue({
      items: [
        {
          id: 'v-1',
          project_id: 'p-1',
          rule_set: 'iso19650',
          file_kind: 'document',
          file_id: 'f-1',
          filename: 'bad.pdf',
          violation_codes: ['not-iso19650', 'missing-volume'],
          summary: 'not-iso19650',
          acknowledged_at: null,
          acknowledged_by_id: null,
          created_at: '2026-05-19T08:00:00Z',
          updated_at: '2026-05-19T08:00:00Z',
        },
      ],
      total: 1,
      limit: 500,
      offset: 0,
    });

    renderWithClient(
      <NamingViolationBanner
        projectId="p-1"
        fileKind="document"
        fileId="f-1"
      />,
    );

    await waitFor(() => {
      expect(
        screen.getByTestId('naming-violation-banner'),
      ).toBeInTheDocument();
    });
    expect(
      screen.getByTestId('violation-code-not-iso19650'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('violation-code-missing-volume'),
    ).toBeInTheDocument();
  });

  it('expands the rule detail panel when Show rule is clicked', async () => {
    vi.mocked(listViolations).mockResolvedValue({
      items: [
        {
          id: 'v-1',
          project_id: 'p-1',
          rule_set: 'iso19650',
          file_kind: 'document',
          file_id: 'f-1',
          filename: 'bad.pdf',
          violation_codes: ['bad-role-code'],
          summary: 'bad-role-code',
          acknowledged_at: null,
          acknowledged_by_id: null,
          created_at: '2026-05-19T08:00:00Z',
          updated_at: '2026-05-19T08:00:00Z',
        },
      ],
      total: 1,
      limit: 500,
      offset: 0,
    });

    renderWithClient(
      <NamingViolationBanner
        projectId="p-1"
        fileKind="document"
        fileId="f-1"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('violation-toggle-rule')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId('violation-toggle-rule'));
    // Mock returns defaultValue verbatim — no ``{{rs}}`` interpolation.
    expect(screen.getByText(/Rule set:/)).toBeInTheDocument();
    expect(screen.getByText(/Role \(discipline\)/)).toBeInTheDocument();
  });

  it('calls acknowledge when the user clicks the Acknowledge button', async () => {
    vi.mocked(listViolations).mockResolvedValue({
      items: [
        {
          id: 'v-77',
          project_id: 'p-1',
          rule_set: 'iso19650',
          file_kind: 'document',
          file_id: 'f-1',
          filename: 'bad.pdf',
          violation_codes: ['not-iso19650'],
          summary: 'not-iso19650',
          acknowledged_at: null,
          acknowledged_by_id: null,
          created_at: '2026-05-19T08:00:00Z',
          updated_at: '2026-05-19T08:00:00Z',
        },
      ],
      total: 1,
      limit: 500,
      offset: 0,
    });
    vi.mocked(acknowledgeViolation).mockResolvedValue({
      id: 'v-77',
      project_id: 'p-1',
      rule_set: 'iso19650',
      file_kind: 'document',
      file_id: 'f-1',
      filename: 'bad.pdf',
      violation_codes: ['not-iso19650'],
      summary: 'not-iso19650',
      acknowledged_at: '2026-05-19T09:00:00Z',
      acknowledged_by_id: 'u-1',
      created_at: '2026-05-19T08:00:00Z',
      updated_at: '2026-05-19T09:00:00Z',
    });

    renderWithClient(
      <NamingViolationBanner
        projectId="p-1"
        fileKind="document"
        fileId="f-1"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('violation-acknowledge')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId('violation-acknowledge'));
    await waitFor(() => {
      expect(acknowledgeViolation).toHaveBeenCalledWith('v-77');
    });
  });
});

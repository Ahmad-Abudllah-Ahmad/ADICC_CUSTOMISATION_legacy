// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * ClashRunDiffBadge UI tests.
 *
 * The badge fetches ``GET /v1/clash/runs/{id}/diff`` via
 * ``clashApi.runDiff``; we mock that one method so the tests are fully
 * offline. React Query retries are disabled so error states surface
 * synchronously (matches the ClashCostImpactColumn test convention).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  render,
  screen,
  waitFor,
  cleanup,
  act,
} from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// ── clashApi.runDiff stub ───────────────────────────────────────────────────
// Mock the feature api module but keep every other export intact so the
// component's other imports (types) resolve normally.
vi.mock('../api', async () => {
  const actual = await vi.importActual<typeof import('../api')>('../api');
  return {
    ...actual,
    clashApi: {
      ...actual.clashApi,
      runDiff: vi.fn(),
    },
  };
});

import { clashApi } from '../api';
import { ClashRunDiffBadge } from '../ClashRunDiffBadge';

const runDiffMock = clashApi.runDiff as unknown as ReturnType<typeof vi.fn>;

function renderBadge(
  props: Partial<React.ComponentProps<typeof ClashRunDiffBadge>> = {},
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <ClashRunDiffBadge projectId="p-1" runId="r-1" {...props} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  cleanup();
});

describe('ClashRunDiffBadge', () => {
  it('calls runDiff with the project + run id', async () => {
    runDiffMock.mockResolvedValue({
      new: 2,
      persisted: 0,
      resolved: 0,
      reopened: 0,
      ignored: 0,
    });
    renderBadge({ projectId: 'proj-X', runId: 'run-Y' });
    await waitFor(() => expect(runDiffMock).toHaveBeenCalled());
    expect(runDiffMock).toHaveBeenCalledWith('proj-X', 'run-Y');
  });

  it('renders only the non-zero lifecycle buckets with counts', async () => {
    runDiffMock.mockResolvedValue({
      new: 3,
      persisted: 5,
      resolved: 0,
      reopened: 1,
      ignored: 0,
    });
    renderBadge();
    await screen.findByTestId('clash-run-diff-badge');
    // New / persisting / reopened render; resolved / suppressed do not.
    expect(screen.getByTestId('clash-run-diff-new').textContent).toContain('3');
    expect(
      screen.getByTestId('clash-run-diff-persisted').textContent,
    ).toContain('5');
    expect(
      screen.getByTestId('clash-run-diff-reopened').textContent,
    ).toContain('1');
    expect(screen.queryByTestId('clash-run-diff-resolved')).toBeNull();
    expect(screen.queryByTestId('clash-run-diff-ignored')).toBeNull();
  });

  it('self-hides on a first run (all-zero diff)', async () => {
    runDiffMock.mockResolvedValue({
      new: 0,
      persisted: 0,
      resolved: 0,
      reopened: 0,
      ignored: 0,
    });
    renderBadge();
    // Let the query resolve, then assert nothing rendered.
    await waitFor(() => expect(runDiffMock).toHaveBeenCalled());
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.queryByTestId('clash-run-diff-badge')).toBeNull();
  });

  it('fails soft on an API error (renders nothing, no crash)', async () => {
    runDiffMock.mockRejectedValue(new Error('boom'));
    renderBadge();
    await waitFor(() => expect(runDiffMock).toHaveBeenCalled());
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.queryByTestId('clash-run-diff-badge')).toBeNull();
  });

  it('coerces a malformed payload (negatives / non-numbers) safely', async () => {
    // A negative or non-numeric field must never render NaN; the bucket is
    // clamped to >= 0 (and a 0 bucket then hides).
    runDiffMock.mockResolvedValue({
      new: -4,
      persisted: 'oops',
      resolved: 2.9,
      reopened: 0,
      ignored: 0,
    } as never);
    renderBadge();
    await screen.findByTestId('clash-run-diff-badge');
    // -4 -> 0 (hidden); 'oops' -> 0 (hidden); 2.9 -> 2 (truncated, shown).
    expect(screen.queryByTestId('clash-run-diff-new')).toBeNull();
    expect(screen.queryByTestId('clash-run-diff-persisted')).toBeNull();
    const resolved = screen.getByTestId('clash-run-diff-resolved');
    expect(resolved.textContent).toContain('2');
    expect(resolved.textContent).not.toContain('NaN');
  });

  it('does not call the API without a runId', async () => {
    runDiffMock.mockResolvedValue({
      new: 1,
      persisted: 0,
      resolved: 0,
      reopened: 0,
      ignored: 0,
    });
    renderBadge({ runId: '' });
    await act(async () => {
      await Promise.resolve();
    });
    expect(runDiffMock).not.toHaveBeenCalled();
  });
});

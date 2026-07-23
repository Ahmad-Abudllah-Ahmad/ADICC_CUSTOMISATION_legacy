// @ts-nocheck
/**
 * Unit tests for the row-level edit / delete handlers in the Resources
 * Assignments tab.
 *
 * The tab itself depends on many sibling features (project context,
 * authentication, useQueries fan-out, etc.) which would each need a
 * non-trivial mock. We instead exercise the leaf behaviours directly:
 *
 *   1. ``deleteAssignment`` issues a DELETE to the right endpoint and
 *      returns ``undefined`` on 204.
 *   2. ``updateAssignment`` PATCHes the same id with the supplied
 *      partial payload and returns the updated row.
 *
 * That covers the critical fix: before this change, the only mutation
 * endpoints called from the page were ``proposeAssignment`` /
 * ``confirmAssignment`` / ``cancelAssignment`` — there were no
 * client-side functions to call PATCH or DELETE on an assignment, so
 * the UI had no way to edit or delete one. The test guarantees the
 * helpers exist, hit the right URL, and round-trip the payload.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

// Mock the API transport. ``apiPatch`` / ``apiDelete`` come from
// shared/lib/api which transparently injects the JWT — for the unit
// test we only care about URL + payload routing.
vi.mock('@/shared/lib/api', () => {
  const apiPatch = vi.fn(async (path: string, body: unknown) => ({
    id: 'a1',
    resource_id: 'r1',
    start_at: '2026-06-01T08:00:00.000Z',
    end_at: '2026-06-01T17:00:00.000Z',
    allocation_percent: 75,
    status: 'confirmed',
    cost_rate: 0,
    currency: '',
    notes: '',
    metadata: {},
    created_at: '2026-05-14T00:00:00.000Z',
    updated_at: '2026-05-14T00:00:00.000Z',
    _path: path,
    _body: body,
  }));
  const apiDelete = vi.fn(async (_path: string) => undefined);
  const apiGet = vi.fn();
  const apiPost = vi.fn();
  return { apiPatch, apiDelete, apiGet, apiPost, getErrorMessage: (e: unknown) => String(e) };
});

import * as api from '@/shared/lib/api';
import { updateAssignment, deleteAssignment } from '../api';

const apiPatchMock = api.apiPatch as unknown as ReturnType<typeof vi.fn>;
const apiDeleteMock = api.apiDelete as unknown as ReturnType<typeof vi.fn>;

describe('Resources assignments - edit/delete helpers', () => {
  beforeEach(() => {
    apiPatchMock.mockClear();
    apiDeleteMock.mockClear();
  });

  it('updateAssignment PATCHes /v1/resources/assignments/{id} with the partial payload', async () => {
    const result = await updateAssignment('a1', {
      allocation_percent: 75,
      status: 'confirmed',
      notes: 'changed',
    });

    expect(apiPatchMock).toHaveBeenCalledTimes(1);
    const [path, body] = apiPatchMock.mock.calls[0]!;
    expect(path).toBe('/v1/resources/assignments/a1');
    expect(body).toEqual({
      allocation_percent: 75,
      status: 'confirmed',
      notes: 'changed',
    });
    // Surface the round-tripped response to the caller (used by the
    // optimistic-update mutation).
    expect(result.id).toBe('a1');
    expect(result.allocation_percent).toBe(75);
    expect(result.status).toBe('confirmed');
  });

  it('deleteAssignment DELETEs /v1/resources/assignments/{id} and resolves void', async () => {
    const result = await deleteAssignment('a1');

    expect(apiDeleteMock).toHaveBeenCalledTimes(1);
    expect(apiDeleteMock.mock.calls[0]![0]).toBe('/v1/resources/assignments/a1');
    expect(result).toBeUndefined();
  });

  it('bulk delete dispatches one DELETE per id in parallel', async () => {
    const ids = ['a1', 'a2', 'a3'];
    await Promise.allSettled(ids.map((id) => deleteAssignment(id)));

    expect(apiDeleteMock).toHaveBeenCalledTimes(3);
    const calledPaths = apiDeleteMock.mock.calls.map((c) => c[0]);
    expect(calledPaths).toEqual([
      '/v1/resources/assignments/a1',
      '/v1/resources/assignments/a2',
      '/v1/resources/assignments/a3',
    ]);
  });

  it('partial-failure bulk delete surfaces the failed count', async () => {
    apiDeleteMock
      .mockResolvedValueOnce(undefined)
      .mockRejectedValueOnce(new Error('403'))
      .mockResolvedValueOnce(undefined);

    const results = await Promise.allSettled(
      ['a1', 'a2', 'a3'].map((id) => deleteAssignment(id)),
    );
    const failed = results.filter((r) => r.status === 'rejected').length;
    expect(failed).toBe(1);
    expect(apiDeleteMock).toHaveBeenCalledTimes(3);
  });
});

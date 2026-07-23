// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/** Tests for the file-comments CommentThread component. */

import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  render,
  screen,
  within,
  waitFor,
} from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { CommentThread } from '../CommentThread';
import type {
  FileCommentListResponse,
  FileCommentThread as ThreadNode,
} from '../types';

vi.mock('../api', async () => {
  const actual =
    await vi.importActual<typeof import('../api')>('../api');
  return {
    ...actual,
    listThreads: vi.fn(),
    updateComment: vi.fn(),
    deleteComment: vi.fn(),
    createComment: vi.fn(),
  };
});

import { listThreads } from '../api';

function makeNode(overrides: Partial<ThreadNode> = {}): ThreadNode {
  return {
    id: overrides.id ?? 'c-1',
    project_id: 'p-1',
    file_kind: 'document',
    file_id: 'f-1',
    file_version_id: null,
    file_version_snapshot: null,
    parent_id: null,
    author_id: overrides.author_id ?? '00000000-0000-0000-0000-000000000001',
    author_name:
      overrides.author_name !== undefined ? overrides.author_name : 'Alice Smith',
    body: overrides.body ?? 'Top-level note.',
    page_number: null,
    anchor_x: null,
    anchor_y: null,
    resolved: overrides.resolved ?? false,
    resolved_at: null,
    resolved_by_id: null,
    created_at: '2026-05-19T08:00:00Z',
    updated_at: '2026-05-19T08:00:00Z',
    mentions: [],
    replies: overrides.replies ?? [],
  };
}

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

describe('CommentThread', () => {
  it('renders the heading with the thread count and the empty state when there are no threads', async () => {
    vi.mocked(listThreads).mockResolvedValue({
      file_kind: 'document',
      file_id: 'f-1',
      threads: [],
      total: 0,
    } satisfies FileCommentListResponse);

    renderWithClient(
      <CommentThread
        projectId="p-1"
        fileKind="document"
        fileId="f-1"
        currentUserId="00000000-0000-0000-0000-000000000001"
        canResolve
      />,
    );

    await waitFor(() => {
      // The i18n test mock returns defaultValue verbatim, so the
      // ``{{count}}`` placeholder is not interpolated; we just verify
      // the heading text root is present.
      expect(screen.getByText(/Comments/)).toBeInTheDocument();
    });
    // EmptyState appears for the zero-row response.
    expect(screen.getByText(/No comments yet/)).toBeInTheDocument();
  });

  it('renders nested replies and shows the Reply affordance for non-tombstoned nodes', async () => {
    const reply = makeNode({ id: 'c-2', parent_id: 'c-1', body: 'Reply body.' });
    const top = makeNode({ id: 'c-1', replies: [reply] });
    vi.mocked(listThreads).mockResolvedValue({
      file_kind: 'document',
      file_id: 'f-1',
      threads: [top],
      total: 1,
    });

    renderWithClient(
      <CommentThread
        projectId="p-1"
        fileKind="document"
        fileId="f-1"
        currentUserId="00000000-0000-0000-0000-000000000001"
        canResolve
      />,
    );

    await waitFor(() => {
      expect(screen.getByText('Top-level note.')).toBeInTheDocument();
    });
    expect(screen.getByText('Reply body.')).toBeInTheDocument();
    expect(screen.getByTestId('comment-reply-c-1')).toBeInTheDocument();
    expect(screen.getByTestId('comment-reply-c-2')).toBeInTheDocument();
    // Resolve only on top-level.
    expect(screen.getByTestId('comment-resolve-c-1')).toBeInTheDocument();
    expect(screen.queryByTestId('comment-resolve-c-2')).not.toBeInTheDocument();
  });

  it('highlights @mentions inside the rendered body', async () => {
    const top = makeNode({ id: 'c-1', body: 'Hey @alice please look.' });
    vi.mocked(listThreads).mockResolvedValue({
      file_kind: 'document',
      file_id: 'f-1',
      threads: [top],
      total: 1,
    });

    renderWithClient(
      <CommentThread
        projectId="p-1"
        fileKind="document"
        fileId="f-1"
        currentUserId="00000000-0000-0000-0000-000000000001"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('comment-node-c-1')).toBeInTheDocument();
    });
    const node = screen.getByTestId('comment-node-c-1');
    // The mention is wrapped in its own element with the highlight bg.
    const mention = within(node).getByText('@alice');
    expect(mention).toBeInTheDocument();
    expect(mention.tagName).toBe('SPAN');
  });

  it('renders the resolved author name instead of the raw id', async () => {
    const top = makeNode({
      id: 'c-1',
      author_id: '11112222-3333-4444-5555-666677778888',
      author_name: 'Alice Smith',
    });
    vi.mocked(listThreads).mockResolvedValue({
      file_kind: 'document',
      file_id: 'f-1',
      threads: [top],
      total: 1,
    });

    renderWithClient(
      <CommentThread
        projectId="p-1"
        fileKind="document"
        fileId="f-1"
        currentUserId={null}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('comment-node-c-1')).toBeInTheDocument();
    });
    const node = screen.getByTestId('comment-node-c-1');
    expect(within(node).getByText('Alice Smith')).toBeInTheDocument();
    // The 8-char id prefix must no longer appear in the byline.
    expect(within(node).queryByText(/^11112222$/)).not.toBeInTheDocument();
  });

  it('falls back to the short id when author_name is null (legacy payload)', async () => {
    const top = makeNode({
      id: 'c-1',
      author_id: '11112222-3333-4444-5555-666677778888',
      author_name: null,
    });
    vi.mocked(listThreads).mockResolvedValue({
      file_kind: 'document',
      file_id: 'f-1',
      threads: [top],
      total: 1,
    });

    renderWithClient(
      <CommentThread
        projectId="p-1"
        fileKind="document"
        fileId="f-1"
        currentUserId={null}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('comment-node-c-1')).toBeInTheDocument();
    });
    const node = screen.getByTestId('comment-node-c-1');
    expect(within(node).getByText('11112222')).toBeInTheDocument();
  });

  it('renders a tombstone for [deleted] bodies and hides the Reply affordance', async () => {
    const top = makeNode({ id: 'c-1', body: '[deleted]' });
    vi.mocked(listThreads).mockResolvedValue({
      file_kind: 'document',
      file_id: 'f-1',
      threads: [top],
      total: 1,
    });

    renderWithClient(
      <CommentThread
        projectId="p-1"
        fileKind="document"
        fileId="f-1"
        currentUserId="00000000-0000-0000-0000-000000000001"
        canResolve
      />,
    );

    await waitFor(() => {
      expect(screen.getByText(/Comment deleted/)).toBeInTheDocument();
    });
    expect(screen.queryByTestId('comment-reply-c-1')).not.toBeInTheDocument();
    expect(screen.queryByTestId('comment-resolve-c-1')).not.toBeInTheDocument();
  });
});

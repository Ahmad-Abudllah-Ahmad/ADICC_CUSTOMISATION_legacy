// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Tests for the reusable inline PDF preview modal (#246). The protected-blob
 * fetch is mocked so we assert the modal's open/close, render, and action
 * wiring without a real network round-trip.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { InlinePdfPreviewModal } from '../InlinePdfPreviewModal';
import {
  fetchProtectedObjectUrl,
  downloadProtectedFile,
} from '@/features/file-manager/api';

vi.mock('@/features/file-manager/api', () => ({
  fetchProtectedObjectUrl: vi.fn(),
  downloadProtectedFile: vi.fn(),
}));

const fetchMock = vi.mocked(fetchProtectedObjectUrl);
const downloadMock = vi.mocked(downloadProtectedFile);

describe('InlinePdfPreviewModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // jsdom lacks these by default; the component revokes blob URLs on cleanup.
    globalThis.URL.revokeObjectURL = vi.fn();
    fetchMock.mockResolvedValue('blob:fake-url');
    downloadMock.mockResolvedValue(undefined);
  });

  it('renders nothing when closed', () => {
    render(
      <InlinePdfPreviewModal
        open={false}
        downloadUrl="/api/v1/documents/1/download/"
        title="plan.pdf"
        onClose={() => {}}
      />,
    );
    expect(screen.queryByTestId('inline-pdf-preview')).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('renders nothing when there is no download URL', () => {
    render(
      <InlinePdfPreviewModal
        open
        downloadUrl={null}
        title="plan.pdf"
        onClose={() => {}}
      />,
    );
    expect(screen.queryByTestId('inline-pdf-preview')).not.toBeInTheDocument();
  });

  it('fetches the protected bytes and shows the PDF in an iframe', async () => {
    render(
      <InlinePdfPreviewModal
        open
        downloadUrl="/api/v1/documents/1/download/"
        title="plan.pdf"
        onClose={() => {}}
      />,
    );
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/documents/1/download/');
    expect(screen.getByText('plan.pdf')).toBeInTheDocument();
    const frame = await screen.findByTestId('inline-pdf-frame');
    expect(frame).toHaveAttribute('src', 'blob:fake-url');
  });

  it('calls onClose when the close button is clicked', () => {
    const onClose = vi.fn();
    render(
      <InlinePdfPreviewModal
        open
        downloadUrl="/api/v1/documents/1/download/"
        title="plan.pdf"
        onClose={onClose}
      />,
    );
    fireEvent.click(screen.getByTestId('inline-pdf-close'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('downloads through the protected helper', async () => {
    render(
      <InlinePdfPreviewModal
        open
        downloadUrl="/api/v1/documents/1/download/"
        title="plan.pdf"
        onClose={() => {}}
      />,
    );
    fireEvent.click(screen.getByTestId('inline-pdf-download'));
    await waitFor(() =>
      expect(downloadMock).toHaveBeenCalledWith(
        '/api/v1/documents/1/download/',
        'plan.pdf',
      ),
    );
  });

  it('shows a fallback when the fetch fails', async () => {
    fetchMock.mockResolvedValue(null);
    render(
      <InlinePdfPreviewModal
        open
        downloadUrl="/api/v1/documents/1/download/"
        title="plan.pdf"
        onClose={() => {}}
      />,
    );
    await waitFor(() =>
      expect(screen.queryByTestId('inline-pdf-frame')).not.toBeInTheDocument(),
    );
    // The error state still offers a download button.
    expect(screen.getByTestId('inline-pdf-download')).toBeInTheDocument();
  });
});

// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Unit tests for the MatchWizard "Photo / Drawing" source picker
// (ImageSourceSelector) and the createSessionFromImage API helper.
//
// The picker is self-validating: it accepts PNG/JPG/WebP up to 10 MB,
// shows a live preview thumbnail, supports a file-input fallback, and
// surfaces an inline error on rejection. These tests pin that contract
// plus the multipart shape the API helper posts to /sessions/from-image.

import { useState } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  render,
  screen,
  cleanup,
  fireEvent,
  waitFor,
  within,
} from '@testing-library/react';

// i18n: the component calls t(key, { defaultValue }). Return the default
// so assertions can match the English copy without a full i18n bundle.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_key: string, opts?: { defaultValue?: string } | string) =>
      typeof opts === 'object' && opts?.defaultValue ? opts.defaultValue : _key,
  }),
}));

// Auth store — the API helper reads the access token for the upload.
vi.mock('@/stores/useAuthStore', () => ({
  useAuthStore: {
    getState: () => ({ accessToken: 'test-token' }),
  },
}));

import ImageSourceSelector from '../ImageSourceSelector';
import { matchElementsApi } from '../api';

// jsdom lacks createObjectURL / revokeObjectURL — stub them so the
// preview effect doesn't throw.
beforeEach(() => {
  globalThis.URL.createObjectURL = vi.fn(() => 'blob:preview');
  globalThis.URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function makeFile(name: string, type: string, sizeBytes = 16): File {
  const blob = new Blob([new Uint8Array(sizeBytes)], { type });
  return new File([blob], name, { type });
}

/** Harness mirroring how MatchWizard drives the picker: it lifts the
 *  validated file into local state so we can assert the selection. */
function Harness() {
  const [file, setFile] = useState<File | null>(null);
  return (
    <div>
      <div data-testid="picked">{file ? file.name : 'none'}</div>
      <ImageSourceSelector file={file} onPick={setFile} />
    </div>
  );
}

describe('ImageSourceSelector', () => {
  it('renders the drop zone with a clear empty-state prompt', () => {
    render(<Harness />);
    expect(screen.getByText('Click or drop an image')).toBeInTheDocument();
    // The honest AI-suggestion note is always shown.
    expect(
      screen.getByText(/AI reads the image and suggests visible elements/i),
    ).toBeInTheDocument();
  });

  it('accepts a valid PNG and shows the preview + filename', async () => {
    render(<Harness />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = makeFile('site.png', 'image/png');

    fireEvent.change(input, { target: { files: [file] } });

    expect(screen.getByTestId('picked')).toHaveTextContent('site.png');
    await waitFor(() =>
      expect(screen.getByAltText('Preview of the uploaded image')).toBeInTheDocument(),
    );
    // The harness's bookkeeping div also echoes the name, so scope the
    // assertion to the picker's drop zone to confirm the preview surface
    // itself shows the filename.
    const dropZone = screen.getByLabelText('Image upload drop zone');
    expect(within(dropZone).getByText('site.png')).toBeInTheDocument();
  });

  it('rejects a non-image file with an inline error and no selection', () => {
    render(<Harness />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const bad = makeFile('notes.pdf', 'application/pdf');

    fireEvent.change(input, { target: { files: [bad] } });

    expect(screen.getByTestId('picked')).toHaveTextContent('none');
    expect(
      screen.getByText('Unsupported file. Use a PNG, JPG or WebP image.'),
    ).toBeInTheDocument();
  });

  it('rejects an oversized image (> 10 MB)', () => {
    render(<Harness />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const huge = makeFile('huge.jpg', 'image/jpeg', 10 * 1024 * 1024 + 1);

    fireEvent.change(input, { target: { files: [huge] } });

    expect(screen.getByTestId('picked')).toHaveTextContent('none');
    expect(
      screen.getByText('Image is larger than 10 MB. Downscale it and try again.'),
    ).toBeInTheDocument();
  });

  it('clears the selection on the Clear button', async () => {
    render(<Harness />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [makeFile('site.png', 'image/png')] },
    });
    expect(screen.getByTestId('picked')).toHaveTextContent('site.png');

    fireEvent.click(screen.getByText('Clear'));
    expect(screen.getByTestId('picked')).toHaveTextContent('none');
    await waitFor(() =>
      expect(screen.getByText('Click or drop an image')).toBeInTheDocument(),
    );
  });

  it('accepts a dropped image via the drag-drop handler', () => {
    render(<Harness />);
    const file = makeFile('dropped.webp', 'image/webp');
    const zone = screen.getByLabelText('Image upload drop zone');

    fireEvent.drop(zone, { dataTransfer: { files: [file] } });

    expect(screen.getByTestId('picked')).toHaveTextContent('dropped.webp');
  });
});

describe('createSessionFromImage', () => {
  it('posts multipart form-data with an "image" field to /sessions/from-image', async () => {
    let capturedUrl = '';
    let capturedBody: FormData | null = null;
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
        capturedUrl = String(input);
        capturedBody = init?.body as FormData;
        return new Response(JSON.stringify({ id: 'sess-1', source: 'image' }), {
          status: 201,
          headers: { 'Content-Type': 'application/json' },
        });
      });

    const file = makeFile('test.jpg', 'image/jpeg');
    const session = await matchElementsApi.createSessionFromImage({
      project_id: 'project-id',
      file,
      catalogue_id: 'de',
      construction_stage: '06_Superstructure',
    });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(capturedUrl).toContain('/sessions/from-image');
    expect(capturedBody).toBeInstanceOf(FormData);
    const fd = capturedBody as unknown as FormData;
    expect(fd.get('project_id')).toBe('project-id');
    expect(fd.get('image')).toBeInstanceOf(File);
    expect((fd.get('image') as File).name).toBe('test.jpg');
    expect(fd.get('catalogue_id')).toBe('de');
    expect(fd.get('construction_stage')).toBe('06_Superstructure');
    expect(session.id).toBe('sess-1');
  });

  it('throws a readable error when the upload is rejected', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Image is too large.' }), {
        status: 413,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    await expect(
      matchElementsApi.createSessionFromImage({
        project_id: 'p',
        file: makeFile('big.png', 'image/png'),
      }),
    ).rejects.toThrow(/413/);
  });
});

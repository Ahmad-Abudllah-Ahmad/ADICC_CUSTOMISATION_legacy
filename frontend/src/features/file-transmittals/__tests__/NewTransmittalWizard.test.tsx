// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests the 3-step New Transmittal wizard end-to-end:
//   1. Pre-selected items render in step 2.
//   2. Add recipient → step 3 advances enabled.
//   3. Finish triggers POST create + POST send and fires ``onSent`` with
//      the sent transmittal id.
//
// API layer is mocked so we exercise the wizard reducer + the
// orchestration of ``useCreateTransmittal`` + ``useSendTransmittal``
// without hitting a real backend.

import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import type { Transmittal } from '../types';

/* ── API layer mock ─────────────────────────────────────────────────── */

const draft: Transmittal = {
  id: 'tx-1',
  project_id: 'proj-1',
  number: 'T-0001',
  subject: 'Issue for review - package R1',
  reason_code: 'for_review',
  sender_id: 'user-1',
  sent_at: '2026-05-19T10:00:00Z',
  status: 'draft',
  notes: null,
  cover_sheet_path: null,
  items: [
    {
      id: 'i-1',
      transmittal_id: 'tx-1',
      file_kind: 'document',
      file_id: 'doc-1',
      file_version_snapshot: null,
      canonical_name_snapshot: 'Plans.pdf',
      sort_order: 0,
    },
  ],
  recipients: [],
  created_at: '2026-05-19T10:00:00Z',
  updated_at: '2026-05-19T10:00:00Z',
};

const sent: Transmittal = {
  ...draft,
  status: 'sent',
  cover_sheet_path: 'transmittals/proj-1/tx-1/cover.pdf',
};

const mocks = vi.hoisted(() => ({
  createTransmittalMock: vi.fn(),
  sendTransmittalMock: vi.fn(),
}));

const createTransmittalMock = mocks.createTransmittalMock;
const sendTransmittalMock = mocks.sendTransmittalMock;

vi.mock('../api', () => ({
  createTransmittal: mocks.createTransmittalMock,
  sendTransmittal: mocks.sendTransmittalMock,
  listTransmittals: vi.fn(async () => []),
  getTransmittal: vi.fn(),
  addTransmittalItem: vi.fn(),
  removeTransmittalItem: vi.fn(),
  addTransmittalRecipient: vi.fn(),
  acknowledgeTransmittal: vi.fn(),
  downloadTransmittalCover: vi.fn(),
}));

/* ── Toast spy ──────────────────────────────────────────────────────── */

const toastMocks = vi.hoisted(() => ({ addToastMock: vi.fn() }));
const addToastMock = toastMocks.addToastMock;
vi.mock('@/stores/useToastStore', () => ({
  useToastStore: Object.assign(
    (selector: (s: { addToast: typeof toastMocks.addToastMock }) => unknown) =>
      selector({ addToast: toastMocks.addToastMock }),
    { getState: () => ({ addToast: toastMocks.addToastMock }) },
  ),
}));

/* ── i18n shim ─────────────────────────────────────────────────────── */

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_key: string, opts?: { defaultValue?: string } & Record<string, unknown>) => {
      if (typeof opts === 'object' && opts && 'defaultValue' in opts) {
        let dv = opts.defaultValue ?? '';
        for (const [k, v] of Object.entries(opts)) {
          if (k === 'defaultValue') continue;
          dv = dv.replaceAll(`{{${k}}}`, String(v));
        }
        return dv;
      }
      return _key;
    },
    i18n: { language: 'en' },
  }),
  // ``src/app/i18n.ts`` is pulled in transitively and calls
  // ``.use(initReactI18next)`` at module load — expose the noop plugin.
  initReactI18next: { type: '3rdParty', init: () => {} },
}));

import { NewTransmittalWizard } from '../NewTransmittalWizard';

// Wire default return values now that the draft/sent literals are
// declared (the mocks themselves were hoisted above to satisfy
// vi.mock's top-of-file relocation semantics).
createTransmittalMock.mockImplementation(async () => draft);
sendTransmittalMock.mockImplementation(async () => sent);

afterEach(() => {
  cleanup();
  createTransmittalMock.mockClear();
  sendTransmittalMock.mockClear();
  createTransmittalMock.mockImplementation(async () => draft);
  sendTransmittalMock.mockImplementation(async () => sent);
  addToastMock.mockClear();
});

function renderWizard(preselected = [{
  file_kind: 'document' as const,
  file_id: 'doc-1',
  canonical_name_snapshot: 'Plans.pdf',
}]) {
  const onSent = vi.fn();
  const onClose = vi.fn();
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const utils = render(
    <QueryClientProvider client={client}>
      <NewTransmittalWizard
        open
        onClose={onClose}
        projectId="proj-1"
        preselectedItems={preselected}
        onSent={onSent}
      />
    </QueryClientProvider>,
  );
  return { ...utils, onSent, onClose };
}

describe('NewTransmittalWizard', () => {
  it('renders step 1 with subject + reason fields', () => {
    renderWizard();
    expect(
      screen.getByPlaceholderText(/Issue for review/i),
    ).toBeTruthy();
  });

  it('advances through 3 steps and creates + sends on finish', async () => {
    const { onSent } = renderWizard();

    // Step 1: enter subject.
    const subjectInput = screen.getByPlaceholderText(
      /Issue for review/i,
    ) as HTMLInputElement;
    fireEvent.change(subjectInput, { target: { value: 'My transmittal' } });

    // Next → step 2.
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));

    // Step 2: preselected file row visible.
    expect(screen.getByText('Plans.pdf')).toBeTruthy();

    // Next → step 3.
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));

    // Step 3: add a recipient.
    const emailInput = screen.getByPlaceholderText(
      'user@example.com',
    ) as HTMLInputElement;
    fireEvent.change(emailInput, {
      target: { value: 'alice@example.io' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));

    // Recipient row should appear (rendered twice — as display label
    // fallback AND as the email line — so allow ``getAllByText``).
    await waitFor(() => {
      const matches = screen.getAllByText('alice@example.io');
      expect(matches.length).toBeGreaterThan(0);
    });

    // Send.
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));

    await waitFor(() => expect(createTransmittalMock).toHaveBeenCalledTimes(1));
    expect(sendTransmittalMock).toHaveBeenCalledWith('tx-1');
    await waitFor(() => expect(onSent).toHaveBeenCalledWith('tx-1'));
    // Success toast is emitted.
    expect(addToastMock).toHaveBeenCalled();
    const lastCall = addToastMock.mock.calls.at(-1)?.[0];
    expect(lastCall?.type).toBe('success');
  });

  it('rejects invalid email and shows error toast', () => {
    renderWizard();
    // Skip to step 3 by clicking through with a valid subject.
    const subjectInput = screen.getByPlaceholderText(
      /Issue for review/i,
    ) as HTMLInputElement;
    fireEvent.change(subjectInput, { target: { value: 'test' } });
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));

    // Add invalid email.
    const emailInput = screen.getByPlaceholderText(
      'user@example.com',
    ) as HTMLInputElement;
    fireEvent.change(emailInput, { target: { value: 'not-an-email' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    expect(addToastMock).toHaveBeenCalled();
    const lastCall = addToastMock.mock.calls.at(-1)?.[0];
    expect(lastCall?.type).toBe('error');
  });
});

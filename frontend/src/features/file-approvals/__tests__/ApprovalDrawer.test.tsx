// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for the ApprovalDrawer component.
//
// Covers:
//   1. Renders all steps as a timeline with the correct decision badges.
//   2. Approve / Reject buttons appear ONLY for the actionable step
//      (first pending step) AND only when the current user is its approver.
//   3. Approve action calls ``useDecideApprovalStep``.

import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import type { ApprovalWorkflow } from '../types';

/* ── Auth store mock — drawer reads sub from accessToken JWT ───────── */

// JWT with payload {"sub":"user-approver-1"}.
// payload base64 = eyJzdWIiOiJ1c2VyLWFwcHJvdmVyLTEifQ
vi.mock('@/stores/useAuthStore', () => {
  const token = 'header.eyJzdWIiOiJ1c2VyLWFwcHJvdmVyLTEifQ.signature';
  return {
    useAuthStore: Object.assign(
      (selector: (s: { accessToken: string }) => unknown) =>
        selector({ accessToken: token }),
      { getState: () => ({ accessToken: token }) },
    ),
  };
});

/* ── Toast mock ────────────────────────────────────────────────────── */

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
    t: (
      _key: string,
      opts?: { defaultValue?: string } & Record<string, unknown>,
    ) => {
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

/* ── API mock ──────────────────────────────────────────────────────── */

const workflow: ApprovalWorkflow = {
  id: 'wf-1',
  project_id: 'proj-1',
  file_kind: 'document',
  file_id: 'doc-1',
  file_version_snapshot: null,
  submitted_by_id: 'user-submitter',
  submitted_at: '2026-05-19T10:00:00Z',
  status: 'in_review',
  final_decision_at: null,
  final_decision_by_id: null,
  stamp_template_id: null,
  stamped_artifact_path: null,
  notes: 'Please review the layout',
  steps: [
    {
      id: 'step-1',
      workflow_id: 'wf-1',
      sort_order: 0,
      approver_id: 'user-approver-1',
      role_label: 'Reviewer',
      decision: 'pending',
      decision_at: null,
      decision_note: null,
    },
    {
      id: 'step-2',
      workflow_id: 'wf-1',
      sort_order: 1,
      approver_id: 'user-approver-2',
      role_label: 'PM',
      decision: 'pending',
      decision_at: null,
      decision_note: null,
    },
  ],
  created_at: '2026-05-19T10:00:00Z',
  updated_at: '2026-05-19T10:00:00Z',
};

const apiMocks = vi.hoisted(() => ({
  getWorkflowMock: vi.fn(),
  decideStepMock: vi.fn(),
  withdrawMock: vi.fn(),
}));

const getWorkflowMock = apiMocks.getWorkflowMock;
const decideStepMock = apiMocks.decideStepMock;
const withdrawMock = apiMocks.withdrawMock;

vi.mock('../api', () => ({
  getWorkflow: apiMocks.getWorkflowMock,
  decideStep: apiMocks.decideStepMock,
  withdrawWorkflow: apiMocks.withdrawMock,
  listWorkflows: vi.fn(async () => []),
  submitForApproval: vi.fn(),
  listStampTemplates: vi.fn(async () => []),
  createStampTemplate: vi.fn(),
}));

import { ApprovalDrawer } from '../ApprovalDrawer';

function wireApiDefaults(): void {
  getWorkflowMock.mockImplementation(async () => workflow);
  decideStepMock.mockImplementation(async () => ({
    ...workflow,
    steps: [
      { ...(workflow.steps[0] as (typeof workflow.steps)[number]), decision: 'approved' as const },
      workflow.steps[1] as (typeof workflow.steps)[number],
    ],
  }));
  withdrawMock.mockImplementation(async () => workflow);
}

wireApiDefaults();

afterEach(() => {
  cleanup();
  getWorkflowMock.mockClear();
  decideStepMock.mockClear();
  withdrawMock.mockClear();
  addToastMock.mockClear();
  wireApiDefaults();
});

function renderDrawer() {
  const onClose = vi.fn();
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return {
    onClose,
    ...render(
      <QueryClientProvider client={client}>
        <ApprovalDrawer open workflowId="wf-1" onClose={onClose} />
      </QueryClientProvider>,
    ),
  };
}

describe('ApprovalDrawer', () => {
  it('renders the submitter notes and both steps', async () => {
    renderDrawer();
    await waitFor(() => expect(getWorkflowMock).toHaveBeenCalled());
    expect(await screen.findByText('Please review the layout')).toBeTruthy();
    expect(await screen.findByText('Reviewer')).toBeTruthy();
    expect(await screen.findByText('PM')).toBeTruthy();
  });

  it('shows "Record decision" only on the first pending step that belongs to me', async () => {
    renderDrawer();
    await waitFor(() => expect(getWorkflowMock).toHaveBeenCalled());

    // We are user-approver-1, so step-1 is actionable; step-2 is not.
    const decideButtons = await screen.findAllByRole('button', {
      name: 'Record decision',
    });
    expect(decideButtons).toHaveLength(1);
  });

  it('approves the actionable step when Approve is clicked', async () => {
    renderDrawer();
    await waitFor(() => expect(getWorkflowMock).toHaveBeenCalled());

    const decideButton = await screen.findByRole('button', {
      name: 'Record decision',
    });
    fireEvent.click(decideButton);

    const approveButton = await screen.findByRole('button', { name: 'Approve' });
    fireEvent.click(approveButton);

    await waitFor(() => expect(decideStepMock).toHaveBeenCalledTimes(1));
    const firstCall = decideStepMock.mock.calls[0] as unknown[];
    // signature: (workflowId, stepId, payload)
    expect(firstCall[0]).toBe('wf-1');
    expect(firstCall[1]).toBe('step-1');
    expect(firstCall[2]).toMatchObject({ decision: 'approved' });
  });
});

// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * RulePackPreviewModal unit tests.
 *
 * Mocks the api module so the debounce + preview-yaml round-trip is
 * deterministic; uses vi.useFakeTimers() to advance the 800 ms debounce.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  render,
  screen,
  fireEvent,
  cleanup,
  waitFor,
  act,
} from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/shared/lib/api', () => ({
  apiGet: vi.fn().mockResolvedValue({ items: [] }),
  apiPost: vi.fn(),
}));

vi.mock('../api', () => ({
  previewYaml: vi.fn(),
  installYaml: vi.fn(),
}));

const addToastMock = vi.fn();
vi.mock('@/stores/useToastStore', () => ({
  useToastStore: (sel?: (s: unknown) => unknown) => {
    const state = { addToast: addToastMock };
    return sel ? sel(state) : state;
  },
}));

import { RulePackPreviewModal } from '../RulePackPreviewModal';
import { SEED_PACKS } from '../SEED_PACKS';
import { previewYaml, installYaml } from '../api';
import { apiGet } from '@/shared/lib/api';

const previewMock = previewYaml as unknown as ReturnType<typeof vi.fn>;
const installMock = installYaml as unknown as ReturnType<typeof vi.fn>;
const apiGetMock = apiGet as unknown as ReturnType<typeof vi.fn>;

const SEED = SEED_PACKS[0]!; // DIN 276

/**
 * The backend dry-run report is a FLAT list of per-(rule, element) rows
 * ({ rule_id, element_id, passed }). Tests describe intent as per-rule
 * pass/fail tallies; this helper expands those tallies into the real
 * row shape so the mock matches production.
 */
function expandDryRunRows(
  tallies: Array<{ rule_id: string; pass_count: number; fail_count: number }>,
): Array<{ rule_id: string; element_id: string; passed: boolean }> {
  const rows: Array<{ rule_id: string; element_id: string; passed: boolean }> = [];
  let elementSeq = 0;
  for (const t of tallies) {
    for (let i = 0; i < t.pass_count; i += 1) {
      rows.push({ rule_id: t.rule_id, element_id: `el-${elementSeq++}`, passed: true });
    }
    for (let i = 0; i < t.fail_count; i += 1) {
      rows.push({ rule_id: t.rule_id, element_id: `el-${elementSeq++}`, passed: false });
    }
  }
  return rows;
}
const SUCCESS_RESPONSE = {
  pack: {
    rules: [
      {
        id: 'din276_code_present',
        name: 'DIN 276 cost-group code present on every element',
        severity: 'error' as const,
      },
      {
        id: 'din276_code_in_building_range',
        name: 'DIN 276 code must be in the 300/400/500 series',
        severity: 'warning' as const,
      },
    ],
  },
};

function renderModal(
  overrides: Partial<React.ComponentProps<typeof RulePackPreviewModal>> = {},
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <RulePackPreviewModal
        open
        onClose={overrides.onClose ?? vi.fn()}
        seedPack={overrides.seedPack === undefined ? SEED : overrides.seedPack}
        projectId={overrides.projectId === undefined ? 'project-1' : overrides.projectId}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  cleanup();
  apiGetMock.mockResolvedValue({ items: [] });
});

afterEach(() => {
  // Reset timers so other tests use real timers.
  vi.useRealTimers();
});

describe('RulePackPreviewModal', () => {
  it('opens with seed pack content preloaded into the editor', () => {
    previewMock.mockResolvedValue(SUCCESS_RESPONSE);
    renderModal();
    const ta = screen.getByTestId(
      'rule-pack-preview-modal-yaml-textarea',
    ) as HTMLTextAreaElement;
    expect(ta.value).toBe(SEED.yaml);
    // Default readonly in seed mode.
    expect(ta.readOnly).toBe(true);
  });

  it('starts empty in custom mode (no seedPack)', () => {
    previewMock.mockResolvedValue(SUCCESS_RESPONSE);
    renderModal({ seedPack: null });
    const ta = screen.getByTestId(
      'rule-pack-preview-modal-yaml-textarea',
    ) as HTMLTextAreaElement;
    expect(ta.value).toBe('');
    expect(ta.readOnly).toBe(false);
  });

  it('debounces preview calls and fires after 800 ms', async () => {
    vi.useFakeTimers();
    previewMock.mockResolvedValue(SUCCESS_RESPONSE);
    renderModal();
    // No preview before the debounce timer fires.
    expect(previewMock).not.toHaveBeenCalled();
    await act(async () => {
      vi.advanceTimersByTime(801);
    });
    expect(previewMock).toHaveBeenCalledTimes(1);
    expect(previewMock).toHaveBeenCalledWith({
      yaml_text: SEED.yaml,
      model_id: undefined,
    });
  });

  it('renders an inline preview error when the API rejects', async () => {
    previewMock.mockRejectedValue(new Error('parse boom'));
    renderModal();
    await waitFor(
      () => {
        expect(screen.getByTestId('rule-pack-preview-modal-yaml-error')).toBeTruthy();
      },
      { timeout: 2000 },
    );
    const banner = screen.getByTestId('rule-pack-preview-modal-yaml-error');
    expect(banner.textContent).toContain('parse boom');
  });

  it('disables the install button until the preview succeeds', async () => {
    // Never-resolving preview promise so the button stays disabled.
    previewMock.mockReturnValue(new Promise(() => {}));
    renderModal();
    const installBtn = screen.getByTestId(
      'rule-pack-preview-modal-install',
    ) as HTMLButtonElement;
    expect(installBtn.disabled).toBe(true);
  });

  it('fires the install POST after confirming the dialog', async () => {
    previewMock.mockResolvedValue(SUCCESS_RESPONSE);
    installMock.mockResolvedValue({
      requirement_set_id: 'rs-1',
      pack_id: 'p1',
      rules_installed: 2,
      rule_ids: ['din276_code_present', 'din276_code_in_building_range'],
    });
    renderModal();
    // Wait for the preview to land.
    await waitFor(() => expect(previewMock).toHaveBeenCalled());
    await waitFor(() => {
      const btn = screen.getByTestId('rule-pack-preview-modal-install') as HTMLButtonElement;
      expect(btn.disabled).toBe(false);
    });
    fireEvent.click(screen.getByTestId('rule-pack-preview-modal-install'));
    // ConfirmDialog renders a confirm button with data-testid="confirm-dialog-confirm".
    const confirmBtn = await screen.findByTestId('confirm-dialog-confirm');
    fireEvent.click(confirmBtn);
    await waitFor(() => expect(installMock).toHaveBeenCalledTimes(1));
    expect(installMock).toHaveBeenCalledWith({
      yaml_text: SEED.yaml,
      project_id: 'project-1',
    });
  });

  it('shows a success toast and closes the modal after install succeeds', async () => {
    previewMock.mockResolvedValue(SUCCESS_RESPONSE);
    installMock.mockResolvedValue({
      requirement_set_id: 'rs-1',
      pack_id: 'p1',
      rules_installed: 2,
      rule_ids: ['din276_code_present', 'din276_code_in_building_range'],
    });
    const onClose = vi.fn();
    renderModal({ onClose });
    await waitFor(() => expect(previewMock).toHaveBeenCalled());
    await waitFor(() => {
      const btn = screen.getByTestId('rule-pack-preview-modal-install') as HTMLButtonElement;
      expect(btn.disabled).toBe(false);
    });
    fireEvent.click(screen.getByTestId('rule-pack-preview-modal-install'));
    const confirmBtn = await screen.findByTestId('confirm-dialog-confirm');
    fireEvent.click(confirmBtn);
    await waitFor(() => expect(installMock).toHaveBeenCalled());
    await waitFor(() => expect(addToastMock).toHaveBeenCalled());
    expect(addToastMock.mock.calls[0]?.[0]).toMatchObject({ type: 'success' });
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it('renders dry-run pass/fail counts when a model is picked and preview returns dry_run', async () => {
    // Models load → one model returned.
    apiGetMock.mockResolvedValue({
      items: [{ id: 'model-a', name: 'Model A' }],
    });
    previewMock.mockResolvedValue({
      ...SUCCESS_RESPONSE,
      dry_run: {
        pack_id: 'din276',
        total_elements: 7,
        passed: 5,
        failed: 2,
        not_applicable: 0,
        results: expandDryRunRows([
          { rule_id: 'din276_code_present', pass_count: 3, fail_count: 1 },
          { rule_id: 'din276_code_in_building_range', pass_count: 2, fail_count: 1 },
        ]),
      },
    });
    renderModal();
    // Wait for the model dropdown to populate.
    await waitFor(() => {
      const select = screen.getByTestId(
        'rule-pack-preview-modal-model-select',
      ) as HTMLSelectElement;
      // The placeholder + 1 model = 2 options.
      expect(select.options.length).toBe(2);
    });
    const select = screen.getByTestId(
      'rule-pack-preview-modal-model-select',
    ) as HTMLSelectElement;
    fireEvent.change(select, { target: { value: 'model-a' } });
    await waitFor(() => {
      const chip = screen.getByTestId(
        'rule-pack-preview-modal-rule-din276_code_present-dryrun',
      );
      // pass / (pass+fail) = 3 / 4
      expect(chip.textContent).toContain('3 / 4');
    });
  });

  it('toggles the editor between readonly and editable in seed mode', () => {
    previewMock.mockResolvedValue(SUCCESS_RESPONSE);
    renderModal();
    const ta = screen.getByTestId(
      'rule-pack-preview-modal-yaml-textarea',
    ) as HTMLTextAreaElement;
    expect(ta.readOnly).toBe(true);
    const toggle = screen.getByTestId('rule-pack-preview-modal-readonly-toggle');
    fireEvent.click(toggle);
    expect(ta.readOnly).toBe(false);
    fireEvent.click(toggle);
    expect(ta.readOnly).toBe(true);
  });

  it('does NOT install when the Cancel button is clicked', () => {
    previewMock.mockResolvedValue(SUCCESS_RESPONSE);
    const onClose = vi.fn();
    renderModal({ onClose });
    fireEvent.click(screen.getByTestId('rule-pack-preview-modal-cancel'));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(installMock).not.toHaveBeenCalled();
  });

  // ── Test-against-current-model section ──────────────────────────────
  // Helper that wires up a model + dry-run preview response so each test
  // below starts from the "test mode is visible" state.
  async function renderWithTestMode(
    dryRunResults: Array<{ rule_id: string; pass_count: number; fail_count: number }>,
  ) {
    apiGetMock.mockResolvedValue({
      items: [{ id: 'model-a', name: 'Model A' }],
    });
    const rows = expandDryRunRows(dryRunResults);
    previewMock.mockResolvedValue({
      ...SUCCESS_RESPONSE,
      dry_run: {
        pack_id: 'din276',
        total_elements: rows.length,
        passed: rows.filter((r) => r.passed).length,
        failed: rows.filter((r) => !r.passed).length,
        not_applicable: 0,
        results: rows,
      },
    });
    renderModal();
    await waitFor(() => {
      const select = screen.getByTestId(
        'rule-pack-preview-modal-model-select',
      ) as HTMLSelectElement;
      expect(select.options.length).toBe(2);
    });
    fireEvent.change(
      screen.getByTestId('rule-pack-preview-modal-model-select') as HTMLSelectElement,
      { target: { value: 'model-a' } },
    );
    await waitFor(() => {
      expect(screen.getByTestId('rule-pack-preview-modal-test-mode')).toBeTruthy();
    });
  }

  it('renders the test-mode section only after picking a model', async () => {
    previewMock.mockResolvedValue(SUCCESS_RESPONSE);
    renderModal();
    // No dry_run on the initial preview → test-mode panel must not render.
    await waitFor(() => expect(previewMock).toHaveBeenCalled());
    expect(screen.queryByTestId('rule-pack-preview-modal-test-mode')).toBeNull();
  });

  it('shows pass/warn/fail counts and color-coded chips in test mode', async () => {
    // Rule 1 (severity=error) has 1 fail → red. Rule 2 (severity=warning)
    // has 2 fails → amber. No passing-only rule, so pass count is 0.
    await renderWithTestMode([
      { rule_id: 'din276_code_present', pass_count: 3, fail_count: 1 },
      { rule_id: 'din276_code_in_building_range', pass_count: 4, fail_count: 2 },
    ]);

    expect(
      screen.getByTestId('rule-pack-preview-modal-test-mode-pass-count').textContent,
    ).toContain('0');
    expect(
      screen.getByTestId('rule-pack-preview-modal-test-mode-warn-count').textContent,
    ).toContain('1');
    expect(
      screen.getByTestId('rule-pack-preview-modal-test-mode-fail-count').textContent,
    ).toContain('1');

    const errorRule = screen.getByTestId(
      'rule-pack-preview-modal-test-mode-rule-din276_code_present',
    );
    expect(errorRule.getAttribute('data-status')).toBe('fail');

    const warnRule = screen.getByTestId(
      'rule-pack-preview-modal-test-mode-rule-din276_code_in_building_range',
    );
    expect(warnRule.getAttribute('data-status')).toBe('warn');
  });

  it('marks rules with zero failures as pass (green)', async () => {
    await renderWithTestMode([
      { rule_id: 'din276_code_present', pass_count: 5, fail_count: 0 },
      { rule_id: 'din276_code_in_building_range', pass_count: 8, fail_count: 0 },
    ]);
    const passRule = screen.getByTestId(
      'rule-pack-preview-modal-test-mode-rule-din276_code_present',
    );
    expect(passRule.getAttribute('data-status')).toBe('pass');
    expect(
      screen.getByTestId('rule-pack-preview-modal-test-mode-pass-count').textContent,
    ).toContain('2');
    expect(
      screen.getByTestId('rule-pack-preview-modal-test-mode-fail-count').textContent,
    ).toContain('0');
  });

  it('expands a rule on click to reveal the per-rule fail count drilldown', async () => {
    await renderWithTestMode([
      { rule_id: 'din276_code_present', pass_count: 1, fail_count: 4 },
      { rule_id: 'din276_code_in_building_range', pass_count: 7, fail_count: 0 },
    ]);
    // Before click — no element list.
    expect(
      screen.queryByTestId(
        'rule-pack-preview-modal-test-mode-rule-din276_code_present-elements',
      ),
    ).toBeNull();
    fireEvent.click(
      screen.getByTestId('rule-pack-preview-modal-test-mode-rule-din276_code_present-toggle'),
    );
    const drilldown = screen.getByTestId(
      'rule-pack-preview-modal-test-mode-rule-din276_code_present-elements',
    );
    expect(drilldown.textContent).toMatch(/4/);
    // Toggling again should collapse.
    fireEvent.click(
      screen.getByTestId('rule-pack-preview-modal-test-mode-rule-din276_code_present-toggle'),
    );
    expect(
      screen.queryByTestId(
        'rule-pack-preview-modal-test-mode-rule-din276_code_present-elements',
      ),
    ).toBeNull();
  });

  it('per-rule fail-count chip reflects the dry-run failures', async () => {
    await renderWithTestMode([
      { rule_id: 'din276_code_present', pass_count: 1, fail_count: 7 },
      { rule_id: 'din276_code_in_building_range', pass_count: 2, fail_count: 0 },
    ]);
    const failChip = screen.getByTestId(
      'rule-pack-preview-modal-test-mode-rule-din276_code_present-fail-count',
    );
    expect(failChip.textContent).toContain('7');
    const okChip = screen.getByTestId(
      'rule-pack-preview-modal-test-mode-rule-din276_code_in_building_range-fail-count',
    );
    expect(okChip.textContent).toContain('0');
  });
});

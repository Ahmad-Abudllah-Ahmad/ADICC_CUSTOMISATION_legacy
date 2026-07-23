// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * RulePackLibrary unit tests.
 *
 * Render the library with mocked API + mocked toast store so the only
 * thing exercised is the filter/search/grid/modal-open behaviour.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  render,
  screen,
  fireEvent,
  cleanup,
  within,
} from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/shared/lib/api', () => ({
  apiGet: vi.fn().mockResolvedValue({ items: [] }),
  apiPost: vi.fn(),
}));

vi.mock('../api', () => ({
  previewYaml: vi.fn().mockResolvedValue({ pack: { rules: [] } }),
  installYaml: vi.fn().mockResolvedValue({
    requirement_set_id: 'rs-1',
    pack_id: 'pack',
    rules_installed: 0,
    rule_ids: [],
  }),
}));

import { RulePackLibrary } from '../RulePackLibrary';
import { SEED_PACKS } from '../SEED_PACKS';

function renderLibrary(projectId: string | null = 'project-1') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <RulePackLibrary projectId={projectId} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  cleanup();
});

describe('RulePackLibrary', () => {
  it('renders all 5 seed packs in the grid', () => {
    renderLibrary();
    const grid = screen.getByTestId('rule-pack-library-grid');
    for (const pack of SEED_PACKS) {
      expect(within(grid).getByTestId(`rule-pack-card-${pack.id}`)).toBeTruthy();
    }
  });

  it('filters by category when a category pill is clicked', () => {
    renderLibrary();
    const firePill = screen.getByTestId('rule-pack-library-filter-fire-safety');
    fireEvent.click(firePill);
    const grid = screen.getByTestId('rule-pack-library-grid');
    expect(within(grid).getByTestId('rule-pack-card-fire_compartment_property')).toBeTruthy();
    // Other categories should be filtered out.
    expect(within(grid).queryByTestId('rule-pack-card-din_276_kg_completeness')).toBeNull();
    expect(within(grid).queryByTestId('rule-pack-card-mep_clearance')).toBeNull();
  });

  it('filters by search query against name + description', () => {
    renderLibrary();
    const search = screen.getByTestId('rule-pack-library-search');
    fireEvent.change(search, { target: { value: 'corridor' } });
    const grid = screen.getByTestId('rule-pack-library-grid');
    // Only the corridor/door pack matches.
    expect(within(grid).getByTestId('rule-pack-card-clearance_corridor_door')).toBeTruthy();
    expect(within(grid).queryByTestId('rule-pack-card-din_276_kg_completeness')).toBeNull();
  });

  it('shows the empty state when no packs match the filter', () => {
    renderLibrary();
    const search = screen.getByTestId('rule-pack-library-search');
    fireEvent.change(search, { target: { value: 'zzzz-no-match-zzzz' } });
    // Grid should be gone, EmptyState should be present.
    expect(screen.queryByTestId('rule-pack-library-grid')).toBeNull();
    // The EmptyState heading uses the defaultValue from the t() call.
    expect(screen.getByText('No matching rule packs')).toBeTruthy();
  });

  it('opens the preview modal in seed mode when a card is clicked', () => {
    renderLibrary();
    const card = screen.getByTestId('rule-pack-card-din_276_kg_completeness');
    fireEvent.click(card);
    // Modal renders → preview-modal testid present and the YAML editor
    // is prefilled with the seed pack content (readonly).
    const modal = screen.getByTestId('rule-pack-preview-modal');
    expect(modal).toBeTruthy();
    const ta = screen.getByTestId(
      'rule-pack-preview-modal-yaml-textarea',
    ) as HTMLTextAreaElement;
    expect(ta.value.length).toBeGreaterThan(0);
    expect(ta.readOnly).toBe(true);
  });

  it('opens the preview modal in custom mode via the Paste-your-own CTA', () => {
    renderLibrary();
    const paste = screen.getByTestId('rule-pack-library-paste-custom');
    fireEvent.click(paste);
    expect(screen.getByTestId('rule-pack-preview-modal')).toBeTruthy();
    // Custom mode → editor empty, placeholder reflects the paste CTA label.
    const ta = screen.getByTestId(
      'rule-pack-preview-modal-yaml-textarea',
    ) as HTMLTextAreaElement;
    expect(ta.value).toBe('');
  });

  it('opens the modal when Enter is pressed on a card (a11y)', () => {
    renderLibrary();
    const card = screen.getByTestId('rule-pack-card-mep_clearance');
    fireEvent.keyDown(card, { key: 'Enter' });
    expect(screen.getByTestId('rule-pack-preview-modal')).toBeTruthy();
    // Editor should be populated with the MEP-clearance YAML.
    const ta = screen.getByTestId(
      'rule-pack-preview-modal-yaml-textarea',
    ) as HTMLTextAreaElement;
    expect(ta.value).toContain('mep_clearance');
  });

  it('renders region and classification chips for each card', () => {
    renderLibrary();
    const card = screen.getByTestId('rule-pack-card-din_276_kg_completeness');
    // Region chips → DE / AT / CH / LU
    expect(
      within(card).getByTestId('rule-pack-card-din_276_kg_completeness-region-DE'),
    ).toBeTruthy();
    // Classification chip → DIN276
    expect(
      within(card).getByTestId(
        'rule-pack-card-din_276_kg_completeness-classification-DIN276',
      ),
    ).toBeTruthy();
  });
});

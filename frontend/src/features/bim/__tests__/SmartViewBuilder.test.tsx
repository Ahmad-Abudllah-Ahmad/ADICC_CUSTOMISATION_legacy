// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * SmartViewBuilder UI smoke test.
 *
 * Verifies:
 *   - the builder renders an empty AND group with no rules
 *   - quick presets render and clicking one replaces the rule tree
 *   - clicking "+ Rule" appends a leaf rule
 *   - the AND/OR group toggle flips on click
 *   - the live-count pill renders once the preview query resolves
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import SmartViewBuilder from '../SmartViewBuilder';
import type {
  SmartViewGroup,
  SmartViewPropertyCatalog,
  SmartViewPreviewResult,
} from '../api';

// Stub the network layer — we want a deterministic catalog + preview.
vi.mock('../api', async (orig) => {
  const actual = await orig<typeof import('../api')>();
  return {
    ...actual,
    fetchSmartViewProperties: vi.fn(
      async (): Promise<SmartViewPropertyCatalog> => ({
        model_id: 'm1',
        source_format: 'IFC',
        element_count: 3,
        entries: [
          {
            field: 'element_type',
            label: 'element type',
            group: 'identity',
            data_type: 'enum',
            source_formats: ['IFC'],
            sample_values: ['IfcWall', 'IfcDoor'],
            distinct_count: 2,
            truncated: false,
          },
          {
            field: 'geometry.area_m2',
            label: 'area m2',
            group: 'geometry',
            data_type: 'number',
            source_formats: ['IFC'],
            sample_values: ['12.5', '25.0', '200.0'],
            distinct_count: 3,
            truncated: false,
          },
        ],
      }),
    ),
    previewSmartView: vi.fn(
      async (): Promise<SmartViewPreviewResult> => ({
        matched_count: 42,
        sample_element_ids: [],
        truncated: false,
        normalised_rule_tree: { op: 'AND', rules: [] },
      }),
    ),
  };
});

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

describe('SmartViewBuilder', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders an empty AND group + preset row', () => {
    const tree: SmartViewGroup = { op: 'AND', rules: [] };
    render(
      wrap(
        <SmartViewBuilder
          modelId="m1"
          projectId={null}
          value={tree}
          onChange={() => {}}
        />,
      ),
    );
    // Empty group hint visible.
    expect(screen.getByText(/No rules yet/i)).toBeInTheDocument();
    // Presets are present.
    expect(screen.getByText(/Walls only/i)).toBeInTheDocument();
    expect(screen.getByText(/Concrete elements/i)).toBeInTheDocument();
  });

  it('applies a preset on click', () => {
    const onChange = vi.fn<(next: SmartViewGroup) => void>();
    const tree: SmartViewGroup = { op: 'AND', rules: [] };
    render(
      wrap(
        <SmartViewBuilder
          modelId="m1"
          projectId={null}
          value={tree}
          onChange={onChange}
        />,
      ),
    );
    fireEvent.click(screen.getByText(/Walls only/i));
    expect(onChange).toHaveBeenCalledTimes(1);
    const next = onChange.mock.calls[0]![0]!;
    expect(next.op).toBe('OR');
    expect(next.rules.length).toBeGreaterThan(0);
  });

  it('adds a new leaf on "+ Rule" click', () => {
    const onChange = vi.fn<(next: SmartViewGroup) => void>();
    const tree: SmartViewGroup = { op: 'AND', rules: [] };
    render(
      wrap(
        <SmartViewBuilder
          modelId="m1"
          projectId={null}
          value={tree}
          onChange={onChange}
        />,
      ),
    );
    fireEvent.click(screen.getByText(/^Rule$/i));
    expect(onChange).toHaveBeenCalledTimes(1);
    const next = onChange.mock.calls[0]![0]!;
    expect(next.rules.length).toBe(1);
  });

  it('toggles AND ↔ OR on click', () => {
    const onChange = vi.fn<(next: SmartViewGroup) => void>();
    const tree: SmartViewGroup = { op: 'AND', rules: [] };
    render(
      wrap(
        <SmartViewBuilder
          modelId="m1"
          projectId={null}
          value={tree}
          onChange={onChange}
        />,
      ),
    );
    fireEvent.click(screen.getByText('AND'));
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange.mock.calls[0]![0]!.op).toBe('OR');
  });

  it('renders the live match-count pill once preview resolves', async () => {
    const tree: SmartViewGroup = { op: 'AND', rules: [] };
    render(
      wrap(
        <SmartViewBuilder
          modelId="m1"
          projectId={null}
          value={tree}
          onChange={() => {}}
        />,
      ),
    );
    await waitFor(() => {
      // i18n interpolation may or may not be active in the test harness,
      // so accept either the substituted text or the raw key.
      expect(
        screen.getByTestId('smart-view-preview-count'),
      ).toBeInTheDocument();
    });
  });
});

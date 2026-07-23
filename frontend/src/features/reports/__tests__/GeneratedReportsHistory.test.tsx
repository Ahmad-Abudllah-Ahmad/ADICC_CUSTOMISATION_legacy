// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
// Tests for <GeneratedReportsHistory> (Wave V_REPORTING).

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/shared/lib/api', () => ({ apiGet: vi.fn() }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_key: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? _key,
    i18n: { language: 'en' },
  }),
  // ``src/app/i18n.ts`` is pulled in transitively and calls
  // ``.use(initReactI18next)`` at module load — expose the noop plugin.
  initReactI18next: { type: '3rdParty', init: () => {} },
}));

import { apiGet } from '@/shared/lib/api';
import { GeneratedReportsHistory } from '../GeneratedReportsHistory';

function renderWithQuery(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const mockedApiGet = vi.mocked(apiGet);

describe('<GeneratedReportsHistory>', () => {
  beforeEach(() => mockedApiGet.mockReset());

  it('returns null when projectId is empty (no API call)', () => {
    const { container } = renderWithQuery(<GeneratedReportsHistory projectId="" />);
    expect(container.firstChild).toBeNull();
    expect(mockedApiGet).not.toHaveBeenCalled();
  });

  it('renders empty state when API returns []', async () => {
    mockedApiGet.mockResolvedValueOnce([]);
    renderWithQuery(<GeneratedReportsHistory projectId="proj-1" />);
    await waitFor(() => expect(screen.getByText('No reports generated yet')).toBeInTheDocument());
    expect(mockedApiGet).toHaveBeenCalledWith(
      '/v1/reporting/reports/?project_id=proj-1&limit=10',
    );
  });

  it('renders row with title, type and format badge', async () => {
    mockedApiGet.mockResolvedValueOnce([
      {
        id: 'r1',
        report_type: 'cost_report',
        title: 'Q1 cost report',
        format: 'pdf',
        created_at: '2026-05-01T10:00:00Z',
      },
    ]);
    renderWithQuery(<GeneratedReportsHistory projectId="proj-1" />);
    await waitFor(() => expect(screen.getByText('Q1 cost report')).toBeInTheDocument());
    expect(screen.getByText('pdf')).toBeInTheDocument();
  });
});
